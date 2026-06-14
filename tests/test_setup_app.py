"""Tests for the captive-portal Flask app (wifi onboarding).

Uses Flask's built-in test client — no real hardware required.
scan_fn and wifi_service are injected fakes.
"""
from __future__ import annotations

import pytest

from sunset_cam.setup_app import create_app


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeWifi:
    def __init__(self):
        self.connected = None  # (ssid, psk) when connect() is called

    def connect(self, ssid: str, psk: str) -> None:
        if not ssid or not ssid.strip():
            raise ValueError("empty ssid")
        self.connected = (ssid, psk)


def make_scan_fn(*ssids):
    """Return a scan_fn that yields a fixed list of network dicts."""
    networks = [{"ssid": s, "signal_dbm": -50, "encrypted": True} for s in ssids]
    return lambda: networks


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_wifi():
    return FakeWifi()


@pytest.fixture()
def client(fake_wifi):
    app = create_app(
        scan_fn=make_scan_fn("HomeNetwork", "Neighbor"),
        wifi_service=fake_wifi,
    )
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# GET / — index page lists SSIDs
# ---------------------------------------------------------------------------

def test_get_index_returns_200(client):
    rv = client.get("/")
    assert rv.status_code == 200


def test_get_index_lists_scanned_ssid(client):
    rv = client.get("/")
    assert b"HomeNetwork" in rv.data


def test_get_index_has_form(client):
    rv = client.get("/")
    assert b"<form" in rv.data
    assert b"/connect" in rv.data


# ---------------------------------------------------------------------------
# POST /connect — happy path
# ---------------------------------------------------------------------------

def test_post_connect_success_returns_200(client, fake_wifi):
    rv = client.post("/connect", data={"ssid": "HomeNetwork", "psk": "pw"})
    assert rv.status_code == 200


def test_post_connect_calls_connect_with_ssid_and_psk(client, fake_wifi):
    client.post("/connect", data={"ssid": "HomeNetwork", "psk": "pw"})
    assert fake_wifi.connected == ("HomeNetwork", "pw")


def test_post_connect_success_page_mentions_ssid(client, fake_wifi):
    rv = client.post("/connect", data={"ssid": "HomeNetwork", "psk": "pw"})
    assert b"HomeNetwork" in rv.data


# ---------------------------------------------------------------------------
# POST /connect — empty ssid → 400, no join
# ---------------------------------------------------------------------------

def test_post_connect_empty_ssid_returns_400(client, fake_wifi):
    rv = client.post("/connect", data={"ssid": "", "psk": "pw"})
    assert rv.status_code == 400


def test_post_connect_empty_ssid_connect_not_called(client, fake_wifi):
    client.post("/connect", data={"ssid": "", "psk": "pw"})
    assert fake_wifi.connected is None


def test_post_connect_empty_ssid_shows_error(client, fake_wifi):
    rv = client.post("/connect", data={"ssid": "", "psk": "pw"})
    # Should re-render the form with an error message
    assert b"<form" in rv.data


# ---------------------------------------------------------------------------
# Captive-portal catch-all — probe paths redirect to /
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("probe", [
    "/generate_204",
    "/hotspot-detect.html",
    "/ncsi.txt",
    "/connecttest.txt",
    "/some/other/path",
])
def test_probe_redirects_to_root(client, probe):
    rv = client.get(probe)
    assert rv.status_code == 302
    assert rv.headers["Location"].endswith("/")


def test_root_itself_does_not_redirect(client):
    """GET / must render the page, not loop-redirect."""
    rv = client.get("/")
    assert rv.status_code == 200
