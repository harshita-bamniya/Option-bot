"""Multi-provider explanation engine — renders AnalysisResult into the
spec §4.1 6-section Telegram report.

Provider priority (first configured key wins):
    1. Anthropic Claude  — ANTHROPIC_API_KEY   (paid, best quality)
    2. Groq              — GROQ_API_KEY         (FREE 14,400 req/day, Llama 3.3 70B)
    3. Google Gemini     — GEMINI_API_KEY       (FREE 1,500 req/day, Gemini 1.5 Flash)
    4. Fallback formatter — always available, no key, deterministic output

Add whichever key(s) you have to .env — the engine picks automatically.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import Optional

from app.config.settings import settings
from app.core.analyzer import AnalysisResult
from app.explain.fallback_formatter import render_analysis_fallback
from app.utils.logging import get_logger

log = get_logger(__name__)


SYSTEM_PROMPT = """You are the Explanation Engine for the AI Trading Co-Pilot — a
decision-support tool for Indian (NSE) options/positional traders.

Your ONLY job is to re-render the structured analysis JSON you receive into the
exact 6-section format shown below. You MUST NOT invent numbers, change any
levels, change the direction, or speculate beyond what the JSON says. Use only
facts from the JSON.

Format (≤1800 chars, plain text + emojis — this is a Telegram message):

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 AI TRADING CO-PILOT | {INSTRUMENT} ANALYSIS
🕐 Time: {TIME IST} | Session: {SESSION}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 SECTION 1: WHAT WE SEE
(Brief observation of price, key EMAs, patterns, volume. 2-3 sentences.)

📐 SECTION 2: WHY THIS MAKES SENSE
(Enumerated confluence: timeframe alignment, group scores, pattern, volume confirmation, news sentiment.)

📋 SECTION 3: TRADE PLAN
🟢/🔴 TRADE TYPE:   ...
🟢/🔴 DIRECTION:    BUY/SELL/NO TRADE
🟢 INSTRUMENT:      ...
🟢 ENTRY:           ...
🟢 STOP LOSS:       ...
🟢 TARGET 1:        ...
🟢 TARGET 2:        ...
🟢 RISK:REWARD:     ...
🟢 POSITION SIZE:   ... (lots)
🟢 MAX LOSS:        Rs ...

⚠️ SECTION 4: RISK FACTORS
(Bullet points: IV rank, events, VIX, setup weakness thresholds.)

🚫 SECTION 5: AVOID IF
(Bullet conditions that invalidate the setup.)

✅ SECTION 6: FINAL ADVICE
(One paragraph: conviction label (HIGH/MODERATE/LOW), concrete call to action, disclaimer suffix.)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Always close with: "This is decision support — all trades carry risk."
If direction is NO TRADE: skip Section 3 trade plan lines after DIRECTION; fill with "—".
"""


# ─── provider implementations ────────────────────────────────────────────────

async def _call_anthropic(payload: dict, timeout: float) -> str:
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await asyncio.wait_for(
        client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1200,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(payload)}],
        ),
        timeout=timeout,
    )
    return "".join(
        blk.text for blk in resp.content if getattr(blk, "type", "") == "text"
    )


async def _call_groq(payload: dict, timeout: float) -> str:
    from groq import AsyncGroq
    client = AsyncGroq(api_key=settings.groq_api_key)
    resp = await asyncio.wait_for(
        client.chat.completions.create(
            model="llama-3.3-70b-versatile",   # best free Groq model
            max_tokens=1200,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": json.dumps(payload)},
            ],
        ),
        timeout=timeout,
    )
    return resp.choices[0].message.content or ""


async def _call_gemini(payload: dict, timeout: float) -> str:
    import httpx
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-1.5-flash:generateContent?key={settings.gemini_api_key}"
    )
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": json.dumps(payload)}]}],
        "generationConfig": {"maxOutputTokens": 1200},
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await asyncio.wait_for(client.post(url, json=body), timeout=timeout)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]


# ─── provider registry ────────────────────────────────────────────────────────

_PROVIDERS = [
    ("anthropic", lambda: bool(settings.anthropic_api_key), _call_anthropic),
    ("groq",      lambda: bool(settings.groq_api_key),      _call_groq),
    ("gemini",    lambda: bool(settings.gemini_api_key),     _call_gemini),
]


# ─── main explainer ───────────────────────────────────────────────────────────

class Explainer:

    async def render(self, result: AnalysisResult, *, timeout: float = 8.0) -> str:
        payload = _to_compact_payload(result)

        for name, is_configured, call_fn in _PROVIDERS:
            if not is_configured():
                continue
            try:
                text = await call_fn(payload, timeout)
                if text and text.strip():
                    log.debug("explain_ok", provider=name)
                    return text
            except Exception as e:
                log.warning("explain_provider_failed", provider=name, reason=str(e))
                continue     # try next provider

        # All providers failed or unconfigured → deterministic fallback
        log.info("explain_using_fallback")
        return render_analysis_fallback(result)


def _to_compact_payload(r: AnalysisResult) -> dict:
    """Strip big nested indicator dumps — keep only what the LLM needs."""
    return {
        "instrument":    r.instrument,
        "time_ist":      r.ts.strftime("%H:%M"),
        "session":       r.session,
        "spot":          r.spot_price,
        "direction":     r.direction,
        "trade_type":    r.trade_type,
        "fcs":           round(r.fcs, 1),
        "confidence_pct": round(r.confidence_pct, 0),
        "entry":         round(r.entry_price, 2),
        "stop_loss":     round(r.stop_loss, 2),
        "target_1":      round(r.target_1, 2),
        "target_2":      round(r.target_2, 2),
        "risk_reward":   round(r.risk_reward, 2),
        "position":      r.position,
        "mtfs":          round(r.mtfs, 2),
        "iis":           round(r.iis_primary_tf, 1),
        "regime":        r.regime,
        "pattern":       {"name": r.pattern["name"], "confidence": r.pattern["confidence"]},
        "iv_rank":       r.iv_rank,
        "iv_percentile": r.iv_percentile,
        "vix":           r.vix,
        "pcr":           r.options["details"].get("pcr"),
        "strategy":      r.options.get("strategy"),
        "news_sentiment": round(r.news_sentiment, 2),
        "groups_summary": {g: {"state": v["state"], "score": round(v["score"], 2)}
                           for g, v in r.groups.items()},
        "risk_warnings":    r.warnings,
        "rejected_reasons": r.rejected_reasons,
    }
