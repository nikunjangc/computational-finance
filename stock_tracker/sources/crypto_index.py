"""Crypto-index poller (the "coin index" path).

Polls a public price API (CoinGecko, no key required) and emits an Utterance
whenever a tracked coin's 24h move exceeds a threshold. The emitted text is
written so the bag-of-words engine routes it to the crypto sector.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Dict, List

from ..models import Utterance
from .base import Source

log = logging.getLogger("stock_tracker.sources.crypto")

_API = "https://api.coingecko.com/api/v3/simple/price"


class CryptoIndexSource(Source):
    name = "crypto"

    def __init__(self, coins: List[str], move_pct: float = 3.0, poll_seconds: int = 60):
        self.coins = coins
        self.move_pct = move_pct
        self.poll_seconds = poll_seconds
        self._last_alert: Dict[str, float] = {}

    def _fetch(self) -> Dict[str, dict]:
        import requests
        params = {
            "ids": ",".join(self.coins),
            "vs_currencies": "usd",
            "include_24hr_change": "true",
        }
        resp = requests.get(_API, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    async def stream(self) -> AsyncIterator[Utterance]:
        if not self.coins:
            return
        while True:
            try:
                data = await asyncio.to_thread(self._fetch)
            except Exception as exc:
                log.debug("crypto fetch failed: %s", exc)
                await asyncio.sleep(self.poll_seconds)
                continue

            for coin, body in data.items():
                change = float(body.get("usd_24h_change", 0.0))
                price = body.get("usd")
                if abs(change) < self.move_pct:
                    continue
                # De-dupe: only re-alert if the move grew meaningfully.
                if abs(change) <= abs(self._last_alert.get(coin, 0.0)) + 1.0:
                    continue
                self._last_alert[coin] = change
                word = "surged" if change > 0 else "dropped"
                yield Utterance(
                    text=(
                        f"Crypto move: {coin.title()} (a digital asset / cryptocurrency) "
                        f"{word} {change:+.1f}% in 24h to ${price}. Bitcoin and the broader "
                        f"blockchain / crypto complex are on the move."
                    ),
                    source="crypto:coingecko",
                    speaker="Market",
                    meta={"coin": coin, "change_24h": change, "price": price},
                )
            await asyncio.sleep(self.poll_seconds)
