"""TDD tests for provision_client.provision_unit()."""
import pytest
from sunset_cam.provision_client import provision_unit


class FakeResp:
    def __init__(self, body, *, raises=False):
        self._body = body
        self._raises = raises

    def raise_for_status(self):
        if self._raises:
            raise RuntimeError("http error")

    def json(self):
        return self._body


GOOD_BODY = {
    "camera_id": 1,
    "claim_code": "SUNSET-AAAA-BBBB",
    "device_token": "tok-abc",
}


def test_provision_unit_posts_to_correct_url():
    captured = {}

    def fake_poster(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        return FakeResp(GOOD_BODY)

    provision_unit("https://api.example.com", "secret", "hw-001", poster=fake_poster)
    assert captured["url"] == "https://api.example.com/api/cameras/provision"


def test_provision_unit_strips_trailing_slash_from_api_base():
    captured = {}

    def fake_poster(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        return FakeResp(GOOD_BODY)

    provision_unit("https://api.example.com/", "secret", "hw-001", poster=fake_poster)
    assert captured["url"] == "https://api.example.com/api/cameras/provision"


def test_provision_unit_sends_bearer_auth_header():
    captured = {}

    def fake_poster(url, json=None, headers=None, timeout=None):
        captured["headers"] = headers
        return FakeResp(GOOD_BODY)

    provision_unit("https://api.example.com", "my-cron-secret", "hw-001", poster=fake_poster)
    assert captured["headers"]["Authorization"] == "Bearer my-cron-secret"


def test_provision_unit_sends_hardware_id_in_body():
    captured = {}

    def fake_poster(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return FakeResp(GOOD_BODY)

    provision_unit("https://api.example.com", "secret", "hw-xyz-001", poster=fake_poster)
    assert captured["json"]["hardware_id"] == "hw-xyz-001"


def test_provision_unit_sends_label_in_body_when_provided():
    captured = {}

    def fake_poster(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return FakeResp(GOOD_BODY)

    provision_unit(
        "https://api.example.com", "secret", "hw-001", label="bench-cam-1", poster=fake_poster
    )
    assert captured["json"]["label"] == "bench-cam-1"


def test_provision_unit_sends_none_label_when_not_provided():
    captured = {}

    def fake_poster(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return FakeResp(GOOD_BODY)

    provision_unit("https://api.example.com", "secret", "hw-001", poster=fake_poster)
    assert "label" in captured["json"]
    assert captured["json"]["label"] is None


def test_provision_unit_returns_three_fields():
    def fake_poster(url, json=None, headers=None, timeout=None):
        return FakeResp(GOOD_BODY)

    result = provision_unit("https://api.example.com", "secret", "hw-001", poster=fake_poster)
    assert result["camera_id"] == 1
    assert result["claim_code"] == "SUNSET-AAAA-BBBB"
    assert result["device_token"] == "tok-abc"


def test_provision_unit_propagates_http_errors():
    def fake_poster(url, json=None, headers=None, timeout=None):
        return FakeResp({}, raises=True)

    with pytest.raises(RuntimeError, match="http error"):
        provision_unit("https://api.example.com", "secret", "hw-001", poster=fake_poster)


def test_provision_unit_calls_raise_for_status_before_json():
    """raise_for_status must be called before json() to surface HTTP errors."""
    call_order = []

    class OrderTrackingResp:
        def raise_for_status(self):
            call_order.append("raise_for_status")

        def json(self):
            call_order.append("json")
            return GOOD_BODY

    def fake_poster(url, json=None, headers=None, timeout=None):
        return OrderTrackingResp()

    provision_unit("https://api.example.com", "secret", "hw-001", poster=fake_poster)
    assert call_order == ["raise_for_status", "json"]


def test_provision_unit_passes_timeout_to_poster():
    captured = {}

    def fake_poster(url, json=None, headers=None, timeout=None):
        captured["timeout"] = timeout
        return FakeResp(GOOD_BODY)

    provision_unit("https://api.example.com", "secret", "hw-001", poster=fake_poster, timeout_s=30.0)
    assert captured["timeout"] == 30.0
