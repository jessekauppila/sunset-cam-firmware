"""Captive-portal Flask app for WiFi onboarding.

Creates a minimal Flask app that:
  - Lists scanned SSIDs on GET /
  - Accepts SSID + PSK via POST /connect and delegates to WifiSetupService
  - Redirects all other paths (OS captive-portal probes) to / so the portal
    pops automatically on iOS and Android.

Use the app factory so tests can inject fakes:

    app = create_app(scan_fn=my_scan, wifi_service=my_service)
    client = app.test_client()
"""
from __future__ import annotations

from typing import Callable

from flask import Flask, redirect, render_template_string, request, url_for

# ---------------------------------------------------------------------------
# HTML templates
# ---------------------------------------------------------------------------

_INDEX_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Camera WiFi Setup</title>
  <style>
    body { font-family: sans-serif; max-width: 480px; margin: 2rem auto; padding: 0 1rem; }
    h1   { font-size: 1.4rem; }
    label { display: block; margin-top: 1rem; font-weight: bold; }
    select, input[type=password] { width: 100%; padding: .5rem; margin-top: .25rem;
                                    box-sizing: border-box; font-size: 1rem; }
    button { margin-top: 1.5rem; width: 100%; padding: .75rem;
             font-size: 1rem; background: #0070f3; color: #fff; border: none;
             border-radius: 4px; cursor: pointer; }
    .error { color: #c00; margin-top: .5rem; }
    .info  { background: #f0f4ff; border: 1px solid #c0cfe8; border-radius: 6px;
             padding: .75rem 1rem; margin-top: 1rem; font-size: .9rem;
             color: #3a4a6b; line-height: 1.5; }
  </style>
</head>
<body>
  <h1>Connect Camera to WiFi</h1>
  <div class="info">
    &#x1F512; This is a private, direct connection to your camera &mdash; your
    password is sent only to the camera over an encrypted setup network, never
    to the internet. Your browser may warn that the page is &ldquo;not
    secure&rdquo;; that&rsquo;s expected for local device setup.
  </div>
  {% if error %}
    <p class="error">{{ error }}</p>
  {% endif %}
  <form method="post" action="/connect">
    <label for="ssid">Network</label>
    <select id="ssid" name="ssid">
      {% for net in networks %}
        <option value="{{ net.ssid }}"
          {% if net.ssid == selected %}selected{% endif %}>
          {{ net.ssid }}{% if net.encrypted %} 🔒{% endif %}
        </option>
      {% endfor %}
      <option value="">-- enter manually --</option>
    </select>
    <label for="psk">Password</label>
    <input type="password" id="psk" name="psk" autocomplete="current-password"
           minlength="8">
    <button type="submit">Connect</button>
  </form>
</body>
</html>
"""

_SUCCESS_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Saved</title>
  <style>
    body { font-family: sans-serif; max-width: 480px; margin: 2rem auto; padding: 0 1rem; }
    h1   { font-size: 1.4rem; color: #080; }
  </style>
</head>
<body>
  <h1>Saved.</h1>
  <p>The camera will reboot and join <strong>{{ ssid }}</strong> in about a minute — you can close this page.</p>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Captive-portal probe paths (iOS / Android / Windows / Linux)
# ---------------------------------------------------------------------------
_PROBE_PATHS = frozenset([
    "/generate_204",           # Android / Chrome
    "/hotspot-detect.html",    # Apple
    "/ncsi.txt",               # Windows NCSI
    "/connecttest.txt",        # Windows NCSI v2
])


# ---------------------------------------------------------------------------
# Default reboot implementation
# ---------------------------------------------------------------------------

def _default_reboot() -> None:
    """Schedule a reboot 3 s out via systemd so the HTTP response flushes first.

    Using ``systemd-run --on-active`` means the reboot is triggered by the
    init system after a short delay, giving Flask time to send the success page
    before the AP radio drops.
    """
    import subprocess
    subprocess.Popen(["systemd-run", "--on-active=3", "systemctl", "reboot"])


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(
    *,
    scan_fn: Callable[[], list[dict]],
    wifi_service,
    reboot_fn: Callable[[], None] = _default_reboot,
) -> Flask:
    """Build and return the captive-portal Flask application.

    Parameters
    ----------
    scan_fn:
        Callable that returns a list of network dicts
        ``{"ssid": str, "signal": int, "encrypted": bool}``.
        Called on every GET / so the list is always fresh.
    wifi_service:
        Object with a ``connect(ssid, psk)`` method
        (a :class:`~sunset_cam.wifi_setup.WifiSetupService` or a test fake).
        ``connect`` saves the NM profile without activating it;
        raises ``ValueError`` when ssid is empty.
    reboot_fn:
        Zero-argument callable invoked after a successful credential save.
        Defaults to a systemd-run delayed reboot so the radio switches cleanly
        on next boot.  Inject a no-op or spy in tests.
    """
    app = Flask(__name__)

    # ------------------------------------------------------------------
    # GET / — scan and render the network list form
    # ------------------------------------------------------------------
    @app.get("/")
    def index():
        networks = scan_fn()
        return render_template_string(_INDEX_HTML, networks=networks,
                                      selected=None, error=None)

    # ------------------------------------------------------------------
    # POST /connect — save creds, then schedule reboot
    # ------------------------------------------------------------------
    @app.post("/connect")
    def connect():
        ssid = request.form.get("ssid", "")
        psk = request.form.get("psk", "")
        # Server-side password-length check: non-empty PSKs must be >= 8 chars
        # (WPA2 minimum). Empty PSK = open network, which is still allowed.
        if psk and len(psk) < 8:
            networks = scan_fn()
            body = render_template_string(
                _INDEX_HTML, networks=networks, selected=ssid,
                error="WiFi password must be at least 8 characters.",
            )
            return body, 400
        try:
            wifi_service.connect(ssid, psk)
        except ValueError as exc:
            # Re-render the form with the error; HTTP 400
            networks = scan_fn()
            body = render_template_string(_INDEX_HTML, networks=networks,
                                          selected=ssid, error=str(exc))
            return body, 400
        reboot_fn()
        return render_template_string(_SUCCESS_HTML, ssid=ssid), 200

    # ------------------------------------------------------------------
    # Captive-portal catch-all — redirect everything else to /
    # ------------------------------------------------------------------
    @app.get("/generate_204")
    @app.get("/hotspot-detect.html")
    @app.get("/ncsi.txt")
    @app.get("/connecttest.txt")
    def _probe():
        return redirect(url_for("index"), 302)

    @app.get("/<path:path>")
    def catch_all(path):  # noqa: ARG001
        return redirect(url_for("index"), 302)

    return app
