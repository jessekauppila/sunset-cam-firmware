from datetime import datetime, timezone

import pytest
import responses

from sunset_cam.upload import upload_snapshot


def base_cfg() -> dict:
    return {
        "camera_id": 42,
        "device_token": "tok-abc",
        "api_base": "https://sunrisesunset.studio",
        "phase": "sunset",
        "window_id": "2026-05-03-sunset-cam42",
    }


@responses.activate
def test_upload_posts_to_correct_url_with_bearer() -> None:
    responses.add(
        responses.POST,
        "https://sunrisesunset.studio/api/cameras/42/snapshot",
        json={"snapshot_id": 78901, "accepted_at": "2026-05-03T01:32:14Z"},
        status=202,
    )

    captured_at = datetime(2026, 5, 3, 1, 32, 14, tzinfo=timezone.utc)
    result = upload_snapshot(base_cfg(), b"jpeg-bytes", captured_at)

    assert result["snapshot_id"] == 78901
    assert len(responses.calls) == 1
    call = responses.calls[0]
    assert call.request.headers["Authorization"] == "Bearer tok-abc"
    body = call.request.body
    if isinstance(body, bytes):
        body = body.decode("latin-1")
    assert "captured_at" in body
    assert "phase" in body
    assert "window_id" in body
    assert "image" in body
    assert "jpeg-bytes" in body


@responses.activate
def test_upload_raises_on_http_error() -> None:
    responses.add(
        responses.POST,
        "https://sunrisesunset.studio/api/cameras/42/snapshot",
        json={"error": "unauthorized"},
        status=401,
    )

    captured_at = datetime(2026, 5, 3, 1, 32, 14, tzinfo=timezone.utc)
    try:
        upload_snapshot(base_cfg(), b"jpeg-bytes", captured_at)
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError on 401")


# --- welkin sink + dispatch -------------------------------------------------

from sunset_cam.profiles import profiles_from_config  # noqa: E402
from sunset_cam.upload import send_frame, upload_frame  # noqa: E402


@responses.activate
def test_upload_frame_posts_raw_jpeg_with_headers() -> None:
    responses.add(
        responses.POST,
        "http://192.168.1.20:8000/frames/7",
        json={"frame_id": "7/2026-09-18T20:05:00Z"},
        status=201,
    )
    captured_at = datetime(2026, 9, 18, 20, 5, 0, tzinfo=timezone.utc)
    ack = upload_frame(
        "http://192.168.1.20:8000/", 7, b"\xff\xd8jpeg", captured_at, profile="clouds", token="s3cret"
    )
    assert ack == {"frame_id": "7/2026-09-18T20:05:00Z"}
    req = responses.calls[0].request
    assert req.body == b"\xff\xd8jpeg"
    assert req.headers["Content-Type"] == "image/jpeg"
    assert req.headers["X-Captured-At"] == "2026-09-18T20:05:00Z"
    assert req.headers["X-Profile"] == "clouds"
    assert req.headers["Authorization"] == "Bearer s3cret"


@responses.activate
def test_upload_frame_omits_auth_without_token_and_tolerates_empty_body() -> None:
    responses.add(responses.POST, "http://h:8000/frames/7", body="", status=204)
    captured_at = datetime(2026, 9, 18, 20, 5, 0, tzinfo=timezone.utc)
    assert upload_frame("http://h:8000", 7, b"j", captured_at, profile="clouds") == {}
    assert "Authorization" not in responses.calls[0].request.headers


@responses.activate
def test_upload_frame_raises_on_http_error() -> None:
    responses.add(responses.POST, "http://h:8000/frames/7", body="nope", status=500)
    captured_at = datetime(2026, 9, 18, 20, 5, 0, tzinfo=timezone.utc)
    with pytest.raises(RuntimeError, match="500"):
        upload_frame("http://h:8000", 7, b"j", captured_at, profile="clouds")


@responses.activate
def test_send_frame_routes_a_cloud_profile_to_welkin_not_sunset() -> None:
    responses.add(responses.POST, "http://h:8000/frames/7", json={}, status=201)
    cfg = {
        "camera_id": 7,
        "profiles": [
            {
                "name": "clouds",
                "window": {"daily_utc": {"start": "16:00", "end": "01:00"}},
                "interval_s": 300,
                "sink": {"kind": "welkin", "url": "http://h:8000"},
            }
        ],
    }
    [profile] = profiles_from_config(cfg)
    send_frame(cfg, profile, b"j", datetime(2026, 9, 18, 20, 5, tzinfo=timezone.utc))
    assert [c.request.url for c in responses.calls] == ["http://h:8000/frames/7"]


@responses.activate
def test_send_frame_routes_a_sunset_profile_with_the_sinks_phase() -> None:
    responses.add(
        responses.POST,
        "https://sunrisesunset.studio/api/cameras/42/snapshot",
        json={"snapshot_id": 1, "accepted_at": "2026-05-03T01:32:14Z"},
        status=202,
    )
    cfg = {**base_cfg(), "profiles": [
        {
            "name": "dawn",
            "window": {"daily_utc": {"start": "12:00", "end": "14:00"}},
            "interval_s": 1,
            "sink": {"kind": "sunset", "phase": "sunrise", "window_id": "dawn-1"},
        }
    ]}
    [profile] = profiles_from_config(cfg)
    ack = send_frame(cfg, profile, b"j", datetime(2026, 5, 3, 13, tzinfo=timezone.utc))
    assert ack["snapshot_id"] == 1
    body = responses.calls[0].request.body
    body = body.decode("latin-1") if isinstance(body, bytes) else body
    assert "sunrise" in body and "dawn-1" in body
