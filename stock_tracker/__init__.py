"""
stock_tracker
=============

A live, agentic market-event tracker.

It listens to live information sources (CNBC / Yahoo Finance YouTube live
streams, the FOMC / economic calendar, crypto indices, generic websocket
feeds), runs a *bag-of-words* matcher over the text to detect when a market
mover (e.g. the Fed Chair, the President, a policy maker) mentions a theme,
maps that theme to the related stocks, and pushes an alert to Telegram /
WhatsApp.

Example
-------
    "Today Trump said about quantum stocks and cryptography ..."
        -> sector: Quantum Computing  (bullish)
        -> tickers: IONQ, RGTI, QBTS, QUBT, IBM
        -> alert sent to Telegram

The package is intentionally dependency-light: the core pipeline runs on the
standard library + PyYAML, and the live connectors (`youtube-transcript-api`,
`websockets`, Telegram/WhatsApp HTTP APIs) are optional and degrade
gracefully when not installed or not configured.
"""

from .models import Utterance, Signal, TickerHit, Direction

__all__ = ["Utterance", "Signal", "TickerHit", "Direction", "__version__"]

__version__ = "0.1.0"
