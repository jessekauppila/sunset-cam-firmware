from datetime import datetime, timezone

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
