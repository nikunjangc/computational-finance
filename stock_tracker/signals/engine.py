"""Turns raw utterances into ranked, tradeable stock signals."""

from __future__ import annotations

from typing import List, Optional

from ..knowledge_base import KnowledgeBase
from ..models import Signal, Utterance
from ..nlp.bag_of_words import BagOfWordsMatcher


class SignalEngine:
    def __init__(self, kb: Optional[KnowledgeBase] = None, min_confidence: float = 0.45):
        self.kb = kb or KnowledgeBase.load()
        self.matcher = BagOfWordsMatcher(self.kb)
        self.min_confidence = min_confidence

    def process(self, utterance: Utterance) -> List[Signal]:
        """Return all signals above the confidence threshold, best first."""
        signals: List[Signal] = []
        for m in self.matcher.match(utterance.text):
            if m.confidence < self.min_confidence:
                continue
            signals.append(
                Signal(
                    utterance=utterance,
                    sector=m.sector.display,
                    sector_key=m.sector.key,
                    matched_keywords=m.keywords,
                    direction=m.direction,
                    confidence=m.confidence,
                    tickers=list(m.sector.tickers),
                    rationale=m.rationale,
                )
            )
        signals.sort(key=lambda s: s.confidence, reverse=True)
        return signals

    def process_text(self, text: str, source: str = "cli", speaker: str = "cli") -> List[Signal]:
        """Convenience wrapper to classify a bare string."""
        return self.process(Utterance(text=text, source=source, speaker=speaker))
