"""Instagram publisher via the Graph API Content Publishing API.

Instagram requires a **publicly reachable image URL** — unlike Facebook it does
not accept a file upload. Posting is a two-step flow:

  1. POST /{ig_user_id}/media        (image_url + caption)  -> creation_id
  2. POST /{ig_user_id}/media_publish (creation_id)         -> published

Setup outline:
  * Instagram **Business/Creator** account linked to a Facebook Page.
  * Meta app with `instagram_content_publish` (+ `pages_show_list`).
  * IG_USER_ID = the IG business account id; IG_ACCESS_TOKEN = a token with the
    above scopes (often the same long-lived Page token).
  * The image card must be served at a public HTTPS URL — set
    IMAGE_PUBLIC_BASE_URL and IMAGE_OUTPUT_DIR so cards land somewhere served.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..content.generator import Post
from ..models import Signal
from .base import Publisher

log = logging.getLogger("stock_tracker.publish.instagram")


class InstagramPublisher(Publisher):
    name = "instagram"

    def __init__(self, ig_user_id: str, access_token: str, api_version: str = "v21.0", http_post=None):
        self.ig_user_id = ig_user_id
        self.access_token = access_token
        self.api_version = api_version
        self._http_post = http_post  # injectable for tests

    def _post(self, url, data=None):
        if self._http_post is not None:
            return self._http_post(url, data=data)
        import requests

        return requests.post(url, data=data, timeout=30)

    def publish(self, signal: Signal, post: Post, image_path: Optional[str], image_url: Optional[str] = None) -> bool:
        if not image_url:
            log.warning(
                "Instagram needs a public image URL (set IMAGE_PUBLIC_BASE_URL so the "
                "card is reachable); skipping IG post for %s", signal.sector
            )
            return False

        base = f"https://graph.facebook.com/{self.api_version}/{self.ig_user_id}"
        try:
            create = self._post(
                f"{base}/media",
                data={"image_url": image_url, "caption": post.full_text(), "access_token": self.access_token},
            )
            if not _ok(create):
                log.warning("instagram media create failed %s: %s", _status(create), _text(create))
                return False
            creation_id = create.json().get("id")
            if not creation_id:
                log.warning("instagram media create returned no id: %s", _text(create))
                return False

            publish = self._post(
                f"{base}/media_publish",
                data={"creation_id": creation_id, "access_token": self.access_token},
            )
            if not _ok(publish):
                log.warning("instagram media_publish failed %s: %s", _status(publish), _text(publish))
                return False
        except Exception as exc:
            log.warning("instagram post error: %s", exc)
            return False

        log.info("posted to instagram %s", self.ig_user_id)
        return True


def _status(resp) -> int:
    return getattr(resp, "status_code", 0)


def _ok(resp) -> bool:
    s = _status(resp)
    return not (s and s >= 300)


def _text(resp) -> str:
    return str(getattr(resp, "text", ""))[:200]
