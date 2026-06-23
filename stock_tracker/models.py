"""Core data models passed between sources, the signal engine and notifiers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Direction(str, Enum):
    """Inferred market direction implied by an utterance for a sector."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"

    @property
    def emoji(self) -> str:
        return {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}[self.value]


@dataclass
class Utterance:
    """A unit of raw text captured from a live source.

    Every source – a YouTube live caption line, an FOMC calendar event, a
    crypto-index move, a websocket headline – is normalised into one of
    these so the rest of the pipeline is source-agnostic.
    """

    text: str
    source: str                       # e.g. "youtube:CNBC", "calendar:FOMC"
    speaker: Optional[str] = None     # e.g. "Jerome Powell", "Trump"
    url: Optional[str] = None
    timestamp: datetime = field(default_factory=_now)
    meta: Dict = field(default_factory=dict)

    def short(self, n: int = 160) -> str:
        t = " ".join(self.text.split())
        return t if len(t) <= n else t[: n - 1] + "…"


@dataclass
class TickerHit:
    """A stock related to a detected sector."""

    symbol: str
    name: str
    sector: str


@dataclass
class Signal:
    """The output of the engine: a tradeable theme detected in an utterance."""

    utterance: Utterance
    sector: str                       # human readable sector display name
    sector_key: str                   # machine key in the knowledge base
    matched_keywords: List[str]
    direction: Direction
    confidence: float                 # 0..1
    tickers: List[TickerHit]
    rationale: str = ""

    @property
    def symbols(self) -> List[str]:
        return [t.symbol for t in self.tickers]

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.utterance.timestamp.isoformat(),
            "source": self.utterance.source,
            "speaker": self.utterance.speaker,
            "sector": self.sector,
            "direction": self.direction.value,
            "confidence": round(self.confidence, 3),
            "matched_keywords": self.matched_keywords,
            "tickers": self.symbols,
            "text": self.utterance.short(240),
            "url": self.utterance.url,
        }
