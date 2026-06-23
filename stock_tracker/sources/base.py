"""Source abstraction.

A Source is an async generator of :class:`Utterance`. The agent runs every
source concurrently and feeds whatever they yield into the signal engine.
This uniform interface is what lets "scheduled" sources (economic calendar)
and "push" sources (websocket / live captions) coexist.
"""

from __future__ import annotations

import abc
import logging
from typing import AsyncIterator

from ..models import Utterance

log = logging.getLogger("stock_tracker.sources")


class Source(abc.ABC):
    name: str = "source"

    @abc.abstractmethod
    async def stream(self) -> AsyncIterator[Utterance]:
        """Yield Utterance objects as live information arrives."""
        raise NotImplementedError
        yield  # pragma: no cover  (makes this an async generator for typing)
