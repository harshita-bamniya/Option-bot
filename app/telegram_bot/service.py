"""TelegramService — high-level façade used by command handlers + scheduler.

Keeps the analysis pipeline, options chain access, news, and explanation
behind a single object so handlers stay thin.
"""
from __future__ import annotations

from datetime import timedelta
from typing import List, Optional

import pandas as pd

from app.core.analyzer import Analyzer, AnalysisResult
from app.data.market_data_service import MarketDataService
from app.data.options_chain import OptionsChainService, OptionsChain
from app.data.symbols import canonicalize_instrument
from app.db.repositories import MarketDataRepo, UserRepo, SignalRepo
from app.explain.explainer import Explainer
from app.explain.fallback_formatter import render_quick, render_options_trade
from app.news.marketaux import MarketauxClient
from app.news.sentiment import SentimentScorer
from app.config.constants import INSTRUMENT_UNIVERSE
from app.options.black_scholes import bs_greeks, implied_vol
from app.options.iv_rank import compute_iv_metrics, realized_vol_from_candles, realized_vol_rank
from app.utils.clock import now_ist
from app.utils.logging import get_logger

log = get_logger(__name__)


class TelegramService:

    def __init__(self) -> None:
        self.analyzer   = Analyzer()
        self.chain_svc  = OptionsChainService()
        self.news       = MarketauxClient()
        self.sentiment  = SentimentScorer()
        self.explainer  = Explainer()

    async def close(self) -> None:
        await self.chain_svc.close()
        await self.news.close()

    # ---------- candle loaders ----------

    def _load_candles(self, instrument: str) -> dict[str, pd.DataFrame]:
        return {
            "5m":  MarketDataRepo.recent(instrument, "5m",  500),
            "15m": MarketDataRepo.recent(instrument, "15m", 500),
            "1h":  MarketDataRepo.recent(instrument, "1h",  500),
            "1d":  MarketDataRepo.recent(instrument, "1d",  400),
        }

    # ---------- analyses ----------

    async def analyze(self, instrument: str, chat_id: int) -> str:
        result = await self._run_analysis(instrument, chat_id)
        if result is None:
            return f"⚠️ Not enough data for {instrument} yet — pipeline still warming."
        return await self.explainer.render(result)

    async def quick(self, instrument: str, chat_id: int) -> str:
        result = await self._run_analysis(instrument, chat_id)
        if result is None:
            return f"⚠️ Not enough data for {instrument}."
        return render_quick(result)

    async def positional(self, instrument: str, chat_id: int) -> str:
        result = await self._run_analysis(instrument, chat_id, style="positional")
        if result is None:
            return f"⚠️ No positional data for {instrument}."
        return await self.explainer.render(result)

    async def swing(self, instrument: str, chat_id: int) -> str:
        result = await self._run_analysis(instrument, chat_id, style="swing")
        if result is None:
            return f"⚠️ No swing data for {instrument}."
        return await self.explainer.render(result)

    async def _run_analysis(
        self, instrument: str, chat_id: int, *, style: str = "mixed"
    ) -> Optional[AnalysisResult]:
        instrument = canonicalize_instrument(instrument)
        if instrument not in INSTRUMENT_UNIVERSE:
            log.info("unknown_instrument", instrument=instrument)

        user = UserRepo.get(chat_id)
        capital = float(user.capital) if user else 500_000
        risk_pct = float(user.risk_pct) if user else 1.0

        candles = self._load_candles(instrument)
        primary = candles.get("15m") if candles.get("15m") is not None and len(candles["15m"]) > 30 else candles.get("1d")
        if primary is None or primary.empty:
            return None

        # Options chain (if this instrument has options)
        chain: Optional[OptionsChain] = None
        iv_now: Optional[float] = None
        inst_meta = INSTRUMENT_UNIVERSE.get(instrument, {})
        if inst_meta.get("options"):
            chain = await self.chain_svc.fetch(instrument)
            if chain:
                atm = chain.atm_strike()
                if atm:
                    atm_quote = next((q for q in chain.quotes
                                      if q.strike == atm and q.option_type == "CE" and q.iv), None)
                    if atm_quote and atm_quote.iv:
                        iv_now = float(atm_quote.iv) / 100.0 if atm_quote.iv > 5 else float(atm_quote.iv)

            # Fallback: estimate IV from realized volatility when chain unavailable
            if iv_now is None:
                daily_df = candles.get("1d")
                if daily_df is not None and not daily_df.empty:
                    iv_now = realized_vol_from_candles(daily_df)
                    if iv_now:
                        log.info("iv_estimated_from_realized_vol",
                                 instrument=instrument, iv_now=round(iv_now, 4))

        # News sentiment (last 6h)
        articles = await self.news.all_news(
            symbols=[instrument],
            since=now_ist() - timedelta(hours=6),
            limit=20,
        )
        news_score = self.sentiment.aggregate(articles, instrument=instrument)

        # VIX from last daily candle of INDIAVIX if present
        vix_df = MarketDataRepo.recent("INDIAVIX", "1d", 1)
        vix = float(vix_df["close"].iloc[-1]) if not vix_df.empty else None

        result = self.analyzer.analyze(
            instrument=instrument,
            candles_by_tf=candles,
            options_chain=chain,
            news_sentiment=news_score,
            vix_level=vix,
            iv_now=iv_now,
            user_capital=capital,
            user_risk_pct=risk_pct,
            chat_id=chat_id,
            lot_size=inst_meta.get("lot_size") or 1,
        )
        return result

    # ---------- specific commands ----------

    async def iv_report(self, instrument: str) -> str:
        instrument = canonicalize_instrument(instrument)
        chain = await self.chain_svc.fetch(instrument)
        if not chain:
            return f"⚠️ No options chain available for {instrument}."
        atm = chain.atm_strike()
        atm_q = next((q for q in chain.quotes if q.strike == atm and q.option_type == "CE"), None)
        iv_now = (atm_q.iv / 100 if atm_q and atm_q.iv and atm_q.iv > 5 else atm_q.iv) if atm_q else None
        if not iv_now:
            return f"⚠️ IV unavailable for {instrument} at ATM {atm}."
        m = compute_iv_metrics(instrument, iv_now)
        from app.options.metrics import pcr, max_pain
        pr, mp = pcr(chain), max_pain(chain)
        return (
            f"📊 IV REPORT — {instrument}\n"
            f"ATM Strike: {atm}   Spot: {chain.spot:.2f}\n"
            f"IV: {iv_now*100:.1f}%   IV Rank: {m['iv_rank']:.0f}   IV Pctl: {m['iv_percentile']:.0f}\n"
            f"State: {m['iv_state']}\n"
            f"PCR: {pr:.2f}   Max Pain: {mp:.0f}\n"
            f"History depth: {m['history_days']} days"
        )

    async def trade(self, instrument: str, option_type: str, strike: float) -> str:
        instrument = canonicalize_instrument(instrument)
        option_type = option_type.upper()
        if option_type not in ("CE", "PE"):
            return "⚠️ Option type must be CE or PE."
        chain = await self.chain_svc.fetch(instrument)
        if not chain:
            return f"⚠️ Chain unavailable for {instrument}."
        q = next((x for x in chain.quotes if x.strike == strike and x.option_type == option_type), None)
        if not q:
            return f"⚠️ No quote for {instrument} {strike} {option_type}."
        spot = chain.spot
        days_to_expiry = max((chain.expiry - now_ist().date()).days, 0)
        T = max(days_to_expiry, 1) / 365.0
        sigma = (q.iv / 100 if q.iv and q.iv > 5 else q.iv) if q.iv else implied_vol(
            price=q.ltp or 0, S=spot, K=strike, T=T,
            option_type="C" if option_type == "CE" else "P",
        )
        if sigma is None:
            sigma = 0.18
        g = bs_greeks(spot, strike, T, 0.07, sigma, "C" if option_type == "CE" else "P")
        breakeven = strike + (q.ltp or 0) if option_type == "CE" else strike - (q.ltp or 0)
        iv_m = compute_iv_metrics(instrument, sigma)

        verdict = "Tradeable" if 0.25 <= abs(g["delta"]) <= 0.70 else "Caution — delta suboptimal"
        caution = f"Theta -Rs {abs(g['theta']):.1f}/day" if T < 10 / 365 else "Time-decay manageable"
        note = "Naked call okay for intraday — use spread for multi-day hold"
        return render_options_trade(
            instrument=instrument, option_type=option_type, strike=strike,
            premium=q.ltp or 0, delta=g["delta"], gamma=g["gamma"],
            theta=g["theta"], vega=g["vega"], iv=sigma, iv_rank=iv_m["iv_rank"],
            breakeven=breakeven, verdict=verdict, caution=caution, strategy_note=note,
        )

    async def levels(self, instrument: str) -> str:
        instrument = canonicalize_instrument(instrument)
        from app.indicators.structure import compute_key_levels
        df = MarketDataRepo.recent(instrument, "1d", 60)
        if df.empty:
            return f"⚠️ No data for {instrument}."
        kl = compute_key_levels(df)
        return (
            f"📐 KEY LEVELS — {instrument}\n"
            f"Pivot: {kl.pivot:.2f}\n"
            f"R1/R2/R3: {kl.r1:.2f} / {kl.r2:.2f} / {kl.r3:.2f}\n"
            f"S1/S2/S3: {kl.s1:.2f} / {kl.s2:.2f} / {kl.s3:.2f}\n"
            f"Swing High/Low: {kl.swing_high:.2f} / {kl.swing_low:.2f}\n"
            f"Fib 38.2 / 50 / 61.8: {kl.fib_382:.2f} / {kl.fib_500:.2f} / {kl.fib_618:.2f}"
        )

    async def news_brief(self, instrument: str) -> str:
        instrument = canonicalize_instrument(instrument)
        articles = await self.news.all_news(
            symbols=[instrument], since=now_ist() - timedelta(hours=12), limit=10,
        )
        if not articles:
            return f"📰 No recent news for {instrument}."
        score = self.sentiment.aggregate(articles, instrument=instrument)
        lines = [f"📰 NEWS BRIEF — {instrument}  (sentiment: {score:+.2f})"]
        for a in articles[:5]:
            lines.append(f"• {a.get('title','')[:100]}")
        return "\n".join(lines)

    async def watchlist_scan(self, chat_id: int) -> str:
        user = UserRepo.get(chat_id)
        if not user or not user.watchlist:
            return "⚠️ No watchlist. Add with /addwatch SYMBOL"
        lines = [f"👁️ WATCHLIST SCAN — {len(user.watchlist)} instruments"]
        for sym in user.watchlist[:10]:
            try:
                r = await self._run_analysis(sym, chat_id)
                if r is None:
                    lines.append(f"• {sym}: — (no data)")
                    continue
                lines.append(f"• {sym}: {r.direction} | FCS {r.fcs:+.0f} | {r.trade_type}")
            except Exception:
                lines.append(f"• {sym}: error")
        return "\n".join(lines)

    def history(self, chat_id: int) -> str:
        sigs = SignalRepo.recent_for_user(chat_id, limit=15)
        if not sigs:
            return "📜 No signals yet."
        lines = ["📜 HISTORY (last 15)"]
        for s in sigs:
            lines.append(f"• {s.ts.strftime('%m-%d %H:%M')} {s.instrument:9} "
                         f"{s.direction:8} FCS {s.fcs_score:+.0f}")
        return "\n".join(lines)

    def learn_status(self, chat_id: int) -> str:
        stats = SignalRepo.stats(chat_id)
        return (
            f"📈 LEARNING STATUS\n"
            f"Total closed: {stats['total']}\n"
            f"Wins: {stats['wins']}   Losses: {stats['losses']}\n"
            f"Win Rate: {stats['win_rate']:.1f}%"
        )
