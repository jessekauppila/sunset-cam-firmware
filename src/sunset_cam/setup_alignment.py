"""Pi-side alignment tool: framework-agnostic page + stream renderers.

Public API (built up across tasks 5-9):
- ``render_align_page(lat, lng)`` → HTML for ``/setup/align``
- ``render_orientation_json(sampler)`` → JSON for ``/setup/orientation.json``
  (added in Task 7)
- ``stream_mjpeg(frame_source, fps)`` → multipart MJPEG bytes for
  ``/setup/preview.mjpg`` (added in Task 9)

Spec: docs/superpowers/specs/2026-05-17-pi-side-alignment-tool-design.md v0.2
"""
from __future__ import annotations


def render_align_page(lat: float, lng: float) -> str:
    """Render the alignment page HTML. Embeds the camera's lat/lng as
    data-attributes for use by client-side scripts (added in Task 6)."""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Align your camera</title>
  <style>
    body {{ background: #000; color: #fff; font: 14px system-ui, sans-serif; margin: 0; padding: 0; }}
    .preview-wrap {{ position: relative; width: 100%; max-width: 100vw; aspect-ratio: 16/9; margin: 0 auto; }}
    .preview-wrap img {{ width: 100%; display: block; }}
    .overlay {{ position: absolute; inset: 0; pointer-events: none; }}
    .instructions {{ padding: 16px 20px; line-height: 1.55; max-width: 560px; margin: 0 auto; }}
    .instructions ol {{ padding-left: 1.2em; }}
  </style>
</head>
<body data-lat="{lat}" data-lng="{lng}">
  <div class="preview-wrap">
    <img src="/setup/preview.mjpg" alt="camera preview" />
    <svg class="overlay" viewBox="0 0 1600 900" preserveAspectRatio="none">
      <line x1="0" y1="450" x2="1600" y2="450"
            stroke="#ffcc66" stroke-width="2" stroke-dasharray="12 6" opacity="0.85" />
      <text x="800" y="60" fill="#ffcc66" font-size="36" text-anchor="middle"
            font-family="system-ui, sans-serif">&uarr; UP</text>
    </svg>
  </div>
  <div class="instructions">
    <p>Rotate the camera housing until:</p>
    <ol>
      <li>The real horizon lines up with the dashed line.</li>
      <li>The &uarr; on screen points the same direction as the &uarr; drawn on the housing.</li>
    </ol>
    <p>When both match, mount the camera in place. Then close this tab and return to setup.</p>
    </div>
</body>
</html>
"""
