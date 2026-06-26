"""Generate platform-tailored social copy from a Signal.

Uses the LLM (shared budget with the classifier via CostTracker) when enabled,
and always has a free template fallback so posting works even with no API
budget left. A disclaimer is appended to every post.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from ..models import Signal

log = logging.getLogger("stock_tracker.content")

DEFAULT_DISCLAIMER = "Educational only — not financial advice. Do your own research."


@dataclass
class Post:
    caption: str
    hashtags: List[str] = field(default_factory=list)
    disclaimer: str = DEFAULT_DISCLAIMER

    def full_text(self) -> str:
        parts = [self.caption.strip()]
        if self.hashtags:
            parts.append(" ".join("#" + h.lstrip("#") for h in self.hashtags))
        if self.disclaimer:
            parts.append(self.disclaimer)
        return "\n\n".join(parts)


class ContentGenerator:
    def __init__(self, api_key=None, model="claude-haiku-4-5", tracker=None, client=None,
                 disclaimer: str = DEFAULT_DISCLAIMER):
        self.api_key = api_key
        self.model = model
        self.tracker = tracker
        self._client = client
        self.disclaimer = disclaimer

    # ------------------------------------------------------------------
    def generate(self, signal: Signal, platform: str = "facebook") -> Post:
        if self._llm_available():
            post = self._generate_llm(signal, platform)
            if post is not None:
                return post
        return self._template(signal)

    def _llm_available(self) -> bool:
        if not self.api_key or self.tracker is None:
            return False
        return self.tracker.can_spend()

    def _client_obj(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _generate_llm(self, signal: Signal, platform: str) -> Optional[Post]:
        u = signal.utterance
        prompt = (
            f"Write a short, punchy {platform} caption about this market event. "
            f"No hype, no guarantees, no price targets. 2-3 short lines max.\n\n"
            f"Sector: {signal.sector}\nDirection: {signal.direction.value}\n"
            f"Tickers: {', '.join(signal.symbols)}\nSpeaker: {u.speaker}\n"
            f"Quote: \"{u.short(200)}\"\n\n"
            'Respond ONLY as JSON: {"caption":"...","hashtags":["...", "..."]} '
            "(3-6 lowercase hashtags, no # prefix)."
        )
        try:
            resp = self._client_obj().messages.create(
                model=self.model,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
            if self.tracker is not None:
                self.tracker.record(resp.usage, self.model)
        except Exception as exc:
            log.warning("content LLM failed (%s); using template", exc)
            return None

        data = _extract_json(raw)
        caption = (data.get("caption") or "").strip()
        if not caption:
            return None
        hashtags = [str(h) for h in (data.get("hashtags") or [])][:6]
        return Post(caption=caption, hashtags=hashtags, disclaimer=self.disclaimer)

    def _template(self, signal: Signal) -> Post:
        u = signal.utterance
        tickers = ", ".join("$" + s for s in signal.symbols)
        caption = (
            f"{signal.direction.emoji} {signal.direction.value.upper()} watch — {signal.sector}\n"
            f"{u.speaker or 'Markets'} on the move: \"{u.short(140)}\"\n"
            f"Names in focus: {tickers or '—'}"
        )
        tags = _slug_tags(signal)
        return Post(caption=caption, hashtags=tags, disclaimer=self.disclaimer)


def _slug_tags(signal: Signal) -> List[str]:
    tags = ["stocks", "investing", "markets"]
    tags.append(re.sub(r"[^a-z0-9]", "", signal.sector_key.lower())[:24] or "trading")
    tags += [s.lower() for s in signal.symbols[:3]]
    # de-dup preserving order
    seen, out = set(), []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:6]


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
    return {}
