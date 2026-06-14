import pytest
from sunset_cam.register import post_register


class FakeResp:
    def __init__(self, body, *, raises=False):
        self._body = body
        self._raises = raises

    def raise_for_status(self):
        if self._raises:
            raise RuntimeError("http error")

    def json(self):
        return self._body


def test_post_register_sends_identity_and_returns_placement_status():
    captured = {}

    def fake_poster(url, json=None, headers=None, timeout=None):
        captured.update(url=url, json=json, headers=headers)
        return FakeResp({"camera_id": 1, "placement_status": "ready", "placement": {"azimuth_deg": 270}})

    cfg = {
        "api_base": "https://x.test",
        "claim_code": "SUNSET-AAAA-BBBB",
        "hardware_id": "sunset-cam-1",
        "firmware_version": "0.4.0",
        "capabilities": {"mjpeg": False},
    }
    out = post_register(cfg, poster=fake_poster)

    assert captured["url"] == "https://x.test/api/cameras/register"
    assert captured["json"]["claim_code"] == "SUNSET-AAAA-BBBB"
    assert captured["json"]["hardware_id"] == "sunset-cam-1"
    assert captured["json"]["capabilities"] == {"mjpeg": False}
    assert captured["json"]["firmware_version"] == "0.4.0"
    assert out["camera_id"] == 1
    assert out["placement_status"] == "ready"
    assert out["placement"] == {"azimuth_deg": 270}


def test_post_register_omits_placement_when_absent():
    def fake_poster(url, json=None, headers=None, timeout=None):
        return FakeResp({"camera_id": 2, "placement_status": "awaiting_location"})

    cfg = {
        "api_base": "https://x.test/",
        "claim_code": "SUNSET-AAAA-BBBB",
        "hardware_id": "c",
        "firmware_version": "0.4.0",
        "capabilities": {},
    }
    out = post_register(cfg, poster=fake_poster)

    assert out["placement_status"] == "awaiting_location"
    assert out.get("placement") is None


def test_post_register_strips_trailing_slash_from_api_base():
    captured = {}

    def fake_poster(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        return FakeResp({"camera_id": 3, "placement_status": "ready"})

    cfg = {
        "api_base": "https://x.test/",
        "claim_code": "C",
        "hardware_id": "H",
        "firmware_version": "v",
        "capabilities": {},
    }
    post_register(cfg, poster=fake_poster)
    assert captured["url"] == "https://x.test/api/cameras/register"


def test_post_register_sends_no_bearer_auth():
    """Registration is keyed by claim_code+hardware_id — no Authorization header."""
    captured = {}

    def fake_poster(url, json=None, headers=None, timeout=None):
        captured["headers"] = headers
        return FakeResp({"camera_id": 1, "placement_status": "pending"})

    cfg = {
        "api_base": "https://x.test",
        "claim_code": "C",
        "hardware_id": "H",
        "firmware_version": "v",
        "capabilities": {},
    }
    post_register(cfg, poster=fake_poster)
    assert "Authorization" not in (captured["headers"] or {})


def test_post_register_does_not_read_device_token():
    """Response must not contain or return device_token — that lives in config.json."""
    result_holder = {}

    def fake_poster(url, json=None, headers=None, timeout=None):
        # Response deliberately includes a stray device_token to prove we ignore it
        return FakeResp({"camera_id": 5, "placement_status": "ready", "device_token": "SHOULD_BE_IGNORED"})

    cfg = {
        "api_base": "https://x.test",
        "claim_code": "C",
        "hardware_id": "H",
        "firmware_version": "v",
        "capabilities": {},
    }
    out = post_register(cfg, poster=fake_poster)
    assert "device_token" not in out


def test_post_register_propagates_http_errors():
    def fake_poster(url, json=None, headers=None, timeout=None):
        return FakeResp({}, raises=True)

    with pytest.raises(RuntimeError, match="http error"):
        post_register(
            {
                "api_base": "x",
                "claim_code": "c",
                "hardware_id": "h",
                "firmware_version": "v",
                "capabilities": {},
            },
            poster=fake_poster,
        )


def test_post_register_raise_for_status_called_before_json():
    """raise_for_status must be called before json() to surface HTTP errors promptly."""
    call_order = []

    class OrderTrackingResp:
        def raise_for_status(self):
            call_order.append("raise_for_status")

        def json(self):
            call_order.append("json")
            return {"camera_id": 1, "placement_status": "ready"}

    def fake_poster(url, json=None, headers=None, timeout=None):
        return OrderTrackingResp()

    cfg = {
        "api_base": "https://x.test",
        "claim_code": "C",
        "hardware_id": "H",
        "firmware_version": "v",
        "capabilities": {},
    }
    post_register(cfg, poster=fake_poster)
    assert call_order == ["raise_for_status", "json"]
