"""Tests for the captive-portal Flask app (wifi onboarding).

Uses Flask's built-in test client — no real hardware required.
scan_fn, wifi_service, and reboot_fn are injected fakes.
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


class FakeReboot:
    def __init__(self):
        self.called = False

    def __call__(self):
        self.called = True


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
def fake_reboot():
    return FakeReboot()


@pytest.fixture()
def client(fake_wifi, fake_reboot):
    app = create_app(
        scan_fn=make_scan_fn("HomeNetwork", "Neighbor"),
        wifi_service=fake_wifi,
        reboot_fn=fake_reboot,
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
    rv = client.post("/connect", data={"ssid": "HomeNetwork", "psk": "validpassword"})
    assert rv.status_code == 200


def test_post_connect_calls_connect_with_ssid_and_psk(client, fake_wifi):
    client.post("/connect", data={"ssid": "HomeNetwork", "psk": "validpassword"})
    assert fake_wifi.connected == ("HomeNetwork", "validpassword")


def test_post_connect_success_page_mentions_ssid(client, fake_wifi):
    rv = client.post("/connect", data={"ssid": "HomeNetwork", "psk": "validpassword"})
    assert b"HomeNetwork" in rv.data


def test_post_connect_success_calls_reboot_fn(client, fake_wifi, fake_reboot):
    """After a successful save, reboot_fn must be called."""
    client.post("/connect", data={"ssid": "HomeNetwork", "psk": "validpassword"})
    assert fake_reboot.called is True


def test_post_connect_success_page_mentions_reboot(client, fake_wifi):
    """Success page copy should mention reboot so user knows what to expect."""
    rv = client.post("/connect", data={"ssid": "HomeNetwork", "psk": "validpassword"})
    body = rv.data.lower()
    assert b"reboot" in body or b"restart" in body


# ---------------------------------------------------------------------------
# POST /connect — empty ssid → 400, no join, no reboot
# ---------------------------------------------------------------------------

def test_post_connect_empty_ssid_returns_400(client, fake_wifi):
    rv = client.post("/connect", data={"ssid": "", "psk": "validpassword"})
    assert rv.status_code == 400


def test_post_connect_empty_ssid_connect_not_called(client, fake_wifi):
    client.post("/connect", data={"ssid": "", "psk": "validpassword"})
    assert fake_wifi.connected is None


def test_post_connect_empty_ssid_shows_error(client, fake_wifi):
    rv = client.post("/connect", data={"ssid": "", "psk": "validpassword"})
    # Should re-render the form with an error message
    assert b"<form" in rv.data


def test_post_connect_empty_ssid_reboot_not_called(client, fake_wifi, fake_reboot):
    """On validation failure, reboot_fn must NOT be called."""
    client.post("/connect", data={"ssid": "", "psk": "validpassword"})
    assert fake_reboot.called is False


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


# ---------------------------------------------------------------------------
# POST /connect — password-length validation (>=8 chars for WPA2)
# ---------------------------------------------------------------------------

def test_post_connect_short_psk_returns_400(fake_wifi, fake_reboot):
    """A non-empty PSK shorter than 8 chars must be rejected with HTTP 400."""
    app = create_app(
        scan_fn=make_scan_fn("HomeNetwork"),
        wifi_service=fake_wifi,
        reboot_fn=fake_reboot,
    )
    app.config["TESTING"] = True
    with app.test_client() as c:
        rv = c.post("/connect", data={"ssid": "HomeNetwork", "psk": "1234"})
    assert rv.status_code == 400


def test_post_connect_short_psk_connect_not_called(fake_wifi, fake_reboot):
    """connect() must NOT be called when PSK is too short."""
    app = create_app(
        scan_fn=make_scan_fn("HomeNetwork"),
        wifi_service=fake_wifi,
        reboot_fn=fake_reboot,
    )
    app.config["TESTING"] = True
    with app.test_client() as c:
        c.post("/connect", data={"ssid": "HomeNetwork", "psk": "short"})
    assert fake_wifi.connected is None


def test_post_connect_short_psk_reboot_not_called(fake_wifi, fake_reboot):
    """reboot_fn must NOT be called when PSK is too short."""
    app = create_app(
        scan_fn=make_scan_fn("HomeNetwork"),
        wifi_service=fake_wifi,
        reboot_fn=fake_reboot,
    )
    app.config["TESTING"] = True
    with app.test_client() as c:
        c.post("/connect", data={"ssid": "HomeNetwork", "psk": "short"})
    assert fake_reboot.called is False


def test_post_connect_short_psk_shows_form_with_error(fake_wifi, fake_reboot):
    """On short-PSK rejection, form must be re-rendered with an error message."""
    app = create_app(
        scan_fn=make_scan_fn("HomeNetwork"),
        wifi_service=fake_wifi,
        reboot_fn=fake_reboot,
    )
    app.config["TESTING"] = True
    with app.test_client() as c:
        rv = c.post("/connect", data={"ssid": "HomeNetwork", "psk": "abc"})
    assert b"<form" in rv.data
    assert b"8" in rv.data  # error mentions 8-char minimum


def test_post_connect_empty_psk_open_network_proceeds(fake_wifi, fake_reboot):
    """Empty PSK = open network — must still proceed (connect called, reboot called)."""
    app = create_app(
        scan_fn=make_scan_fn("OpenNet"),
        wifi_service=fake_wifi,
        reboot_fn=fake_reboot,
    )
    app.config["TESTING"] = True
    with app.test_client() as c:
        rv = c.post("/connect", data={"ssid": "OpenNet", "psk": ""})
    assert fake_wifi.connected == ("OpenNet", "")
    assert fake_reboot.called is True
    assert rv.status_code == 200


def test_post_connect_exactly_8_char_psk_proceeds(fake_wifi, fake_reboot):
    """A PSK of exactly 8 chars must be accepted (WPA2 minimum)."""
    app = create_app(
        scan_fn=make_scan_fn("HomeNetwork"),
        wifi_service=fake_wifi,
        reboot_fn=fake_reboot,
    )
    app.config["TESTING"] = True
    with app.test_client() as c:
        rv = c.post("/connect", data={"ssid": "HomeNetwork", "psk": "12345678"})
    assert rv.status_code == 200
    assert fake_wifi.connected == ("HomeNetwork", "12345678")


# ---------------------------------------------------------------------------
# GET / — reassuring copy present
# ---------------------------------------------------------------------------

def test_get_index_has_reassuring_copy(client):
    """The index page must include a security-reassurance notice."""
    rv = client.get("/")
    body = rv.data.lower()
    # Key phrases from the reassuring paragraph
    assert b"private" in body or b"encrypted" in body or b"direct" in body
