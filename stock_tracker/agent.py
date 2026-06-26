"""The agentic orchestrator.

Runs every configured source concurrently, pushes each captured utterance
through the signal engine, de-duplicates, and dispatches qualifying signals
to the notifiers. This is the "live agentic mode" – when a relevant event
happens (a Fed remark, a presidential comment on quantum, a crypto move) it
fires an alert with the related stocks.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Optional

from .config import Config
from .coordination import Coordinator
from .knowledge_base import KnowledgeBase
from .models import Signal, Utterance
from .notify.dispatcher import Dispatcher, build_notifiers
from .signals.engine import SignalEngine
from .sources.base import Source

log = logging.getLogger("stock_tracker.agent")


class Agent:
    def __init__(
        self,
        sources: List[Source],
        engine: Optional[SignalEngine] = None,
        dispatcher: Optional[Dispatcher] = None,
        coordinator: Optional[Coordinator] = None,
        publisher=None,
        dedup_seconds: int = 600,
    ):
        self.sources = sources
        self.engine = engine or SignalEngine()
        self.dispatcher = dispatcher or Dispatcher(build_notifiers(Config.from_env()))
        self.coordinator = coordinator
        self.publisher = publisher  # optional SocialPublisher
        self.dedup_seconds = dedup_seconds
        self._recent: dict[str, float] = {}
        self.processed = 0
        self.alerts = 0
        self.suppressed = 0

    # ------------------------------------------------------------------
    def _is_duplicate(self, signal: Signal) -> bool:
        # Key on sector + direction + speaker so the same theme from the same
        # speaker doesn't spam, but a new direction or speaker still alerts.
        key = f"{signal.sector_key}|{signal.direction.value}|{signal.utterance.speaker}"
        now = time.time()
        last = self._recent.get(key)
        self._recent[key] = now
        return last is not None and (now - last) < self.dedup_seconds

    def handle(self, utterance: Utterance) -> List[Signal]:
        """Process one utterance; dispatch and return the signals it fired."""
        self.processed += 1
        fired: List[Signal] = []
        for signal in self.engine.process(utterance):
            if self._is_duplicate(signal):
                log.debug("suppressed local duplicate: %s", signal.sector)
                continue
            # Cross-instance guard: only the active/leader instance (and only
            # once per event) actually sends. Standby instances stay silent.
            if self.coordinator is not None and not self.coordinator.claim(signal):
                self.suppressed += 1
                log.debug("suppressed by coordinator (role=%s): %s", self.coordinator.role(), signal.sector)
                continue
            self.dispatcher.dispatch(signal)
            self.alerts += 1
            fired.append(signal)
            # Auto-post strong signals to social (gated inside the publisher).
            if self.publisher is not None:
                try:
                    self.publisher.publish(signal)
                except Exception as exc:
                    log.warning("publisher raised: %s", exc)
        return fired

    # ------------------------------------------------------------------
    async def _run_source(self, source: Source):
        try:
            async for utterance in source.stream():
                # engine + notifiers are sync/blocking-ish; offload to a thread
                await asyncio.to_thread(self.handle, utterance)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("source %s crashed: %s", getattr(source, "name", source), exc)

    async def _heartbeat(self, seconds: int):
        while True:
            await asyncio.sleep(seconds)
            log.info("heartbeat: alive | processed=%d alerts=%d", self.processed, self.alerts)

    async def run(self, heartbeat_seconds: int = 0) -> None:
        if not self.sources:
            log.warning("no sources configured; nothing to do")
            return
        log.info("agent starting with %d source(s)", len(self.sources))
        tasks = [asyncio.create_task(self._run_source(s)) for s in self.sources]
        if heartbeat_seconds > 0:
            tasks.append(asyncio.create_task(self._heartbeat(heartbeat_seconds)))
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            log.info("agent cancelled; shutting down")
        finally:
            for t in tasks:
                t.cancel()
        log.info("agent finished: processed=%d alerts=%d", self.processed, self.alerts)


def build_default_sources(cfg: Config) -> List[Source]:
    """Wire up real sources based on whatever is configured in the environment."""
    from .sources.crypto_index import CryptoIndexSource
    from .sources.economic_calendar import EconomicCalendarSource
    from .sources.websocket_feed import WebSocketFeedSource
    from .sources.youtube_live import YouTubeLiveSource

    sources: List[Source] = [EconomicCalendarSource()]
    if cfg.youtube_channels:
        sources.append(YouTubeLiveSource(cfg.youtube_channels, poll_seconds=cfg.poll_seconds))
    if cfg.crypto_symbols:
        sources.append(CryptoIndexSource(cfg.crypto_symbols, cfg.crypto_move_pct, cfg.poll_seconds))
    if cfg.websocket_urls:
        sources.append(WebSocketFeedSource(cfg.websocket_urls))
    return sources
