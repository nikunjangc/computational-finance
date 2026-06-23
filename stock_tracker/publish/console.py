"""Dry-run publisher — prints exactly what would be posted. Always available."""

from __future__ import annotations

from typing import Optional

from ..content.generator import Post
from ..models import Signal
from .base import Publisher


class ConsolePublisher(Publisher):
    name = "console"

    def publish(self, signal: Signal, post: Post, image_path: Optional[str], image_url: Optional[str] = None) -> bool:
        print("\n" + "#" * 60)
        print("[DRY-RUN] would post to social:")
        print(post.full_text())
        print(f"image: {image_path or '(none — text only)'}")
        if image_url:
            print(f"image_url: {image_url}")
        print("#" * 60, flush=True)
        return True
