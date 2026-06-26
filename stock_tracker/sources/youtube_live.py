"""YouTube live-caption / transcript watcher (CNBC, Yahoo Finance, etc.).

Polls the caption track of one or more YouTube videos / live streams and
emits newly-seen caption lines as Utterances. Real-time captions on a live
stream grow over time, so we keep a per-video cursor and only emit the tail.

Requires the optional dependency ``youtube-transcript-api``. If it is not
installed, the source disables itself with a clear log message instead of
crashing the agent.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import AsyncIterator, Dict, List

from ..models import Utterance
from .base import Source

log = logging.getLogger("stock_tracker.sources.youtube")

_ID_RE = re.compile(r"(?:v=|youtu\.be/|/live/|/embed/)([A-Za-z0-9_-]{11})")


def extract_video_id(url_or_id: str) -> str:
    m = _ID_RE.search(url_or_id)
    if m:
        return m.group(1)
    return url_or_id.strip()


class YouTubeLiveSource(Source):
    name = "youtube"

    def __init__(self, channels: List[str], poll_seconds: int = 20, languages=("en",)):
        self.video_ids = [extract_video_id(c) for c in channels]
        self.poll_seconds = poll_seconds
        self.languages = list(languages)
        self._cursor: Dict[str, float] = {}   # video_id -> last emitted caption start time

    def _available(self) -> bool:
        try:
            import youtube_transcript_api  # noqa: F401
            return True
        except Exception:
            log.warning(
                "youtube-transcript-api not installed; YouTube source disabled. "
                "Install with: pip install youtube-transcript-api"
            )
            return False

    def _fetch(self, video_id: str):
        from youtube_transcript_api import YouTubeTranscriptApi
        # Works for VODs and for the captions already produced on a live stream.
        return YouTubeTranscriptApi.get_transcript(video_id, languages=self.languages)

    async def stream(self) -> AsyncIterator[Utterance]:
        if not self.video_ids or not self._available():
            return

        while True:
            for vid in self.video_ids:
                try:
                    # network/blocking call -> run off the event loop
                    entries = await asyncio.to_thread(self._fetch, vid)
                except Exception as exc:  # transcript not ready / disabled / rate limited
                    log.debug("transcript fetch failed for %s: %s", vid, exc)
                    continue

                last = self._cursor.get(vid, -1.0)
                new = [e for e in entries if e.get("start", 0.0) > last]
                if not new:
                    continue
                self._cursor[vid] = max(e.get("start", 0.0) for e in new)

                # Coalesce a few caption fragments into one utterance for context.
                for chunk in _chunk(new, size=4):
                    text = " ".join(e["text"].replace("\n", " ") for e in chunk).strip()
                    if not text:
                        continue
                    yield Utterance(
                        text=text,
                        source=f"youtube:{vid}",
                        url=f"https://www.youtube.com/watch?v={vid}",
                        meta={"caption_start": chunk[0].get("start")},
                    )
            await asyncio.sleep(self.poll_seconds)


def _chunk(items: List[dict], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]
