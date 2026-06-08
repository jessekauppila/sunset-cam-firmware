"""Pi-side alignment tool: framework-agnostic page + stream renderers.

Public API:
- ``render_align_page(lat, lng, year=None)`` → HTML for ``/setup/align``
- ``render_orientation_json(sampler)`` → JSON for ``/setup/orientation.json``
- ``stream_mjpeg(frame_source, fps)`` → multipart MJPEG bytes for ``/setup/preview.mjpg``
  (added in Task 9)

Spec: docs/superpowers/specs/2026-05-17-pi-side-alignment-tool-design.md v0.2
"""
from __future__ import annotations

import json
from datetime import date
from typing import Callable, Iterator

from sunset_cam.orientation_sampler import OrientationSampler
from sunset_cam.solstice_math import (
    sunset_azimuth_for_day,
    az_to_pixel,
    count_sunsets_in_fov,
)


FOV_DEG = 102.0          # Camera Module 3 Wide horizontal FOV
SCREEN_W = 1600          # Match SVG viewBox width
SCREEN_H = 900           # Match SVG viewBox height
HORIZON_Y = 450          # Vertical center

_AIM_SCRIPT = """
<script>
  const _img = document.querySelector('.preview-wrap img');
  if (_img) _img.addEventListener('pointerdown', async (e) => {
    const r = _img.getBoundingClientRect();
    const px = Math.round((e.clientX - r.left) / r.width * (_img.naturalWidth || 1600));
    const py = Math.round((e.clientY - r.top) / r.height * (_img.naturalHeight || 900));
    const resp = await fetch('/setup/tap', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({pixel_x: px, pixel_y: py})});
    window._lastTap = await resp.json();
  });
  async function pollHeadingState() {
    try {
      const s = await (await fetch('/setup/state.json', {cache: 'no-store'})).json();
      document.body.dataset.headingStatus = s.status;
      const b = document.getElementById('heading-badge');
      if (b) b.textContent = (s.status === 'tapped')
        ? ('aimed ' + Math.round(s.heading_deg) + '\\u00b0' + (s.fits ? ' \\u2713' : ' \\u2014 clipped'))
        : (s.status === 'suspect' ? 're-tap' : 'tap the sun');
    } catch (e) {}
  }
  setInterval(pollHeadingState, 400); pollHeadingState();
</script>
"""


def _facing_data(lat: float, lng: float, year: int) -> dict:
    """Pre-compute marker positions + sunsets/year counts for each facing."""
    jun_az = sunset_azimuth_for_day(lat, year, 6, 21)
    dec_az = sunset_azimuth_for_day(lat, year, 12, 21)
    out: dict[str, dict] = {}
    for facing, center_az in (("east", 90.0), ("west", 270.0)):
        out[facing] = {
            "jun_x": az_to_pixel(jun_az, center_az, FOV_DEG, SCREEN_W),
            "dec_x": az_to_pixel(dec_az, center_az, FOV_DEG, SCREEN_W),
            "count": count_sunsets_in_fov(lat, lng, center_az, FOV_DEG, year),
        }
    out["both"] = {
        "jun_x": out["west"]["jun_x"],
        "dec_x": out["east"]["dec_x"],
        "count": min(365, out["east"]["count"] + out["west"]["count"]),
    }
    return out


def _marker_group(facing: str, data: dict) -> str:
    """Render the SVG markers + shaded wedge for one facing."""
    jx, dx = data["jun_x"], data["dec_x"]
    lo, hi = sorted((jx, dx))
    wedge = (
        f'<rect x="{lo}" y="{HORIZON_Y - 30}" '
        f'width="{hi - lo}" height="60" '
        f'fill="#ffcc66" fill-opacity="0.18" />'
    )
    j_line = (
        f'<line x1="{jx}" y1="{HORIZON_Y - 30}" x2="{jx}" y2="{HORIZON_Y + 30}" '
        f'stroke="#ffd088" stroke-width="2" stroke-dasharray="6 4" />'
    )
    d_line = (
        f'<line x1="{dx}" y1="{HORIZON_Y - 30}" x2="{dx}" y2="{HORIZON_Y + 30}" '
        f'stroke="#ffaa55" stroke-width="2" stroke-dasharray="6 4" />'
    )
    return f'<g class="facing-group" data-facing="{facing}">{wedge}{j_line}{d_line}</g>'


def render_align_page(lat: float, lng: float, year: int | None = None, phase: str = "sunset") -> str:
    """Render the alignment page HTML."""
    if year is None:
        year = date.today().year
    facing = _facing_data(lat, lng, year)
    marker_groups = "\n".join(
        _marker_group(name, facing[name]) for name in ("east", "west", "both")
    )
    counter_spans = "\n".join(
        f'<span class="counter" data-facing="{name}">{facing[name]["count"]} sunsets/year</span>'
        for name in ("east", "west", "both")
    )

    html = f"""<!doctype html>
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
    .facing-form {{ display: flex; gap: 12px; justify-content: center; padding: 12px; background: #181818; }}
    .facing-form label {{ padding: 6px 14px; border: 1px solid #444; border-radius: 16px; cursor: pointer; }}
    .facing-form input {{ display: none; }}
    .facing-form input:checked + label {{ background: #2a4a7a; border-color: #4a7acc; }}
    .facing-group, .counter {{ display: none; }}
    body:not([data-heading-status="tapped"]) .facing-group {{ display: none; }}
    body[data-current-facing="east"] .facing-group[data-facing="east"],
    body[data-current-facing="east"] .counter[data-facing="east"],
    body[data-current-facing="west"] .facing-group[data-facing="west"],
    body[data-current-facing="west"] .counter[data-facing="west"],
    body[data-current-facing="both"] .facing-group[data-facing="both"],
    body[data-current-facing="both"] .counter[data-facing="both"] {{ display: inline; }}
    .counter-bar {{ text-align: center; padding: 10px; background: #181818; font-size: 18px; }}
    .counter {{ color: #ffcc66; font-weight: 600; }}
    .instructions {{ padding: 16px 20px; line-height: 1.55; max-width: 560px; margin: 0 auto; }}
    .instructions ol {{ padding-left: 1.2em; }}
  </style>
</head>
<body data-lat="{lat}" data-lng="{lng}" data-current-facing="west" data-phase="{phase}" data-heading-status="uncalibrated">
  <div class="top-hud">
    <span>roll: <span id="roll-readout" class="readout">—</span></span>
    <span>pitch: <span id="pitch-readout" class="readout">—</span></span>
    <span id="level-badge" class="level-badge">checking…</span>
    <span id="heading-badge" class="level-badge">tap the sun</span>
  </div>

  <div class="preview-wrap">
    <img src="/setup/preview.mjpg" alt="camera preview" />
    <svg class="overlay" viewBox="0 0 {SCREEN_W} {SCREEN_H}" preserveAspectRatio="none">
      <line x1="0" y1="{HORIZON_Y}" x2="{SCREEN_W}" y2="{HORIZON_Y}"
            stroke="#ffcc66" stroke-width="2" stroke-dasharray="12 6" opacity="0.85" />
      <text x="{SCREEN_W // 2}" y="60" fill="#ffcc66" font-size="36" text-anchor="middle"
            font-family="system-ui, sans-serif">&uarr; UP</text>
{marker_groups}
    </svg>
  </div>

  <form class="facing-form" id="facing-form">
    <input type="radio" name="facing" id="facing-east" value="east" />
    <label for="facing-east">East (sunrise)</label>
    <input type="radio" name="facing" id="facing-west" value="west" checked />
    <label for="facing-west">West (sunset)</label>
    <input type="radio" name="facing" id="facing-both" value="both" />
    <label for="facing-both">Both</label>
  </form>

  <div class="counter-bar">
{counter_spans}
  </div>

  <div class="instructions">
    <p>Rotate the camera housing until:</p>
    <ol>
      <li>The roll readout is close to 0° and the badge shows green.</li>
      <li>The &uarr; on screen matches the &uarr; on the housing.</li>
      <li>The shaded wedge falls inside the visible preview.</li>
    </ol>
    <p>When all three match, mount the camera. Then close this tab and return to setup.</p>
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

    document.getElementById('facing-form').addEventListener('change', (ev) => {{
      if (ev.target && ev.target.name === 'facing') {{
        document.body.dataset.currentFacing = ev.target.value;
      }}
    }});
  </script>
</body>
</html>
"""
    return html.replace("</body>", _AIM_SCRIPT + "</body>")


def render_orientation_json(sampler: OrientationSampler) -> str:
    """Return the latest cached reading as a JSON string. Empty object when
    the sampler has not yet captured anything (e.g., during the first 200 ms
    after startup)."""
    latest = sampler.latest()
    return json.dumps(latest if latest is not None else {})


MJPEG_BOUNDARY = "sunsetcamframe"


def stream_mjpeg(
    frame_source: Callable[[], bytes],
    fps: int = 4,
) -> Iterator[bytes]:
    """Yield multipart-encoded MJPEG bytes by polling ``frame_source``.

    Terminates cleanly on StopIteration (EOF) or any other exception
    (transient camera glitch). The caller (web app) is responsible for
    rate-limiting between frames; the ``fps`` parameter is informational.
    """
    boundary = MJPEG_BOUNDARY
    while True:
        try:
            frame = frame_source()
        except StopIteration:
            return
        except Exception:
            return

        header = (
            f"--{boundary}\r\n"
            f"Content-Type: image/jpeg\r\n"
            f"Content-Length: {len(frame)}\r\n"
            f"\r\n"
        ).encode("ascii")
        yield header
        yield frame
        yield b"\r\n"
