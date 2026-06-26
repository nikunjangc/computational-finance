"""Optional LLM classifier (Claude Haiku) with a hard monthly spend cap.

This is an *upgrade* over the free bag-of-words matcher: it reads a flagged
transcript snippet and infers sector + direction + confidence with a small,
cheap model (default ``claude-haiku-4-5``). It is designed to cost about a
**dollar a month**:

* It only runs on snippets the free bag-of-words pre-filter already flagged,
  so the vast majority of text never reaches the API.
* The fixed sector guide is sent with prompt caching, so repeat calls bill the
  cached prefix at ~0.1x.
* A persistent :class:`CostTracker` enforces ``LLM_MONTHLY_BUDGET_USD``. Once
  the month's budget is spent, ``classify`` returns ``None`` and the engine
  transparently falls back to the free matcher.

If the ``anthropic`` package isn't installed or no API key is configured, the
classifier disables itself — the pipeline keeps working for free.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from ..knowledge_base import KnowledgeBase
from ..models import Direction
from .bag_of_words import KeywordMatch

log = logging.getLogger("stock_tracker.nlp.llm")

# Per-1M-token USD pricing (input, output). Cache read = 0.1x input,
# cache write = 1.25x input. Keep in sync with the model you select.
_PRICING = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
}


class CostTracker:
    """Persists monthly spend and enforces a budget (thread-safe)."""

    def __init__(self, path: str, monthly_budget_usd: float):
        self.path = path
        self.budget = monthly_budget_usd
        self._lock = threading.Lock()

    @staticmethod
    def _month() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _load(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, ValueError):
            data = {}
        # Roll over at the start of a new month.
        if data.get("month") != self._month():
            data = {"month": self._month(), "spent_usd": 0.0, "calls": 0}
        return data

    def _save(self, data: dict) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, self.path)

    def spent(self) -> float:
        with self._lock:
            return float(self._load().get("spent_usd", 0.0))

    def can_spend(self) -> bool:
        return self.spent() < self.budget

    @staticmethod
    def cost_of(usage, model: str) -> float:
        in_price, out_price = _PRICING.get(model, _PRICING["claude-haiku-4-5"])
        get = (lambda k: getattr(usage, k, 0) or 0) if not isinstance(usage, dict) else (lambda k: usage.get(k, 0) or 0)
        inp = get("input_tokens")
        out = get("output_tokens")
        cache_read = get("cache_read_input_tokens")
        cache_write = get("cache_creation_input_tokens")
        return (
            inp / 1e6 * in_price
            + cache_write / 1e6 * in_price * 1.25
            + cache_read / 1e6 * in_price * 0.10
            + out / 1e6 * out_price
        )

    def record(self, usage, model: str) -> float:
        cost = self.cost_of(usage, model)
        with self._lock:
            data = self._load()
            data["spent_usd"] = round(float(data.get("spent_usd", 0.0)) + cost, 6)
            data["calls"] = int(data.get("calls", 0)) + 1
            self._save(data)
        return cost


class LLMClassifier:
    def __init__(
        self,
        api_key: str,
        model: str,
        kb: KnowledgeBase,
        tracker: CostTracker,
        client=None,
        max_tokens: int = 300,
    ):
        self.api_key = api_key
        self.model = model
        self.kb = kb
        self.tracker = tracker
        self.max_tokens = max_tokens
        self._client = client  # injectable for tests
        self._system = self._build_system(kb)

    # ------------------------------------------------------------------
    @staticmethod
    def _build_system(kb: KnowledgeBase) -> str:
        lines = [
            "You are a market-event classifier. Given a short transcript snippet, "
            "identify which of the sectors below it implies, and whether the "
            "implication is bullish, bearish, or neutral for that sector's stocks.",
            "",
            "Sectors (use the exact key):",
        ]
        for key, s in kb.sectors.items():
            lines.append(f"- {key} ({s.display}): {', '.join(s.keywords[:6])}")
        lines += [
            "",
            'Respond with ONLY JSON: {"sectors":[{"key":"<sector_key>",'
            '"direction":"bullish|bearish|neutral","confidence":0.0-1.0}],"reason":"<short>"}',
            "Only include sectors genuinely implied by the text. If none apply, "
            'return {"sectors":[],"reason":"..."}.',
        ]
        return "\n".join(lines)

    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _call(self, text: str) -> Tuple[str, object]:
        resp = self.client().messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": self._system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": text}],
        )
        out = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        return out, resp.usage

    # ------------------------------------------------------------------
    def classify(self, text: str) -> Optional[List[KeywordMatch]]:
        """Return refined matches, or None to signal 'fall back to free mode'."""
        if not self.tracker.can_spend():
            log.info("LLM monthly budget reached ($%.2f); using free matcher", self.tracker.budget)
            return None
        try:
            raw, usage = self._call(text)
        except Exception as exc:
            log.warning("LLM call failed (%s); falling back to bag-of-words", exc)
            return None

        cost = self.tracker.record(usage, self.model)
        log.debug("LLM classify cost=$%.5f spent=$%.4f", cost, self.tracker.spent())
        return self._parse(raw, text)

    def _parse(self, raw: str, text: str) -> List[KeywordMatch]:
        data = _extract_json(raw)
        matches: List[KeywordMatch] = []
        for item in (data.get("sectors") or []):
            key = item.get("key")
            sector = self.kb.sectors.get(key)
            if not sector:
                continue
            try:
                direction = Direction(item.get("direction", "neutral"))
            except ValueError:
                direction = Direction.NEUTRAL
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.6))))
            kws = [k for k in sector.keywords if k in text.lower()]
            matches.append(
                KeywordMatch(
                    sector=sector,
                    keywords=kws or [sector.display],
                    direction=direction,
                    confidence=confidence,
                    rationale="LLM: " + str(data.get("reason", ""))[:200],
                )
            )
        return matches


def _extract_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except ValueError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                pass
    return {"sectors": [], "reason": "unparseable"}


def build_classifier(cfg, kb: KnowledgeBase) -> Optional[LLMClassifier]:
    if not cfg.llm_enabled:
        return None
    if not cfg.anthropic_api_key:
        log.info("LLM classifier requested but ANTHROPIC_API_KEY is unset; using free matcher")
        return None
    try:
        import anthropic  # noqa: F401
    except Exception:
        log.warning("anthropic package not installed; LLM classifier disabled. pip install anthropic")
        return None
    tracker = CostTracker(cfg.llm_state_path, cfg.llm_monthly_budget)
    log.info(
        "LLM classifier enabled: model=%s budget=$%.2f/mo spent=$%.4f",
        cfg.llm_model, cfg.llm_monthly_budget, tracker.spent(),
    )
    return LLMClassifier(cfg.anthropic_api_key, cfg.llm_model, kb, tracker)
