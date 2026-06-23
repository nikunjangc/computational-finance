"""Facebook Page publisher via the Graph API.

Posts a photo (with caption) to a Page you own, or a text/feed post when no
image is available. Requires a Page access token with `pages_manage_posts`.

Setup outline:
  1. Create a Meta app, add your Facebook Page.
  2. Get a Page access token (long-lived) with pages_manage_posts +
     pages_read_engagement -> FB_PAGE_ACCESS_TOKEN, FB_PAGE_ID.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..content.generator import Post
from ..models import Signal
from .base import Publisher

log = logging.getLogger("stock_tracker.publish.facebook")


class FacebookPagePublisher(Publisher):
    name = "facebook"

    def __init__(self, page_id: str, access_token: str, api_version: str = "v21.0", http_post=None):
        self.page_id = page_id
        self.access_token = access_token
        self.api_version = api_version
        self._http_post = http_post  # injectable for tests

    def _post(self, url, data=None, files=None):
        if self._http_post is not None:
            return self._http_post(url, data=data, files=files)
        import requests

        return requests.post(url, data=data, files=files, timeout=30)

    def publish(self, signal: Signal, post: Post, image_path: Optional[str]) -> bool:
        base = f"https://graph.facebook.com/{self.api_version}/{self.page_id}"
        caption = post.full_text()
        try:
            if image_path:
                with open(image_path, "rb") as fh:
                    resp = self._post(
                        f"{base}/photos",
                        data={"message": caption, "access_token": self.access_token},
                        files={"source": fh},
                    )
            else:
                resp = self._post(
                    f"{base}/feed",
                    data={"message": caption, "access_token": self.access_token},
                )
        except Exception as exc:
            log.warning("facebook post error: %s", exc)
            return False

        status = getattr(resp, "status_code", 0)
        if status and status >= 300:
            body = getattr(resp, "text", "")
            log.warning("facebook post failed %s: %s", status, str(body)[:200])
            return False
        log.info("posted to facebook page %s", self.page_id)
        return True
