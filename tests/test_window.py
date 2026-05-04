from datetime import datetime, timezone

from sunset_cam.window import is_active_now


def cfg(start: str, end: str) -> dict:
    return {
        "capture_window_start_utc": start,
        "capture_window_end_utc": end,
    }


def test_returns_false_before_window() -> None:
    c = cfg("2026-05-03T01:00:00Z", "2026-05-03T02:00:00Z")
    now = datetime(2026, 5, 3, 0, 59, 59, tzinfo=timezone.utc)
    assert is_active_now(c, now) is False


def test_returns_true_inside_window() -> None:
    c = cfg("2026-05-03T01:00:00Z", "2026-05-03T02:00:00Z")
    now = datetime(2026, 5, 3, 1, 30, 0, tzinfo=timezone.utc)
    assert is_active_now(c, now) is True


def test_returns_false_after_window() -> None:
    c = cfg("2026-05-03T01:00:00Z", "2026-05-03T02:00:00Z")
    now = datetime(2026, 5, 3, 2, 0, 1, tzinfo=timezone.utc)
    assert is_active_now(c, now) is False


def test_window_endpoints_are_inclusive_at_start_exclusive_at_end() -> None:
    c = cfg("2026-05-03T01:00:00Z", "2026-05-03T02:00:00Z")
    start = datetime(2026, 5, 3, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 3, 2, 0, 0, tzinfo=timezone.utc)
    assert is_active_now(c, start) is True
    assert is_active_now(c, end) is False


def test_naive_datetime_is_rejected() -> None:
    c = cfg("2026-05-03T01:00:00Z", "2026-05-03T02:00:00Z")
    naive = datetime(2026, 5, 3, 1, 30, 0)
    try:
        is_active_now(c, naive)
    except ValueError:
        return
    raise AssertionError("expected ValueError for naive datetime")
