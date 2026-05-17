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
    """Render the alignment page HTML."""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Align your camera</title>
  <style>
    body {{ background: #000; color: #fff; font: 14px system-ui, sans-serif; margin: 0; padding: 0; }}
    .top-hud {{ display: flex; gap: 12px; align-items: center; justify-content: center; padding: 10px 16px; background: #111; }}
    .readout {{ font-variant-numeric: tabular-nums; font-size: 16px; min-width: 80px; }}
    .level-badge {{ padding: 4px 10px; border-radius: 12px; font-size: 11px; background: #444; color: #aaa; }}
    .level-badge.ok {{ background: #265f2c; color: #d8ffd8; }}
    .preview-wrap {{ position: relative; width: 100%; max-width: 100vw; aspect-ratio: 16/9; margin: 0 auto; }}
    .preview-wrap img {{ width: 100%; display: block; }}
    .overlay {{ position: absolute; inset: 0; pointer-events: none; }}
    .instructions {{ padding: 16px 20px; line-height: 1.55; max-width: 560px; margin: 0 auto; }}
    .instructions ol {{ padding-left: 1.2em; }}
  </style>
</head>
<body data-lat="{lat}" data-lng="{lng}">
  <div class="top-hud">
    <span>roll: <span id="roll-readout" class="readout">—</span></span>
    <span>pitch: <span id="pitch-readout" class="readout">—</span></span>
    <span id="level-badge" class="level-badge">checking…</span>
  </div>
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
      <li>The roll readout above is close to 0° and the badge shows green.</li>
      <li>The &uarr; on screen points the same direction as the &uarr; drawn on the housing.</li>
    </ol>
    <p>When both match, mount the camera in place. Then close this tab and return to setup.</p>
  </div>
  <script>
    async function pollOrientation() {{
      try {{
        const r = await fetch('/setup/orientation.json', {{ cache: 'no-store' }});
        if (!r.ok) return;
        const j = await r.json();
        if (j.roll_deg !== undefined) {{
          document.getElementById('roll-readout').textContent = j.roll_deg.toFixed(1) + '°';
        }}
        if (j.pitch_deg !== undefined) {{
          document.getElementById('pitch-readout').textContent = j.pitch_deg.toFixed(1) + '°';
        }}
        const badge = document.getElementById('level-badge');
        const level = Math.abs(j.roll_deg || 99) < 1.0 && Math.abs(j.pitch_deg || 99) < 1.0;
        badge.textContent = level ? 'level' : 'tilted';
        badge.classList.toggle('ok', level);
      }} catch (e) {{ /* swallow */ }}
    }}
    setInterval(pollOrientation, 200);
    pollOrientation();
  </script>
</body>
</html>
"""
