"""Telegram Application builder — wires all command handlers."""
from __future__ import annotations

from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, ConversationHandler,
    MessageHandler, filters,
)

from app.config.settings import settings
from app.telegram_bot import handlers as h
from app.telegram_bot.service import TelegramService


def build_application() -> Application:
    app = ApplicationBuilder().token(settings.telegram_bot_token).build()
    service = TelegramService()
    app.bot_data["service"] = service

    # /start onboarding conversation
    onboarding = ConversationHandler(
        entry_points=[CommandHandler("start", h.cmd_start)],
        states={
            h.STATE_CAPITAL:   [MessageHandler(filters.TEXT & ~filters.COMMAND, h.onboard_capital)],
            h.STATE_RISK:      [MessageHandler(filters.TEXT & ~filters.COMMAND, h.onboard_risk)],
            h.STATE_STYLE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, h.onboard_style)],
            h.STATE_WATCHLIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, h.onboard_watchlist)],
        },
        fallbacks=[CommandHandler("cancel", h.onboard_cancel)],
        allow_reentry=True,
    )
    app.add_handler(onboarding)

    for cmd, fn in [
        ("analyze", h.cmd_analyze),
        ("quick", h.cmd_quick),
        ("positional", h.cmd_positional),
        ("swing", h.cmd_swing),
        ("trade", h.cmd_trade),
        ("iv", h.cmd_iv),
        ("levels", h.cmd_levels),
        ("news", h.cmd_news),
        ("watchlist", h.cmd_watchlist),
        ("addwatch", h.cmd_addwatch),
        ("settings", h.cmd_settings),
        ("setcapital", h.cmd_setcapital),
        ("setrisk", h.cmd_setrisk),
        ("alerts", h.cmd_alerts),
        ("learn", h.cmd_learn),
        ("history", h.cmd_history),
        ("help", h.cmd_help),
        ("status", h.cmd_status),
    ]:
        app.add_handler(CommandHandler(cmd, fn))

    return app
