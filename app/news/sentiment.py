"""Sentiment scoring — prefers Marketaux-provided entity sentiment; falls back
to VADER for headlines we scrape or when Marketaux doesn't return sentiment.

Output scale: [-1.0, +1.0]. Spec §4 treats news sentiment as ±1 input to FCS.
"""
from __future__ import annotations

from typing import Iterable, List, Optional

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


class SentimentScorer:

    def __init__(self) -> None:
        self._vader = SentimentIntensityAnalyzer()

    def score_headline(self, text: str) -> float:
        if not text:
            return 0.0
        s = self._vader.polarity_scores(text)
        return float(s["compound"])  # already in [-1,1]

    def score_marketaux_article(self, article: dict, instrument: Optional[str] = None) -> float:
        """Use Marketaux's entity-level sentiment if present; else VADER on title+snippet."""
        entities = article.get("entities") or []
        if instrument:
            wanted = instrument.lower().split()[0]
            for e in entities:
                sym = (e.get("symbol") or "").lower()
                name = (e.get("name") or "").lower()
                if wanted in sym or wanted in name:
                    val = e.get("sentiment_score")
                    if val is not None:
                        return max(-1.0, min(1.0, float(val)))
        # Average all entity sentiments
        vals = [e.get("sentiment_score") for e in entities if e.get("sentiment_score") is not None]
        if vals:
            return max(-1.0, min(1.0, sum(vals) / len(vals)))
        # Fallback: VADER on title + snippet
        title = article.get("title") or ""
        snippet = article.get("snippet") or article.get("description") or ""
        return self.score_headline(f"{title}. {snippet}")

    def aggregate(self, articles: Iterable[dict], instrument: Optional[str] = None) -> float:
        articles = list(articles)
        if not articles:
            return 0.0
        scores: List[float] = []
        for a in articles:
            scores.append(self.score_marketaux_article(a, instrument))
        return sum(scores) / len(scores)
