"""WhatsApp notifier.

Two providers are supported:
  * twilio – uses the Twilio WhatsApp API (easiest sandbox to start with).
  * meta   – uses the Meta/WhatsApp Cloud API.

Only ``requests`` is required. Configure via environment (see config.py).
"""

from __future__ import annotations

import logging

from ..models import Signal
from .base import Notifier, format_alert

log = logging.getLogger("stock_tracker.notify.whatsapp")


class TwilioWhatsAppNotifier(Notifier):
    name = "whatsapp:twilio"

    def __init__(self, account_sid: str, auth_token: str, from_: str, to: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_ = from_      # e.g. "whatsapp:+14155238886"
        self.to = to            # e.g. "whatsapp:+1..."

    def send(self, signal: Signal) -> bool:
        import requests
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        data = {"From": self.from_, "To": self.to, "Body": format_alert(signal)}
        try:
            resp = requests.post(url, data=data, auth=(self.account_sid, self.auth_token), timeout=15)
            if resp.status_code >= 300:
                log.warning("twilio send failed %s: %s", resp.status_code, resp.text[:200])
                return False
            return True
        except Exception as exc:
            log.warning("twilio send error: %s", exc)
            return False


class MetaWhatsAppNotifier(Notifier):
    name = "whatsapp:meta"

    def __init__(self, token: str, phone_id: str, to: str):
        self.token = token
        self.phone_id = phone_id
        self.to = to.replace("whatsapp:", "").lstrip("+")

    def send(self, signal: Signal) -> bool:
        import requests
        url = f"https://graph.facebook.com/v20.0/{self.phone_id}/messages"
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {
            "messaging_product": "whatsapp",
            "to": self.to,
            "type": "text",
            "text": {"body": format_alert(signal)},
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code >= 300:
                log.warning("meta wa send failed %s: %s", resp.status_code, resp.text[:200])
                return False
            return True
        except Exception as exc:
            log.warning("meta wa send error: %s", exc)
            return False
