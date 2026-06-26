"""Console notifier – always available, used for demo and as a fallback."""

from __future__ import annotations

from ..models import Signal
from .base import Notifier, format_alert


class ConsoleNotifier(Notifier):
    name = "console"

    def send(self, signal: Signal) -> bool:
        print("\n" + "=" * 60)
        print(format_alert(signal, markdown=False))
        print("=" * 60, flush=True)
        return True
