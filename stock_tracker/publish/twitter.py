"""X / Twitter publisher (text) via API v2 with OAuth 1.0a user-context signing.

Posts the caption as a tweet (text only — image upload on X is a separate v1.1
flow). Requires the four user-context credentials from a developer app with
*write* access: API key/secret + access token/secret.

Only the standard library is used for OAuth 1.0a signing (no extra deps). The
JSON body is not part of the OAuth signature base string (X v2 sends JSON, not
form-encoded params), so signing the oauth_* params is sufficient.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time
from typing import Optional
from urllib.parse import quote

from ..content.generator import Post
from ..models import Signal
from .base import Publisher

log = logging.getLogger("stock_tracker.publish.twitter")

_URL = "https://api.twitter.com/2/tweets"
_LIMIT = 280


def tweet_text(post: Post) -> str:
    text = post.caption.strip()
    tags = " ".join("#" + h.lstrip("#") for h in post.hashtags)
    if tags and len(text) + 1 + len(tags) <= _LIMIT:
        text = f"{text}\n{tags}"
    if len(text) > _LIMIT:
        text = text[: _LIMIT - 1].rstrip() + "…"
    return text


def _quote(s: str) -> str:
    return quote(str(s), safe="")


class TwitterPublisher(Publisher):
    name = "twitter"

    def __init__(self, api_key, api_secret, access_token, access_secret, http_post=None, _nonce=None, _ts=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.access_secret = access_secret
        self._http_post = http_post  # injectable for tests
        self._nonce = _nonce
        self._ts = _ts

    def _auth_header(self, method: str, url: str) -> str:
        oauth = {
            "oauth_consumer_key": self.api_key,
            "oauth_nonce": self._nonce or base64.b64encode(os.urandom(16)).decode().strip("="),
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(self._ts or int(time.time())),
            "oauth_token": self.access_token,
            "oauth_version": "1.0",
        }
        param_str = "&".join(f"{_quote(k)}={_quote(oauth[k])}" for k in sorted(oauth))
        base = "&".join([method.upper(), _quote(url), _quote(param_str)])
        signing_key = f"{_quote(self.api_secret)}&{_quote(self.access_secret)}"
        sig = base64.b64encode(hmac.new(signing_key.encode(), base.encode(), hashlib.sha1).digest()).decode()
        oauth["oauth_signature"] = sig
        return "OAuth " + ", ".join(f'{_quote(k)}="{_quote(v)}"' for k, v in sorted(oauth.items()))

    def _post(self, url, headers, json):
        if self._http_post is not None:
            return self._http_post(url, headers=headers, json=json)
        import requests

        return requests.post(url, headers=headers, json=json, timeout=30)

    def publish(self, signal: Signal, post: Post, image_path: Optional[str], image_url: Optional[str] = None) -> bool:
        headers = {"Authorization": self._auth_header("POST", _URL), "Content-Type": "application/json"}
        try:
            resp = self._post(_URL, headers=headers, json={"text": tweet_text(post)})
        except Exception as exc:
            log.warning("twitter post error: %s", exc)
            return False
        status = getattr(resp, "status_code", 0)
        if status and status >= 300:
            log.warning("twitter post failed %s: %s", status, str(getattr(resp, "text", ""))[:200])
            return False
        log.info("posted to X/twitter")
        return True
