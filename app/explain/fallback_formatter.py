"""Deterministic formatters used when Claude is unavailable (spec §4).

Must produce the same sections as the LLM, driven purely by the structured
AnalysisResult. No hallucination risk. Also used for /quick and /trade.
"""
from __future__ import annotations

from app.core.analyzer import AnalysisResult


HR = "━" * 35


def _dir_emoji(direction: str) -> str:
    return {"BUY": "🟢", "SELL": "🔴", "NO TRADE": "⚪"}.get(direction, "⚪")


def render_analysis_fallback(r: AnalysisResult) -> str:
    d = _dir_emoji(r.direction)
    lines = []
    lines.append(HR)
    lines.append(f"📊 AI TRADING CO-PILOT | {r.instrument} ANALYSIS")
    lines.append(f"🕐 Time: {r.ts.strftime('%H:%M')} IST | Session: {r.session}")
    lines.append(HR)
    lines.append("")
    lines.append("🔍 SECTION 1: WHAT WE SEE")
    gs = r.groups
    lines.append(
        f"{r.instrument} at {r.spot_price:.2f}. "
        f"Trend: {gs['trend']['state']}. Momentum: {gs['momentum']['state']}. "
        f"Volume: {gs['volume']['state']}. Volatility: {gs['volatility']['state']}. "
        f"Pattern: {r.pattern['name']} ({r.pattern['confidence']}). Regime: {r.regime}."
    )
    lines.append("")
    lines.append("📐 SECTION 2: WHY THIS MAKES SENSE")
    lines.append(
        f"(1) MTFS {r.mtfs:+.2f} — Daily/1H/15m/5m alignment. "
        f"(2) IIS {r.iis_primary_tf:+.1f}, group confluence. "
        f"(3) Options Score {r.options['score']:+.1f} "
        f"(IV Rank {r.iv_rank:.0f}, PCR {r.options['details'].get('pcr', 0):.2f}). " if r.iv_rank is not None
        else f"(3) Options layer inconclusive (no IV yet). "
    )
    lines.append(f"(4) Pattern contribution: {r.pattern['score']:+.0f}. "
                 f"News sentiment: {r.news_sentiment:+.2f}. FCS: {r.fcs:+.1f}.")
    lines.append("")

    lines.append("📋 SECTION 3: TRADE PLAN")
    lines.append(f"{d} TRADE TYPE:    {r.trade_type}")
    lines.append(f"{d} DIRECTION:     {r.direction}")
    if r.direction != "NO TRADE" and r.risk.get("allow", True):
        lines.append(f"🟢 ENTRY:         {r.entry_price:.2f}")
        lines.append(f"🟢 STOP LOSS:     {r.stop_loss:.2f}")
        lines.append(f"🟢 TARGET 1:      {r.target_1:.2f} (Book 50%)")
        lines.append(f"🟢 TARGET 2:      {r.target_2:.2f} (Book rest)")
        lines.append(f"🟢 RISK:REWARD:   {r.risk_reward:.2f} : 1")
        lines.append(f"🟢 POSITION:      {r.position['lots']} lots ({r.position['units']} units)")
        lines.append(f"🟢 MAX LOSS:      Rs {r.position['risk_rs']:.0f}")
        if r.options.get("strategy"):
            s = r.options["strategy"]
            lines.append(f"🧠 STRATEGY:      {s['strategy']} ({s['iv_state']})")
    else:
        lines.append("🚫 No trade — conditions not met")
    lines.append("")

    lines.append("⚠️ SECTION 4: RISK FACTORS")
    if r.iv_rank is not None:
        lines.append(f"• IV Rank {r.iv_rank:.0f} — {r.options.get('iv_metrics', {}).get('iv_state', '')}")
    if r.vix is not None:
        lines.append(f"• India VIX {r.vix:.1f}")
    for w in r.warnings:
        lines.append(f"• {w}")
    if r.rejected_reasons:
        for rr in r.rejected_reasons:
            lines.append(f"• BLOCKED: {rr}")
    if not r.warnings and not r.rejected_reasons:
        lines.append("• No hard-rule concerns detected.")
    lines.append("")

    lines.append("🚫 SECTION 5: AVOID IF")
    if r.direction == "BUY":
        lines.append(f"• Price closes below {r.stop_loss:.2f} on 15m candle")
    elif r.direction == "SELL":
        lines.append(f"• Price closes above {r.stop_loss:.2f} on 15m candle")
    lines.append("• Volume drops below 0.8x 20-day avg on next candle")
    lines.append("• HIGH-impact macro event announced within 30 minutes")
    lines.append("")

    conv = "HIGH CONVICTION" if abs(r.fcs) >= 60 else ("MODERATE" if abs(r.fcs) >= 35 else "LOW")
    lines.append("✅ SECTION 6: FINAL ADVICE")
    lines.append(
        f"{conv} SETUP (Confidence: {r.confidence_pct:.0f}%). FCS {r.fcs:+.1f}. "
        f"This is decision support — all trades carry risk."
    )
    lines.append(HR)
    return "\n".join(lines)


def render_quick(r: AnalysisResult) -> str:
    emoji = {"BUY": "🟢 BULLISH", "SELL": "🔴 BEARISH", "NO TRADE": "⚪ NEUTRAL"}[r.direction]
    lines = [
        f"⚡ QUICK SCAN | {r.instrument} | {r.ts.strftime('%H:%M')} IST",
        f"Direction:     {emoji} (Confidence: {r.confidence_pct:.0f}%)",
        f"Trade Type:    {r.trade_type}",
        f"Key Level:     Entry {r.entry_price:.2f}",
        f"SL Level:      {r.stop_loss:.2f}",
        f"Target:        {r.target_1:.2f} → {r.target_2:.2f}",
    ]
    if r.iv_rank is not None:
        s = r.options.get("strategy", {}).get("strategy", "")
        lines.append(f"IV Rank:       {r.iv_rank:.0f} ({r.options.get('iv_metrics',{}).get('iv_state','')}) → {s}")
    if r.rejected_reasons:
        lines.append(f"Avoid:         {r.rejected_reasons[0]}")
    return "\n".join(lines)


def render_options_trade(
    *, instrument: str, option_type: str, strike: float,
    premium: float, delta: float, gamma: float, theta: float, vega: float,
    iv: float, iv_rank: float, breakeven: float, verdict: str,
    caution: str, strategy_note: str,
) -> str:
    lines = [
        f"🎯 OPTIONS ANALYSIS | {instrument} {strike:.0f} {option_type}",
        f"Current Premium:    Rs {premium:.2f}",
        f"Delta:              {delta:.3f}",
        f"Gamma:              {gamma:.4f}",
        f"Theta:              Rs {theta:.2f}/day",
        f"Vega:               Rs {vega:.2f} per 1% IV",
        f"Breakeven:          {breakeven:.2f}",
        f"IV at Strike:       {iv*100:.1f}%   |   IV Rank: {iv_rank:.0f}",
        "",
        f"VERDICT:  {verdict}",
        f"CAUTION:  {caution}",
        f"STRATEGY: {strategy_note}",
    ]
    return "\n".join(lines)
