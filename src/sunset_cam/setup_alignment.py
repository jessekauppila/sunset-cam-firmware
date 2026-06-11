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
    sunset_arc_azimuths,
    az_to_pixel,
    count_sunsets_in_fov,
)


FOV_DEG = 102.0          # Camera Module 3 Wide horizontal FOV
SCREEN_W = 1600          # Match SVG viewBox width
SCREEN_H = 900           # Match SVG viewBox height
HORIZON_Y = 450          # Vertical center

_AIM_SCRIPT = """
<button id="confirm-aim" hidden>Confirm aim</button>
<script>
  const _img = document.querySelector('.preview-wrap img');
  const _overlay = document.querySelector('.overlay');
  const _marker = document.getElementById('tap-marker');
  const _sunDot = document.getElementById('sun-dot');
  if (_img) _img.addEventListener('pointerdown', async (e) => {
    const r = _img.getBoundingClientRect();
    const fx = (e.clientX - r.left) / r.width;
    const fy = (e.clientY - r.top) / r.height;
    const px = Math.round(fx * (_img.naturalWidth || 1600));
    const py = Math.round(fy * (_img.naturalHeight || 900));
    if (_marker && _overlay) {
      const vb = _overlay.viewBox.baseVal;
      _marker.setAttribute('cx', fx * vb.width);
      _marker.setAttribute('cy', fy * vb.height);
      _marker.setAttribute('visibility', 'visible');
    }
    const resp = await fetch('/setup/tap', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({pixel_x: px, pixel_y: py})});
    window._lastTap = await resp.json();
  });
  const _confirm = document.getElementById('confirm-aim');
  if (_confirm) _confirm.addEventListener('click', async () => {
    const resp = await fetch('/setup/confirm', {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: '{}'});
    const j = await resp.json();
    if (j.status === 'confirmed') _confirm.textContent = 'Aim confirmed \\u2713';
  });
  async function postHeading(deg, source) {
    const resp = await fetch('/setup/heading', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({heading_deg: deg, source: source})});
    return resp.json();
  }
  const _setManual = document.getElementById('set-manual-heading');
  if (_setManual) _setManual.addEventListener('click', async () => {
    const v = parseFloat(document.getElementById('manual-heading').value);
    if (!isNaN(v)) await postHeading(v, 'manual');
  });
  const _usePhone = document.getElementById('use-phone-compass');
  const _phoneOut = document.getElementById('phone-heading-readout');
  if (_usePhone) _usePhone.addEventListener('click', async () => {
    if (!window.isSecureContext) {
      if (_phoneOut) _phoneOut.textContent = 'phone compass needs HTTPS — use manual for now';
      return;
    }
    try {
      if (typeof DeviceOrientationEvent !== 'undefined' &&
          typeof DeviceOrientationEvent.requestPermission === 'function') {
        const perm = await DeviceOrientationEvent.requestPermission();
        if (perm !== 'granted') { if (_phoneOut) _phoneOut.textContent = 'permission denied'; return; }
      }
      window.addEventListener('deviceorientation', (e) => {
        const h = (e.webkitCompassHeading != null) ? e.webkitCompassHeading
                : (e.absolute && e.alpha != null) ? (360 - e.alpha) % 360 : null;
        if (h != null && _phoneOut) {
          _phoneOut.dataset.heading = h;
          _phoneOut.textContent = 'phone heading ' + Math.round(h) + '° — tap to capture';
        }
      });
      if (_phoneOut) _phoneOut.onclick = async () => {
        const h = parseFloat(_phoneOut.dataset.heading);
        if (!isNaN(h)) { await postHeading(h, 'phone'); _phoneOut.textContent = 'captured ' + Math.round(h) + '°'; }
      };
    } catch (err) { if (_phoneOut) _phoneOut.textContent = 'compass unavailable'; }
  });
  function positionArc(heading) {
    const arc = document.getElementById('ar-arc');
    if (!arc || !_overlay) return;
    if (heading == null || isNaN(heading)) {
      arc.setAttribute('visibility', 'hidden');
      ['arc-arrow-left', 'arc-arrow-right'].forEach((id) => {
        const a = document.getElementById(id); if (a) a.setAttribute('visibility', 'hidden');
      });
      return;
    }
    const vb = _overlay.viewBox.baseVal;
    const fov = parseFloat(document.body.dataset.fov || '102');
    const bearings = [
      ['summer', parseFloat(document.body.dataset.arcSummer)],
      ['equinox', parseFloat(document.body.dataset.arcEquinox)],
      ['winter', parseFloat(document.body.dataset.arcWinter)],
    ];
    arc.setAttribute('visibility', 'visible');
    let offLeft = false, offRight = false;
    for (const [name, az] of bearings) {
      const delta = ((az - heading + 540) % 360) - 180;   // signed deg, + = to the right
      const x = vb.width * (0.5 + delta / fov);
      const inFrame = (x >= 0 && x <= vb.width);
      const line = document.getElementById('arc-' + name);
      const label = document.getElementById('arc-' + name + '-label');
      if (line) { line.setAttribute('x1', x); line.setAttribute('x2', x); line.setAttribute('visibility', inFrame ? 'visible' : 'hidden'); }
      if (label) { label.setAttribute('x', x); label.setAttribute('visibility', inFrame ? 'visible' : 'hidden'); }
      if (!inFrame) { if (x < 0) offLeft = true; else offRight = true; }
    }
    const al = document.getElementById('arc-arrow-left');
    const ar = document.getElementById('arc-arrow-right');
    if (al) al.setAttribute('visibility', offLeft ? 'visible' : 'hidden');
    if (ar) ar.setAttribute('visibility', offRight ? 'visible' : 'hidden');
  }
  async function pollHeadingState() {
    try {
      const s = await (await fetch('/setup/state.json', {cache: 'no-store'})).json();
      document.body.dataset.headingStatus = s.status;
      const aimed = (s.status === 'tapped' || s.status === 'tracking');
      if (_confirm) _confirm.hidden = !aimed;
      const b = document.getElementById('heading-badge');
      if (b) {
        if (aimed) {
          const lead = (s.status === 'tracking') ? '\\u2600 tracking ' : 'aimed ';
          b.textContent = lead + Math.round(s.heading_deg) + '\\u00b0'
            + (s.fits ? ' \\u2713' : ' \\u2014 clipped');
        } else {
          b.textContent = (s.status === 'suspect') ? 're-tap' : 'tap the sun';
        }
      }
      if (_sunDot && _overlay) {
        if (s.sun_fx !== undefined) {
          const vb = _overlay.viewBox.baseVal;
          _sunDot.setAttribute('cx', s.sun_fx * vb.width);
          _sunDot.setAttribute('cy', s.sun_fy * vb.height);
          _sunDot.setAttribute('visibility', 'visible');
        } else {
          _sunDot.setAttribute('visibility', 'hidden');
        }
      }
      positionArc(s.heading_deg !== undefined ? s.heading_deg : null);
    } catch (e) {}
  }
  setInterval(pollHeadingState, 400); pollHeadingState();
  // static preview hook: render the AR arc at a fixed heading without a server
  if (document.body.dataset.previewHeading !== undefined) {
    positionArc(parseFloat(document.body.dataset.previewHeading));
  }
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


def render_align_page(
    lat: float, lng: float, year: int | None = None, phase: str = "sunset",
    mount_roll_ref_deg: float = 0.0, mount_pitch_ref_deg: float = 0.0,
    level_tol_deg: float = 15.0, hfov_deg: float = FOV_DEG,
) -> str:
    """Render the alignment page HTML. The mount reference (roll/pitch the camera
    reads when correctly mounted) drives the level badge + tilt banner, and must
    match the backend gate so the UI and server agree on 'level enough to tap'."""
    if year is None:
        year = date.today().year
    facing = _facing_data(lat, lng, year)
    arc_summer, arc_equinox, arc_winter = sunset_arc_azimuths(lat, year)
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
    .tilt-banner {{ padding: 11px 16px; text-align: center; font-size: 15px; font-weight: 600; }}
    .tilt-banner.warn {{ background: #5a1f1f; color: #ffd6d6; }}
    .tilt-banner.ok {{ background: #1f4a24; color: #d8ffd8; }}
    #tap-marker {{ pointer-events: none; }}
    .overlay .facing-group {{ display: none !important; }}  /* superseded by the world-locked AR arc */
    .heading-source {{ padding: 8px 20px; max-width: 560px; margin: 0 auto; }}
    .heading-source summary {{ cursor: pointer; color: #9cc4ff; }}
    .hs-row {{ display: flex; gap: 10px; align-items: center; margin: 10px 0; flex-wrap: wrap; }}
    .heading-source input {{ width: 80px; padding: 4px; }}
    .heading-source button {{ padding: 6px 12px; border-radius: 6px; border: 1px solid #4a7acc; background: #1c2a44; color: #fff; }}
    #phone-heading-readout {{ font-size: 13px; color: #ffcc66; }}
  </style>
</head>
<body data-lat="{lat}" data-lng="{lng}" data-current-facing="west" data-phase="{phase}" data-heading-status="uncalibrated" data-mount-roll-ref="{mount_roll_ref_deg}" data-mount-pitch-ref="{mount_pitch_ref_deg}" data-level-tol="{level_tol_deg}" data-arc-summer="{arc_summer}" data-arc-equinox="{arc_equinox}" data-arc-winter="{arc_winter}" data-fov="{hfov_deg}">
  <div class="top-hud">
    <span>roll: <span id="roll-readout" class="readout">—</span></span>
    <span>pitch: <span id="pitch-readout" class="readout">—</span></span>
    <span id="level-badge" class="level-badge">checking…</span>
    <span id="heading-badge" class="level-badge">tap the sun</span>
  </div>

  <div id="tilt-banner" class="tilt-banner warn">checking orientation…</div>

  <div class="preview-wrap">
    <img src="/setup/preview.mjpg" alt="camera preview" />
    <svg class="overlay" viewBox="0 0 {SCREEN_W} {SCREEN_H}" preserveAspectRatio="none">
      <line x1="0" y1="{HORIZON_Y}" x2="{SCREEN_W}" y2="{HORIZON_Y}"
            stroke="#ffcc66" stroke-width="2" stroke-dasharray="12 6" opacity="0.85" />
      <text x="{SCREEN_W // 2}" y="60" fill="#ffcc66" font-size="36" text-anchor="middle"
            font-family="system-ui, sans-serif">&uarr; UP</text>
{marker_groups}
      <circle id="tap-marker" cx="0" cy="0" r="34" fill="none"
              stroke="#ff5a5a" stroke-width="5" visibility="hidden" />
      <circle id="sun-dot" cx="0" cy="0" r="26" fill="none"
              stroke="#ffd54a" stroke-width="5" visibility="hidden" />
      <!-- world-locked AR sunset arc: lines pinned to true bearings, positioned by JS -->
      <g id="ar-arc" visibility="hidden">
        <line id="arc-summer" x1="0" x2="0" y1="{HORIZON_Y - 130}" y2="{HORIZON_Y + 130}"
              stroke="#ffd088" stroke-width="3" stroke-dasharray="10 7" opacity="0.9" />
        <line id="arc-equinox" x1="0" x2="0" y1="{HORIZON_Y - 130}" y2="{HORIZON_Y + 130}"
              stroke="#ffcc66" stroke-width="3" opacity="0.95" />
        <line id="arc-winter" x1="0" x2="0" y1="{HORIZON_Y - 130}" y2="{HORIZON_Y + 130}"
              stroke="#ffaa55" stroke-width="3" stroke-dasharray="10 7" opacity="0.9" />
        <text id="arc-summer-label" x="0" y="{HORIZON_Y - 140}" fill="#ffd088"
              font-size="26" text-anchor="middle" font-family="system-ui">Jun</text>
        <text id="arc-equinox-label" x="0" y="{HORIZON_Y - 140}" fill="#ffcc66"
              font-size="26" text-anchor="middle" font-family="system-ui">Equinox</text>
        <text id="arc-winter-label" x="0" y="{HORIZON_Y - 140}" fill="#ffaa55"
              font-size="26" text-anchor="middle" font-family="system-ui">Dec</text>
      </g>
      <text id="arc-arrow-left" x="44" y="{HORIZON_Y + 16}" fill="#ffcc66"
            font-size="52" visibility="hidden">&#8592;</text>
      <text id="arc-arrow-right" x="{SCREEN_W - 44}" y="{HORIZON_Y + 16}" fill="#ffcc66"
            font-size="52" text-anchor="end" visibility="hidden">&#8594;</text>
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

  <div class="heading-source">
    <details>
      <summary>No sun? Set the heading another way</summary>
      <div class="hs-row">
        <label>Heading&deg;
          <input id="manual-heading" type="number" min="0" max="359" inputmode="numeric" />
        </label>
        <button id="set-manual-heading" type="button">Set</button>
      </div>
      <div class="hs-row">
        <button id="use-phone-compass" type="button">Use my phone&rsquo;s compass</button>
        <span id="phone-heading-readout"></span>
      </div>
    </details>
  </div>

  <div class="instructions">
    <p>Rotate the camera housing until:</p>
    <ol>
      <li>The tilt banner turns green (“✓ Ready”) — the housing is at its mount angle.</li>
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
        const rollRef = parseFloat(document.body.dataset.mountRollRef || '0');
        const pitchRef = parseFloat(document.body.dataset.mountPitchRef || '0');
        const tol = parseFloat(document.body.dataset.levelTol || '15');
        const dRoll = Math.abs((j.roll_deg || 0) - rollRef);
        const dPitch = Math.abs((j.pitch_deg || 0) - pitchRef);
        const badge = document.getElementById('level-badge');
        const level = dRoll < 5 && dPitch < 5;
        badge.textContent = level ? 'level' : 'tilted';
        badge.classList.toggle('ok', level);
        const banner = document.getElementById('tilt-banner');
        if (banner) {{
          if (dRoll <= tol && dPitch <= tol) {{
            banner.textContent = '✓ Ready — tap the sun';
            banner.className = 'tilt-banner ok';
          }} else {{
            banner.textContent = '⚠ Camera tilted — rotate so roll ≈ ' + rollRef + '°, pitch ≈ '
              + pitchRef + '° (now: roll ' + Math.round(j.roll_deg || 0) + '°, pitch '
              + Math.round(j.pitch_deg || 0) + '°)';
            banner.className = 'tilt-banner warn';
          }}
        }}
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
