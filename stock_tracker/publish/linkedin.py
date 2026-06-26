"""LinkedIn publisher (text) via the UGC Posts API.

Posts the caption as a text share. Requires an OAuth access token with
``w_member_social`` and the author URN (``urn:li:person:...`` for a member, or
``urn:li:organization:...`` for a Company Page).
"""

from __future__ import annotations

import logging
from typing import Optional

from ..content.generator import Post
from ..models import Signal
from .base import Publisher

log = logging.getLogger("stock_tracker.publish.linkedin")

_URL = "https://api.linkedin.com/v2/ugcPosts"


class LinkedInPublisher(Publisher):
    name = "linkedin"

    def __init__(self, author_urn: str, access_token: str, http_post=None):
        self.author_urn = author_urn
        self.access_token = access_token
        self._http_post = http_post  # injectable for tests

    def _post(self, url, headers, json):
        if self._http_post is not None:
            return self._http_post(url, headers=headers, json=json)
        import requests

        return requests.post(url, headers=headers, json=json, timeout=30)

    def publish(self, signal: Signal, post: Post, image_path: Optional[str], image_url: Optional[str] = None) -> bool:
        body = {
            "author": self.author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": post.full_text()},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        try:
            resp = self._post(_URL, headers=headers, json=body)
        except Exception as exc:
            log.warning("linkedin post error: %s", exc)
            return False
        status = getattr(resp, "status_code", 0)
        if status and status >= 300:
            log.warning("linkedin post failed %s: %s", status, str(getattr(resp, "text", ""))[:200])
            return False
        log.info("posted to linkedin (%s)", self.author_urn)
        return True
