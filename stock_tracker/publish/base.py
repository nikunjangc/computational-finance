"""Publisher abstraction — mirrors the notifier layer, but posts to socials."""

from __future__ import annotations

import abc
from typing import Optional

from ..content.generator import Post
from ..models import Signal


class Publisher(abc.ABC):
    name = "publisher"

    @abc.abstractmethod
    def publish(self, signal: Signal, post: Post, image_path: Optional[str]) -> bool:
        """Publish the post. Return True on success."""
