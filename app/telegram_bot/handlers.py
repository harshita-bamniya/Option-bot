"""Telegram command handlers.

Each handler is a thin wrapper — real work happens in TelegramService.
Keeps this file focused on input parsing + error boundaries.
"""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from app.db.repositories import UserRepo
from app.telegram_bot.service import TelegramService
from app.utils.logging import get_logger

log = get_logger(__name__)

# Conversation states for /start onboarding
STATE_CAPITAL, STATE_RISK, STATE_STYLE, STATE_WATCHLIST = range(4)


HELP_TEXT = """📖 AI TRADING CO-PILOT — Commands

🔍 ANALYSIS
/analyze NIFTY      – Full 6-section analysis
/quick BANKNIFTY    – Fast 3-line scan
/positional INFY    – Positional setup (Daily+Weekly)
/swing RELIANCE     – 2-5 day swing setup
/trade NIFTY CE 24500 – Specific options strike
/iv NIFTY           – IV Rank + strategy
/levels NIFTY       – S/R + pivots + fibs
/news NIFTY         – Latest news + sentiment

👁️ WATCHLIST
/watchlist          – Scan all your instruments
/addwatch SBIN      – Add to watchlist

⚙️ SETTINGS
/start              – Onboarding wizard
/settings           – View current settings
/setcapital 500000  – Update capital
/setrisk 1          – Update risk %  (0.5 / 1 / 1.5 / 2)
/alerts on|off      – Toggle alerts

📊 SYSTEM
/learn              – Learning engine stats
/history            – Last 15 signals
/status             – Market snapshot
/help               – This message
"""


def _service(context: ContextTypes.DEFAULT_TYPE) -> TelegramService:
    return context.application.bot_data["service"]


# ---------------------- /start onboarding ----------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Welcome {user.first_name or 'Trader'} to the AI Trading Co-Pilot.\n\n"
        "A few quick setup questions —\n"
        "1️⃣ What is your trading capital? (in INR, e.g. 500000)"
    )
    return STATE_CAPITAL


async def onboard_capital(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        cap = float(update.message.text.strip().replace(",", ""))
        context.user_data["capital"] = cap
    except ValueError:
        await update.message.reply_text("Please send a number, e.g. 500000")
        return STATE_CAPITAL
    await update.message.reply_text("2️⃣ Risk per trade? (0.5 / 1 / 1.5 / 2)")
    return STATE_RISK


async def onboard_risk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        r = float(update.message.text.strip())
        if not 0.1 <= r <= 5:
            raise ValueError
        context.user_data["risk_pct"] = r
    except ValueError:
        await update.message.reply_text("Send 0.5, 1, 1.5, or 2")
        return STATE_RISK
    await update.message.reply_text(
        "3️⃣ Trade style? (Intraday / Swing / Positional / All)"
    )
    return STATE_STYLE


async def onboard_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    style = update.message.text.strip().title()
    if style not in ("Intraday", "Swing", "Positional", "All"):
        await update.message.reply_text("Choose: Intraday / Swing / Positional / All")
        return STATE_STYLE
    context.user_data["trade_style"] = style
    await update.message.reply_text(
        "4️⃣ Watchlist (comma-separated NSE symbols) — e.g. NIFTY,BANKNIFTY,RELIANCE"
    )
    return STATE_WATCHLIST


async def onboard_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    wl = [s.strip().upper() for s in update.message.text.split(",") if s.strip()]
    if not wl:
        wl = ["NIFTY", "BANKNIFTY"]
    UserRepo.upsert(
        chat_id=update.effective_chat.id,
        username=update.effective_user.username,
        capital=context.user_data["capital"],
        risk_pct=context.user_data["risk_pct"],
        trade_style=context.user_data["trade_style"],
        watchlist=wl,
    )
    await update.message.reply_text(
        "✅ Setup complete!\n\n"
        f"Capital: Rs {context.user_data['capital']:,.0f}\n"
        f"Risk/trade: {context.user_data['risk_pct']}%\n"
        f"Style: {context.user_data['trade_style']}\n"
        f"Watchlist: {', '.join(wl)}\n\n"
        "Send /help for commands. Try /analyze NIFTY 📈"
    )
    return ConversationHandler.END


async def onboard_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Setup cancelled. Run /start any time.")
    return ConversationHandler.END


# ---------------------- analysis commands ----------------------

async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /analyze SYMBOL   e.g. /analyze NIFTY")
        return
    sym = context.args[0].upper()
    await update.message.chat.send_action("typing")
    try:
        msg = await _service(context).analyze(sym, update.effective_chat.id)
    except Exception:
        log.exception("analyze_failed", sym=sym)
        msg = f"⚠️ Internal error analysing {sym}. Try again."
    await update.message.reply_text(msg)


async def cmd_quick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /quick SYMBOL")
        return
    msg = await _service(context).quick(context.args[0].upper(), update.effective_chat.id)
    await update.message.reply_text(msg)


async def cmd_positional(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /positional SYMBOL")
        return
    msg = await _service(context).positional(context.args[0].upper(), update.effective_chat.id)
    await update.message.reply_text(msg)


async def cmd_swing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /swing SYMBOL")
        return
    msg = await _service(context).swing(context.args[0].upper(), update.effective_chat.id)
    await update.message.reply_text(msg)


async def cmd_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 3:
        await update.message.reply_text("Usage: /trade NIFTY CE 24500")
        return
    sym, ot, strike = context.args[0].upper(), context.args[1].upper(), float(context.args[2])
    msg = await _service(context).trade(sym, ot, strike)
    await update.message.reply_text(msg)


async def cmd_iv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /iv SYMBOL")
        return
    msg = await _service(context).iv_report(context.args[0].upper())
    await update.message.reply_text(msg)


async def cmd_levels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /levels SYMBOL")
        return
    msg = await _service(context).levels(context.args[0].upper())
    await update.message.reply_text(msg)


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /news SYMBOL")
        return
    msg = await _service(context).news_brief(context.args[0].upper())
    await update.message.reply_text(msg)


# ---------------------- watchlist ----------------------

async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await _service(context).watchlist_scan(update.effective_chat.id)
    await update.message.reply_text(msg)


async def cmd_addwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /addwatch SYMBOL")
        return
    sym = context.args[0].upper()
    user = UserRepo.get(update.effective_chat.id)
    if not user:
        await update.message.reply_text("Please /start first.")
        return
    wl = list(user.watchlist)
    if sym not in wl:
        wl.append(sym)
        UserRepo.upsert(chat_id=update.effective_chat.id, watchlist=wl)
    await update.message.reply_text(f"✅ {sym} added — watchlist: {', '.join(wl)}")


# ---------------------- settings ----------------------

async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = UserRepo.get(update.effective_chat.id)
    if not u:
        await update.message.reply_text("Please /start first.")
        return
    await update.message.reply_text(
        f"⚙️ SETTINGS\n"
        f"Capital: Rs {float(u.capital):,.0f}\n"
        f"Risk/trade: {float(u.risk_pct)}%\n"
        f"Style: {u.trade_style}\n"
        f"Alerts: {'ON' if u.alerts_on else 'OFF'}\n"
        f"Watchlist: {', '.join(u.watchlist)}\n\n"
        f"Update: /setcapital AMOUNT  |  /setrisk PCT  |  /alerts on|off"
    )


async def cmd_setcapital(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /setcapital 500000")
        return
    try:
        cap = float(context.args[0].replace(",", ""))
    except ValueError:
        await update.message.reply_text("Send a valid number.")
        return
    UserRepo.upsert(chat_id=update.effective_chat.id, capital=cap)
    await update.message.reply_text(f"✅ Capital updated: Rs {cap:,.0f}")


async def cmd_setrisk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /setrisk 1")
        return
    try:
        r = float(context.args[0])
        if not 0.1 <= r <= 5: raise ValueError
    except ValueError:
        await update.message.reply_text("Risk % must be between 0.1 and 5.")
        return
    UserRepo.upsert(chat_id=update.effective_chat.id, risk_pct=r)
    await update.message.reply_text(f"✅ Risk/trade updated: {r}%")


async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or context.args[0].lower() not in ("on", "off"):
        await update.message.reply_text("Usage: /alerts on|off")
        return
    on = context.args[0].lower() == "on"
    UserRepo.upsert(chat_id=update.effective_chat.id, alerts_on=on)
    await update.message.reply_text(f"✅ Alerts {'ON' if on else 'OFF'}")


# ---------------------- system ----------------------

async def cmd_learn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = _service(context).learn_status(update.effective_chat.id)
    await update.message.reply_text(msg)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = _service(context).history(update.effective_chat.id)
    await update.message.reply_text(msg)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.utils.clock import is_market_open, current_session, now_ist
    from app.db.repositories import MarketDataRepo
    vix_df = MarketDataRepo.recent("INDIAVIX", "1d", 1)
    vix = float(vix_df["close"].iloc[-1]) if not vix_df.empty else None
    await update.message.reply_text(
        f"📡 MARKET STATUS\n"
        f"Now (IST): {now_ist().strftime('%Y-%m-%d %H:%M')}\n"
        f"Session: {current_session()}\n"
        f"Open: {'✅' if is_market_open() else '❌'}\n"
        f"India VIX: {vix:.2f}" if vix else "India VIX: —"
    )
