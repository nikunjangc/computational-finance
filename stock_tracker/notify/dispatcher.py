"""Builds the active notifiers from config and fans alerts out to all of them."""

from __future__ import annotations

import logging
from typing import List

from ..config import Config
from ..models import Signal
from .base import Notifier
from .console import ConsoleNotifier
from .telegram import TelegramNotifier
from .whatsapp import MetaWhatsAppNotifier, TwilioWhatsAppNotifier

log = logging.getLogger("stock_tracker.notify")


def build_notifiers(cfg: Config, include_console: bool = True) -> List[Notifier]:
    notifiers: List[Notifier] = []

    if cfg.telegram_bot_token and cfg.telegram_chat_id:
        notifiers.append(TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id))
        log.info("telegram notifier enabled")

    if cfg.whatsapp_provider == "twilio" and all(
        [cfg.twilio_account_sid, cfg.twilio_auth_token, cfg.twilio_from, cfg.whatsapp_to]
    ):
        notifiers.append(
            TwilioWhatsAppNotifier(cfg.twilio_account_sid, cfg.twilio_auth_token, cfg.twilio_from, cfg.whatsapp_to)
        )
        log.info("whatsapp (twilio) notifier enabled")
    elif cfg.whatsapp_provider == "meta" and all([cfg.meta_wa_token, cfg.meta_wa_phone_id, cfg.whatsapp_to]):
        notifiers.append(MetaWhatsAppNotifier(cfg.meta_wa_token, cfg.meta_wa_phone_id, cfg.whatsapp_to))
        log.info("whatsapp (meta) notifier enabled")

    if include_console or not notifiers:
        notifiers.append(ConsoleNotifier())

    return notifiers


class Dispatcher:
    def __init__(self, notifiers: List[Notifier]):
        self.notifiers = notifiers

    def dispatch(self, signal: Signal) -> None:
        for n in self.notifiers:
            try:
                ok = n.send(signal)
                if not ok:
                    log.warning("notifier %s reported failure", n.name)
            except Exception as exc:
                log.warning("notifier %s raised: %s", n.name, exc)
