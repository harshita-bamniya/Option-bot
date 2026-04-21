"""Thin repository layer — keeps DB access out of business logic."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional

import pandas as pd
from sqlalchemy import select, desc, func

from app.db.models import (
    User, MarketData, OptionsChainRow, IVHistory, NewsItem,
    TradeSignal, TradeOutcome, LearningWeights, AlertLog,
)
from app.db.session import get_session


# ---------------- Users ----------------

class UserRepo:

    @staticmethod
    def get(chat_id: int) -> Optional[User]:
        with get_session() as s:
            return s.get(User, chat_id)

    @staticmethod
    def upsert(chat_id: int, **kwargs) -> User:
        with get_session() as s:
            user = s.get(User, chat_id)
            if not user:
                user = User(telegram_chat_id=chat_id, **kwargs)
                s.add(user)
            else:
                for k, v in kwargs.items():
                    setattr(user, k, v)
                user.updated_at = datetime.utcnow()
            s.flush()
            s.expunge(user)
            return user


# ------------ Market data / candles --------------

class MarketDataRepo:

    @staticmethod
    def insert_candles(rows: Iterable[dict]) -> None:
        """Bulk upsert OHLCV rows. Each row: {ts, instrument, timeframe, open, high, low, close, volume}."""
        rows = list(rows)
        if not rows:
            return
        from sqlalchemy.dialects.postgresql import insert
        with get_session() as s:
            stmt = insert(MarketData).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["instrument", "timeframe", "ts"],
                set_={
                    "open":   stmt.excluded.open,
                    "high":   stmt.excluded.high,
                    "low":    stmt.excluded.low,
                    "close":  stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                },
            )
            s.execute(stmt)

    @staticmethod
    def recent(instrument: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        with get_session() as s:
            q = (select(MarketData)
                 .where(MarketData.instrument == instrument, MarketData.timeframe == timeframe)
                 .order_by(desc(MarketData.ts))
                 .limit(limit))
            rows = s.execute(q).scalars().all()
        if not rows:
            return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
        data = [{"ts": r.ts, "open": r.open, "high": r.high, "low": r.low,
                 "close": r.close, "volume": r.volume} for r in rows]
        df = pd.DataFrame(data).sort_values("ts").set_index("ts")
        return df


# ------------- IV history --------------

class IVHistoryRepo:

    @staticmethod
    def upsert(row: dict) -> None:
        from sqlalchemy.dialects.postgresql import insert
        with get_session() as s:
            stmt = insert(IVHistory).values(**row)
            stmt = stmt.on_conflict_do_update(
                index_elements=["instrument", "date"],
                set_={k: v for k, v in row.items() if k not in ("instrument", "date")},
            )
            s.execute(stmt)

    @staticmethod
    def last_252(instrument: str) -> List[float]:
        """Return last 252 IV close values for IV Rank/Percentile computation."""
        cutoff = date.today() - timedelta(days=400)
        with get_session() as s:
            q = (select(IVHistory.iv_close)
                 .where(IVHistory.instrument == instrument, IVHistory.date >= cutoff)
                 .order_by(desc(IVHistory.date))
                 .limit(252))
            return [r[0] for r in s.execute(q).all()]


# ------------- Signals / Outcomes --------------

class SignalRepo:

    @staticmethod
    def insert(row: dict) -> None:
        with get_session() as s:
            s.add(TradeSignal(**row))

    @staticmethod
    def recent_for_user(chat_id: int, limit: int = 15) -> List[TradeSignal]:
        with get_session() as s:
            q = (select(TradeSignal)
                 .where(TradeSignal.telegram_chat_id == chat_id)
                 .order_by(desc(TradeSignal.ts))
                 .limit(limit))
            out = list(s.execute(q).scalars().all())
            for x in out:
                s.expunge(x)
            return out

    @staticmethod
    def stats(chat_id: Optional[int] = None) -> dict:
        with get_session() as s:
            base = select(TradeSignal, TradeOutcome).join(
                TradeOutcome, TradeOutcome.signal_id == TradeSignal.signal_id
            )
            if chat_id is not None:
                base = base.where(TradeSignal.telegram_chat_id == chat_id)
            rows = s.execute(base).all()
        wins = sum(1 for _, o in rows if o.outcome_label == "WIN")
        losses = sum(1 for _, o in rows if o.outcome_label == "LOSS")
        total = wins + losses
        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / total * 100) if total else 0.0,
        }


class OutcomeRepo:

    @staticmethod
    def upsert(signal_id: str, **fields) -> None:
        from sqlalchemy.dialects.postgresql import insert
        with get_session() as s:
            stmt = insert(TradeOutcome).values(signal_id=signal_id, **fields)
            stmt = stmt.on_conflict_do_update(
                index_elements=["signal_id"],
                set_={k: v for k, v in fields.items()},
            )
            s.execute(stmt)


# ------------- Learning --------------

class WeightsRepo:

    @staticmethod
    def active() -> Optional[LearningWeights]:
        with get_session() as s:
            q = select(LearningWeights).where(LearningWeights.active.is_(True)).limit(1)
            w = s.execute(q).scalar_one_or_none()
            if w:
                s.expunge(w)
            return w

    @staticmethod
    def activate(version_id: int) -> None:
        with get_session() as s:
            s.query(LearningWeights).update({LearningWeights.active: False})
            w = s.get(LearningWeights, version_id)
            if w:
                w.active = True
