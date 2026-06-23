"""Render a simple branded image card for a Signal (optional, needs Pillow).

Returns a PNG path, or None if Pillow isn't installed — in which case the
publisher posts text-only.
"""

from __future__ import annotations

import logging
import os
import tempfile

from ..models import Direction, Signal

log = logging.getLogger("stock_tracker.content.image")

_BG = {
    Direction.BULLISH: (16, 99, 65),    # green
    Direction.BEARISH: (140, 26, 26),   # red
    Direction.NEUTRAL: (55, 60, 70),     # slate
}


def render_card(signal: Signal, out_dir: str | None = None) -> str | None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        log.info("Pillow not installed; posting text-only. pip install pillow")
        return None

    W, H = 1080, 1080
    bg = _BG.get(signal.direction, _BG[Direction.NEUTRAL])
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    def font(size: int):
        for path in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ):
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        return ImageFont.load_default()

    arrow = {"bullish": "▲", "bearish": "▼", "neutral": "●"}[signal.direction.value]
    d.text((60, 60), f"{arrow}  {signal.direction.value.upper()}", font=font(70), fill="white")
    d.text((60, 180), signal.sector, font=font(58), fill="white")

    # Quote (wrapped)
    quote = signal.utterance.short(160)
    y = 320
    line, fnt = "", font(40)
    for word in quote.split():
        trial = (line + " " + word).strip()
        if d.textlength(trial, font=fnt) > W - 120:
            d.text((60, y), line, font=fnt, fill=(235, 235, 235))
            y += 52
            line = word
        else:
            line = trial
    if line:
        d.text((60, y), line, font=fnt, fill=(235, 235, 235))

    tickers = "  ".join("$" + s for s in signal.symbols[:6])
    d.text((60, H - 230), tickers, font=font(52), fill="white")
    speaker = (signal.utterance.speaker or "Markets")[:40]
    d.text((60, H - 130), f"{speaker} • {signal.utterance.source}", font=font(32), fill=(210, 210, 210))
    d.text((60, H - 70), "Not financial advice", font=font(28), fill=(200, 200, 200))

    out_dir = out_dir or tempfile.gettempdir()
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"post_{signal.fingerprint()}.png")
    img.save(path, "PNG")
    return path
