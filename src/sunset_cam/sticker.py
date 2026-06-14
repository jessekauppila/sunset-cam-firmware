"""Sticker generation for provisioned cameras.

Produces a PNG sticker containing:
  - A QR code encoding the permanent setup URL ({web_base}/setup/{claim_code})
  - The human-readable claim code printed below the QR

The sticker is meant to be affixed to the device enclosure so a phone can
scan it to reach the setup wizard for that specific camera.
"""
from __future__ import annotations

from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont


def setup_url(web_base: str, claim_code: str) -> str:
    """Return the stable per-camera setup URL for the given claim code.

    >>> setup_url("https://sunset.cam/", "SUNSET-AAAA-BBBB")
    'https://sunset.cam/setup/SUNSET-AAAA-BBBB'
    """
    return f"{web_base.rstrip('/')}/setup/{claim_code}"


def render_sticker(claim_code: str, web_base: str, out_path: str) -> None:
    """Render a PNG sticker with a QR code and human-readable claim code.

    Args:
        claim_code: The permanent claim code (e.g. "SUNSET-AAAA-BBBB").
        web_base:   The web frontend base URL (e.g. "https://sunset.cam").
        out_path:   Destination path for the generated PNG file.
    """
    url = setup_url(web_base, claim_code)

    # --- QR code ---
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # --- Text label below the QR ---
    qr_w, qr_h = qr_img.size
    label_height = 60
    canvas = Image.new("RGB", (qr_w, qr_h + label_height), color="white")
    canvas.paste(qr_img, (0, 0))

    draw = ImageDraw.Draw(canvas)
    try:
        # Use a monospace font if available on the system; fall back gracefully
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 20)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 20)
        except (IOError, OSError):
            font = ImageFont.load_default()

    # Centre the claim code text
    bbox = draw.textbbox((0, 0), claim_code, font=font)
    text_w = bbox[2] - bbox[0]
    text_x = max(0, (qr_w - text_w) // 2)
    text_y = qr_h + (label_height - (bbox[3] - bbox[1])) // 2
    draw.text((text_x, text_y), claim_code, fill="black", font=font)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="PNG")
