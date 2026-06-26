"""Offline demo source that replays sample transcript lines.

Used by ``--demo`` so the whole pipeline can be exercised end-to-end without
any API keys or network access.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import AsyncIterator, List, Optional

from ..models import Utterance
from .base import Source

_SAMPLE = os.path.join(os.path.dirname(__file__), "..", "sample_data", "transcripts.json")


class MockFeedSource(Source):
    name = "mock"

    def __init__(self, path: Optional[str] = None, delay: float = 1.0, loop: bool = False):
        self.path = path or _SAMPLE
        self.delay = delay
        self.loop = loop

    def _load(self) -> List[dict]:
        with open(self.path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    async def stream(self) -> AsyncIterator[Utterance]:
        rows = self._load()
        while True:
            for row in rows:
                await asyncio.sleep(self.delay)
                yield Utterance(
                    text=row["text"],
                    source=row.get("source", "mock"),
                    speaker=row.get("speaker"),
                    url=row.get("url"),
                    meta={"demo": True},
                )
            if not self.loop:
                break
