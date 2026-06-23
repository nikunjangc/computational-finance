"""Generic websocket feed (the "open socket" push path).

Connects to one or more websocket endpoints (e.g. a news/headline feed, a
transcription service relaying CNBC / Yahoo Finance audio-to-text, or your own
relay) and emits each text message as an Utterance. Auto-reconnects with
backoff.

Requires the optional ``websockets`` package; disables itself cleanly if it is
not installed. Messages may be plain text or JSON; if JSON, the ``text`` /
``message`` / ``transcript`` field is used when present.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator, List

from ..models import Utterance
from .base import Source

log = logging.getLogger("stock_tracker.sources.websocket")


class WebSocketFeedSource(Source):
    name = "websocket"

    def __init__(self, urls: List[str], reconnect_max: float = 30.0):
        self.urls = urls
        self.reconnect_max = reconnect_max

    def _available(self) -> bool:
        try:
            import websockets  # noqa: F401
            return True
        except Exception:
            log.warning(
                "websockets not installed; websocket source disabled. "
                "Install with: pip install websockets"
            )
            return False

    @staticmethod
    def _parse(raw) -> str:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", "ignore")
        try:
            obj = json.loads(raw)
        except Exception:
            return str(raw)
        if isinstance(obj, dict):
            for k in ("text", "message", "transcript", "headline", "title"):
                if obj.get(k):
                    return str(obj[k])
        return str(obj)

    async def stream(self) -> AsyncIterator[Utterance]:
        if not self.urls or not self._available():
            return
        # Fan multiple sockets into one queue so a single async generator
        # can yield from all of them.
        queue: asyncio.Queue = asyncio.Queue()
        for url in self.urls:
            asyncio.create_task(self._listen(url, queue))
        while True:
            utt = await queue.get()
            yield utt

    async def _listen(self, url: str, queue: "asyncio.Queue"):
        import websockets
        backoff = 1.0
        while True:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    log.info("websocket connected: %s", url)
                    backoff = 1.0
                    async for raw in ws:
                        text = self._parse(raw)
                        if text.strip():
                            await queue.put(
                                Utterance(text=text, source=f"websocket:{url}", speaker="Feed")
                            )
            except Exception as exc:
                log.warning("websocket %s error: %s; reconnecting in %.0fs", url, exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(self.reconnect_max, backoff * 2)
