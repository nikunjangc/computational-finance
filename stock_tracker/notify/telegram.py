"""Telegram notifier via the Bot API (no extra dependency beyond requests).

Setup:
  1. Talk to @BotFather, create a bot, copy the token -> TELEGRAM_BOT_TOKEN.
  2. Send your bot a message, then read your chat id from
     https://api.telegram.org/bot<token>/getUpdates -> TELEGRAM_CHAT_ID.
"""

from __future__ import annotations

import logging

from ..models import Signal
from .base import Notifier, format_alert

log = logging.getLogger("stock_tracker.notify.telegram")


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    """Send a plain text message to Telegram (used for post confirmations)."""
    import requests

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
        return resp.status_code == 200
    except Exception as exc:
        log.warning("telegram message error: %s", exc)
        return False


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, signal: Signal) -> bool:
        import requests
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": format_alert(signal),
            "disable_web_page_preview": False,
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code != 200:
                log.warning("telegram send failed %s: %s", resp.status_code, resp.text[:200])
                return False
            return True
        except Exception as exc:
            log.warning("telegram send error: %s", exc)
            return False
