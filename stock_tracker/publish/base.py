"""Publisher abstraction — mirrors the notifier layer, but posts to socials."""

from __future__ import annotations

import abc
from typing import Optional

from ..content.generator import Post
from ..models import Signal


class Publisher(abc.ABC):
    name = "publisher"

    @abc.abstractmethod
    def publish(self, signal: Signal, post: Post, image_path: Optional[str], image_url: Optional[str] = None) -> bool:
        """Publish the post. Return True on success.

        image_path: local file (used by Facebook multipart upload).
        image_url:  public HTTPS URL of the same image (required by Instagram,
                    which fetches media rather than accepting an upload).
        """
