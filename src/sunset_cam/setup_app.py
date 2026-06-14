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
  </style>
</head>
<body>
  <h1>Connect Camera to WiFi</h1>
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
    <input type="password" id="psk" name="psk" autocomplete="current-password">
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
  <title>Connecting…</title>
  <style>
    body { font-family: sans-serif; max-width: 480px; margin: 2rem auto; padding: 0 1rem; }
    h1   { font-size: 1.4rem; color: #080; }
  </style>
</head>
<body>
  <h1>Connecting…</h1>
  <p>The camera will join <strong>{{ ssid }}</strong> and come online shortly.</p>
  <p>You can close this page. The camera will appear on your network in about 30 seconds.</p>
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
# App factory
# ---------------------------------------------------------------------------

def create_app(
    *,
    scan_fn: Callable[[], list[dict]],
    wifi_service,
) -> Flask:
    """Build and return the captive-portal Flask application.

    Parameters
    ----------
    scan_fn:
        Callable that returns a list of network dicts
        ``{"ssid": str, "signal_dbm": int | None, "encrypted": bool}``.
        Called on every GET / so the list is always fresh.
    wifi_service:
        Object with ``write_credentials(ssid, psk)`` and ``join()`` methods
        (a :class:`~sunset_cam.wifi_setup.WifiSetupService` or a test fake).
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
    # POST /connect — write creds + join
    # ------------------------------------------------------------------
    @app.post("/connect")
    def connect():
        ssid = request.form.get("ssid", "")
        psk = request.form.get("psk", "")
        try:
            wifi_service.write_credentials(ssid, psk)
        except ValueError as exc:
            # Re-render the form with the error; HTTP 400
            networks = scan_fn()
            body = render_template_string(_INDEX_HTML, networks=networks,
                                          selected=ssid, error=str(exc))
            return body, 400
        wifi_service.join()
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
