"""Bag-of-words matcher: find sector keywords in text and infer direction.

Deliberately dependency-free (pure regex + the YAML lexicons) so it runs
anywhere. It is a transparent, explainable baseline; you can later swap in a
transformer / LLM classifier behind the same ``match`` interface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from ..knowledge_base import KnowledgeBase, Sector
from ..models import Direction

_WORD_RE = re.compile(r"[a-z0-9.\-']+")


def tokenize(text: str) -> List[str]:
    return _WORD_RE.findall(text.lower())


@dataclass
class KeywordMatch:
    sector: Sector
    keywords: List[str]
    direction: Direction
    confidence: float
    rationale: str


class BagOfWordsMatcher:
    def __init__(self, kb: KnowledgeBase, sentiment_window: int = 8):
        self.kb = kb
        self.sentiment_window = sentiment_window
        # Pre-compile a whole-word/phrase pattern per keyword.
        self._patterns = {
            sector.key: [(kw, re.compile(r"\b" + re.escape(kw) + r"\b", re.I)) for kw in sector.keywords]
            for sector in kb.sectors.values()
        }

    def match(self, text: str) -> List[KeywordMatch]:
        """Return one KeywordMatch per sector whose keywords appear in *text*."""
        if not text:
            return []
        tokens = tokenize(text)
        results: List[KeywordMatch] = []

        for sector in self.kb.sectors.values():
            hits: List[str] = []
            for kw, pat in self._patterns[sector.key]:
                if pat.search(text):
                    hits.append(kw)
            if not hits:
                continue

            direction, dir_reason = self._infer_direction(tokens, hits, sector)
            confidence = self._confidence(hits, direction, sector)
            rationale = (
                f"Matched {len(hits)} keyword(s): {', '.join(hits)}. {dir_reason}"
            )
            results.append(
                KeywordMatch(
                    sector=sector,
                    keywords=hits,
                    direction=direction,
                    confidence=confidence,
                    rationale=rationale,
                )
            )
        return results

    # ------------------------------------------------------------------
    def _infer_direction(self, tokens: List[str], hits: List[str], sector: Sector, neg_window: int = 3):
        """Score bullish vs bearish sentiment words near the matched keywords.

        Negation is applied locally: a sentiment word is flipped only when a
        negation word ("not", "no", "ban"…) appears within ``neg_window``
        tokens *before* it – so "not support" flips but a separate "ban"
        nearby does not.
        """
        # Locate token indices where any keyword's first word appears.
        anchor_words = {h.split()[0] for h in hits}
        anchors = [i for i, tok in enumerate(tokens) if tok in anchor_words]
        if not anchors:
            anchors = list(range(len(tokens)))

        # Indices that sit within the sentiment window of some keyword anchor.
        near: set[int] = set()
        for a in anchors:
            near.update(range(max(0, a - self.sentiment_window), min(len(tokens), a + self.sentiment_window + 1)))

        score = 0
        cues: List[str] = []
        counted: set[int] = set()
        for i in sorted(near):
            if i in counted:
                continue
            tok = tokens[i]
            if tok not in self.kb.bullish and tok not in self.kb.bearish:
                continue
            counted.add(i)
            negated = any(tokens[j] in self.kb.negations for j in range(max(0, i - neg_window), i))
            sign = -1 if negated else 1
            if tok in self.kb.bullish:
                score += sign
                cues.append(("not " if negated else "") + tok + "↑")
            else:
                score -= sign
                cues.append(("not " if negated else "") + tok + "↓")

        if score > 0:
            direction = Direction.BULLISH
        elif score < 0:
            direction = Direction.BEARISH
        else:
            direction = sector.bias  # fall back to the sector's default lean

        if cues:
            reason = f"Sentiment cues {cues} -> net {score:+d} -> {direction.value}."
        else:
            reason = f"No directional cue; using sector bias -> {direction.value}."
        return direction, reason

    def _confidence(self, hits: List[str], direction: Direction, sector: Sector) -> float:
        # More keyword hits + a clear (non-neutral) direction => higher confidence.
        base = min(1.0, 0.45 + 0.18 * len(hits))
        if direction == Direction.NEUTRAL:
            base *= 0.7
        return round(base, 3)
