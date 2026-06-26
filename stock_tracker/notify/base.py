"""Notifier abstraction + shared alert formatting."""

from __future__ import annotations

import abc

from ..models import Signal


def format_alert(signal: Signal, markdown: bool = True) -> str:
    u = signal.utterance
    tickers = ", ".join(signal.symbols) if signal.symbols else "—"
    speaker = u.speaker or "Unknown"
    conf = f"{signal.confidence * 100:.0f}%"
    head = f"{signal.direction.emoji} {signal.direction.value.upper()} • {signal.sector}"
    body = (
        f"{head}\n"
        f"Speaker: {speaker}\n"
        f"Source: {u.source}\n"
        f"Keywords: {', '.join(signal.matched_keywords)}\n"
        f"Tickers: {tickers}\n"
        f"Confidence: {conf}\n"
        f"\n“{u.short(280)}”"
    )
    if u.url:
        body += f"\n{u.url}"
    return body


class Notifier(abc.ABC):
    name = "notifier"
    enabled = True

    @abc.abstractmethod
    def send(self, signal: Signal) -> bool:
        """Send the alert. Return True on success."""
        raise NotImplementedError
