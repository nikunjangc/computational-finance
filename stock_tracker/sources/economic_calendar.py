"""Scheduled-event source: FOMC / Fed calendar and other policy events.

This is the "scheduled meeting" path the user asked for. It emits a heads-up
Utterance shortly before each known event so the agent can pre-position and
remind you, then it is ready for the live feed to carry the actual remarks.

The FOMC dates below are seeded statically (editable); a production build can
replace ``_load_events`` with a live pull from an economic-calendar API.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, List, Tuple

from ..models import Utterance
from .base import Source

log = logging.getLogger("stock_tracker.sources.calendar")

# (ISO datetime UTC, event label). FOMC statement releases are ~18:00 UTC.
_FOMC_2026: List[Tuple[str, str]] = [
    ("2026-01-28T19:00:00+00:00", "FOMC rate decision (Jan)"),
    ("2026-03-18T18:00:00+00:00", "FOMC rate decision + projections (Mar)"),
    ("2026-04-29T18:00:00+00:00", "FOMC rate decision (Apr)"),
    ("2026-06-17T18:00:00+00:00", "FOMC rate decision + projections (Jun)"),
    ("2026-07-29T18:00:00+00:00", "FOMC rate decision (Jul)"),
    ("2026-09-16T18:00:00+00:00", "FOMC rate decision + projections (Sep)"),
    ("2026-11-04T19:00:00+00:00", "FOMC rate decision (Nov)"),
    ("2026-12-16T19:00:00+00:00", "FOMC rate decision + projections (Dec)"),
]


class EconomicCalendarSource(Source):
    name = "calendar"

    def __init__(self, lead_minutes: int = 30, check_seconds: int = 60, fire_past_on_start: bool = False):
        self.lead = timedelta(minutes=lead_minutes)
        self.check_seconds = check_seconds
        self.fire_past_on_start = fire_past_on_start
        self._fired: set[str] = set()

    def _load_events(self) -> List[Tuple[datetime, str]]:
        out = []
        for iso, label in _FOMC_2026:
            out.append((datetime.fromisoformat(iso), label))
        return out

    async def stream(self) -> AsyncIterator[Utterance]:
        events = self._load_events()
        while True:
            now = datetime.now(timezone.utc)
            for when, label in events:
                key = when.isoformat()
                if key in self._fired:
                    continue
                window_open = when - self.lead
                # Fire once we enter the lead-up window (and not absurdly late).
                if window_open <= now <= when + timedelta(hours=2):
                    self._fired.add(key)
                    mins = max(0, int((when - now).total_seconds() // 60))
                    yield Utterance(
                        text=(
                            f"Upcoming policy event: {label} at {when:%Y-%m-%d %H:%M UTC} "
                            f"(in ~{mins} min). Watch for the federal funds rate decision, "
                            f"any rate cut or rate hike, and the monetary policy guidance."
                        ),
                        source="calendar:FOMC",
                        speaker="Economic Calendar",
                        meta={"event": label, "event_time": key},
                    )
                elif self.fire_past_on_start and now > when + timedelta(hours=2):
                    # Avoid re-firing long-past events on every restart.
                    self._fired.add(key)
            await asyncio.sleep(self.check_seconds)
