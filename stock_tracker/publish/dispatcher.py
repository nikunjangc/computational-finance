"""Turns a fired Signal into posts and pushes them to the social publishers.

Gated by a (higher) confidence threshold so only strong signals get posted.
Generates copy via ContentGenerator (LLM or free template) and an optional
image card, then fans out to each enabled Publisher.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from ..content.generator import ContentGenerator
from ..content.image_card import render_card
from ..models import Signal
from .base import Publisher
from .console import ConsolePublisher
from .facebook import FacebookPagePublisher
from .instagram import InstagramPublisher

log = logging.getLogger("stock_tracker.publish")


class SocialPublisher:
    def __init__(
        self,
        generator: ContentGenerator,
        publishers: List[Publisher],
        min_confidence: float = 0.7,
        with_image: bool = True,
        image_output_dir: Optional[str] = None,
        image_public_base: Optional[str] = None,
    ):
        self.generator = generator
        self.publishers = publishers
        self.min_confidence = min_confidence
        self.with_image = with_image
        self.image_output_dir = image_output_dir
        self.image_public_base = image_public_base
        self.posted = 0

    def publish(self, signal: Signal) -> bool:
        if signal.confidence < self.min_confidence:
            log.debug("below post threshold (%.2f < %.2f): %s", signal.confidence, self.min_confidence, signal.sector)
            return False
        post = self.generator.generate(signal, platform="facebook")
        image = render_card(signal, out_dir=self.image_output_dir) if self.with_image else None
        # Public URL of the same card (Instagram fetches by URL; FB uses the file).
        image_url = None
        if image and self.image_public_base:
            image_url = self.image_public_base.rstrip("/") + "/" + os.path.basename(image)
        ok_any = False
        for pub in self.publishers:
            try:
                if pub.publish(signal, post, image, image_url):
                    ok_any = True
            except Exception as exc:
                log.warning("publisher %s raised: %s", pub.name, exc)
        if ok_any:
            self.posted += 1
        return ok_any


def build_publisher(cfg) -> Optional[SocialPublisher]:
    if not cfg.publish_enabled:
        return None

    # Shared budget with the classifier so total LLM spend stays capped.
    tracker = None
    if cfg.anthropic_api_key:
        from ..nlp.llm_classifier import CostTracker

        tracker = CostTracker(cfg.llm_state_path, cfg.llm_monthly_budget)
    generator = ContentGenerator(
        api_key=cfg.anthropic_api_key,
        model=cfg.llm_model,
        tracker=tracker,
        disclaimer=cfg.post_disclaimer,
    )

    publishers: List[Publisher] = []
    if not cfg.publish_dry_run:
        if cfg.fb_page_id and cfg.fb_page_token:
            publishers.append(FacebookPagePublisher(cfg.fb_page_id, cfg.fb_page_token))
            log.info("facebook publisher LIVE (page %s)", cfg.fb_page_id)
        ig_token = cfg.ig_access_token or cfg.fb_page_token
        if cfg.ig_user_id and ig_token:
            publishers.append(InstagramPublisher(cfg.ig_user_id, ig_token))
            log.info("instagram publisher LIVE (user %s)", cfg.ig_user_id)
            if not cfg.image_public_base:
                log.warning("instagram is live but IMAGE_PUBLIC_BASE_URL is unset — IG image posts will be skipped")

    if not publishers:
        publishers.append(ConsolePublisher())
        reason = "PUBLISH_DRY_RUN=true" if cfg.publish_dry_run else "no FB/IG credentials"
        log.info("social publishing in DRY-RUN (%s)", reason)

    return SocialPublisher(
        generator,
        publishers,
        min_confidence=cfg.publish_min_confidence,
        with_image=cfg.post_image,
        image_output_dir=cfg.image_output_dir,
        image_public_base=cfg.image_public_base,
    )
