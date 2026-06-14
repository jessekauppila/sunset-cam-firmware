"""Sticker generation for provisioned cameras.

Produces a PNG sticker containing:
  - A QR code encoding the permanent setup URL ({web_base}/setup/{claim_code})
  - The human-readable claim code printed below the QR
  - The setup-AP password for joining the camera's setup WiFi network

The sticker is meant to be affixed to the device enclosure so a phone can
scan it to reach the setup wizard for that specific camera.
"""
from __future__ import annotations

from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

# Fixed WPA2 passphrase for the setup AP — printed on the device sticker so
# the customer can join the camera's setup network.
# KEEP IN SYNC with scripts/setup-ap.sh SETUP_AP_PASSWORD default.
SETUP_AP_PASSWORD = "sunsetcam"


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

    # --- Text labels below the QR ---
    qr_w, qr_h = qr_img.size
    label_height = 100  # extra room for claim code + setup-AP password line
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

    # Centre the claim code text (first line)
    bbox = draw.textbbox((0, 0), claim_code, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_x = max(0, (qr_w - text_w) // 2)
    text_y = qr_h + 10
    draw.text((text_x, text_y), claim_code, fill="black", font=font)

    # Setup-AP password line (second line)
    pw_label = f"Setup WiFi password: {SETUP_AP_PASSWORD}"
    pw_bbox = draw.textbbox((0, 0), pw_label, font=font)
    pw_w = pw_bbox[2] - pw_bbox[0]
    pw_x = max(0, (qr_w - pw_w) // 2)
    pw_y = text_y + text_h + 12
    draw.text((pw_x, pw_y), pw_label, fill="#444444", font=font)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="PNG")
