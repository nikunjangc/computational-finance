"""Turns a fired Signal into posts and pushes them to the social publishers.

Gated by a (higher) confidence threshold so only strong signals get posted.
Generates copy via ContentGenerator (LLM or free template) and an optional
image card, then fans out to each enabled Publisher.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ..content.generator import ContentGenerator
from ..content.image_card import render_card
from ..models import Signal
from .base import Publisher
from .console import ConsolePublisher
from .facebook import FacebookPagePublisher

log = logging.getLogger("stock_tracker.publish")


class SocialPublisher:
    def __init__(
        self,
        generator: ContentGenerator,
        publishers: List[Publisher],
        min_confidence: float = 0.7,
        with_image: bool = True,
    ):
        self.generator = generator
        self.publishers = publishers
        self.min_confidence = min_confidence
        self.with_image = with_image
        self.posted = 0

    def publish(self, signal: Signal) -> bool:
        if signal.confidence < self.min_confidence:
            log.debug("below post threshold (%.2f < %.2f): %s", signal.confidence, self.min_confidence, signal.sector)
            return False
        post = self.generator.generate(signal, platform="facebook")
        image = render_card(signal) if self.with_image else None
        ok_any = False
        for pub in self.publishers:
            try:
                if pub.publish(signal, post, image):
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
    live = cfg.fb_page_id and cfg.fb_page_token and not cfg.publish_dry_run
    if live:
        publishers.append(FacebookPagePublisher(cfg.fb_page_id, cfg.fb_page_token))
        log.info("facebook publisher LIVE (page %s)", cfg.fb_page_id)
    else:
        publishers.append(ConsolePublisher())
        reason = "PUBLISH_DRY_RUN=true" if cfg.publish_dry_run else "no FB_PAGE_ID/FB_PAGE_ACCESS_TOKEN"
        log.info("social publishing in DRY-RUN (%s)", reason)

    return SocialPublisher(
        generator,
        publishers,
        min_confidence=cfg.publish_min_confidence,
        with_image=cfg.post_image,
    )
