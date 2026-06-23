"""Configuration, loaded from environment variables (12-factor style).

Nothing here is secret in the repo – real secrets live in the environment
(or a local ``.env`` that is git-ignored). Copy ``.env.example`` to ``.env``
and fill in the values you have; missing ones simply disable that connector.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional


def _split(val: Optional[str]) -> List[str]:
    if not val:
        return []
    return [v.strip() for v in val.replace("\n", ",").split(",") if v.strip()]


@dataclass
class Config:
    # --- notifications ---
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    whatsapp_provider: str = "twilio"          # twilio | meta
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_from: Optional[str] = None          # e.g. "whatsapp:+14155238886"
    whatsapp_to: Optional[str] = None          # e.g. "whatsapp:+1..."
    meta_wa_token: Optional[str] = None
    meta_wa_phone_id: Optional[str] = None

    # --- sources ---
    youtube_channels: List[str] = field(default_factory=list)   # video/live IDs or URLs
    youtube_api_key: Optional[str] = None
    crypto_symbols: List[str] = field(default_factory=lambda: ["bitcoin", "ethereum"])
    crypto_move_pct: float = 3.0                # alert when |24h move| exceeds this
    websocket_urls: List[str] = field(default_factory=list)

    # --- engine ---
    min_confidence: float = 0.45
    poll_seconds: int = 20

    # --- optional LLM classifier (budget-capped) ---
    anthropic_api_key: Optional[str] = None
    llm_enabled: bool = False
    llm_model: str = "claude-haiku-4-5"
    llm_monthly_budget: float = 1.0          # USD; falls back to free mode when hit
    llm_state_path: str = ".stock_tracker_llm_spend.json"

    # --- social auto-posting ---
    publish_enabled: bool = False
    publish_dry_run: bool = True             # safety: preview unless explicitly off
    publish_min_confidence: float = 0.7      # only post strong signals
    post_image: bool = True
    post_disclaimer: str = "Educational only — not financial advice. Do your own research."
    fb_page_id: Optional[str] = None
    fb_page_token: Optional[str] = None

    # --- multi-instance coordination (primary + failover) ---
    instance_id: Optional[str] = None
    tracker_role: str = "primary"          # primary | standby (role-based mode)
    redis_url: Optional[str] = None        # set => automatic leader+dedup mode
    lease_ttl: int = 30                    # seconds; standby promotes within this
    dedup_window: int = 900                # seconds an event stays de-duped

    @classmethod
    def from_env(cls) -> "Config":
        env = os.environ.get
        return cls(
            telegram_bot_token=env("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=env("TELEGRAM_CHAT_ID"),
            whatsapp_provider=env("WHATSAPP_PROVIDER", "twilio"),
            twilio_account_sid=env("TWILIO_ACCOUNT_SID"),
            twilio_auth_token=env("TWILIO_AUTH_TOKEN"),
            twilio_from=env("TWILIO_WHATSAPP_FROM"),
            whatsapp_to=env("WHATSAPP_TO"),
            meta_wa_token=env("META_WA_TOKEN"),
            meta_wa_phone_id=env("META_WA_PHONE_ID"),
            youtube_channels=_split(env("YOUTUBE_CHANNELS")),
            youtube_api_key=env("YOUTUBE_API_KEY"),
            crypto_symbols=_split(env("CRYPTO_SYMBOLS")) or ["bitcoin", "ethereum"],
            crypto_move_pct=float(env("CRYPTO_MOVE_PCT", "3.0")),
            websocket_urls=_split(env("WEBSOCKET_URLS")),
            min_confidence=float(env("MIN_CONFIDENCE", "0.45")),
            poll_seconds=int(env("POLL_SECONDS", "20")),
            instance_id=env("INSTANCE_ID"),
            tracker_role=env("TRACKER_ROLE", "primary"),
            redis_url=env("REDIS_URL"),
            lease_ttl=int(env("LEASE_TTL", "30")),
            dedup_window=int(env("DEDUP_WINDOW", "900")),
            anthropic_api_key=env("ANTHROPIC_API_KEY"),
            llm_enabled=env("LLM_ENABLED", "false").lower() in ("1", "true", "yes"),
            llm_model=env("LLM_MODEL", "claude-haiku-4-5"),
            llm_monthly_budget=float(env("LLM_MONTHLY_BUDGET_USD", "1.0")),
            llm_state_path=env("LLM_STATE_PATH", ".stock_tracker_llm_spend.json"),
            publish_enabled=env("PUBLISH_ENABLED", "false").lower() in ("1", "true", "yes"),
            publish_dry_run=env("PUBLISH_DRY_RUN", "true").lower() in ("1", "true", "yes"),
            publish_min_confidence=float(env("PUBLISH_MIN_CONFIDENCE", "0.7")),
            post_image=env("POST_IMAGE", "true").lower() in ("1", "true", "yes"),
            post_disclaimer=env("POST_DISCLAIMER", "Educational only — not financial advice. Do your own research."),
            fb_page_id=env("FB_PAGE_ID"),
            fb_page_token=env("FB_PAGE_ACCESS_TOKEN"),
        )
