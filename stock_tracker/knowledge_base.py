"""Loads the sector knowledge base (the bag-of-words config)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List

import yaml

from .models import Direction, TickerHit

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "knowledge", "sectors.yaml")


@dataclass
class Sector:
    key: str
    display: str
    keywords: List[str]
    tickers: List[TickerHit]
    bias: Direction = Direction.NEUTRAL


@dataclass
class KnowledgeBase:
    sectors: Dict[str, Sector] = field(default_factory=dict)
    bullish: List[str] = field(default_factory=list)
    bearish: List[str] = field(default_factory=list)
    negations: List[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | None = None) -> "KnowledgeBase":
        path = path or os.environ.get("STOCK_TRACKER_KB", _DEFAULT_PATH)
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

        sectors: Dict[str, Sector] = {}
        for key, body in (raw.get("sectors") or {}).items():
            tickers = [
                TickerHit(symbol=t["symbol"], name=t.get("name", t["symbol"]), sector=body.get("display", key))
                for t in body.get("tickers", [])
            ]
            bias = Direction(body.get("bias", "neutral"))
            sectors[key] = Sector(
                key=key,
                display=body.get("display", key),
                keywords=[k.lower() for k in body.get("keywords", [])],
                tickers=tickers,
                bias=bias,
            )

        sentiment = raw.get("sentiment") or {}
        return cls(
            sectors=sectors,
            bullish=[w.lower() for w in sentiment.get("bullish", [])],
            bearish=[w.lower() for w in sentiment.get("bearish", [])],
            negations=[w.lower() for w in (raw.get("negations") or [])],
        )

    def all_symbols(self) -> List[str]:
        seen: Dict[str, None] = {}
        for s in self.sectors.values():
            for t in s.tickers:
                seen.setdefault(t.symbol, None)
        return list(seen)
