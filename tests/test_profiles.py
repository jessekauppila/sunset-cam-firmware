from datetime import datetime, time, timezone

import pytest

from sunset_cam.profiles import (
    AbsoluteWindow,
    DailyWindow,
    ProfileError,
    active_profile,
    idle_poll_s,
    next_tick,
    profiles_from_config,
)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def legacy_cfg() -> dict:
    return {
        "camera_id": 42,
        "device_token": "tok",
        "api_base": "https://sunrisesunset.studio",
        "phase": "sunset",
        "window_id": "w1",
        "capture_window_start_utc": "2026-05-03T01:00:00Z",
        "capture_window_end_utc": "2026-05-03T02:30:00Z",
        "capture_interval_s": 1.0,
    }


def clouds(**over: object) -> dict:
    p = {
        "name": "clouds",
        "window": {"daily_utc": {"start": "16:00", "end": "01:00"}},
        "interval_s": 300,
        "sink": {"kind": "welkin", "url": "http://192.168.1.20:8000"},
    }
    p.update(over)
    return p


def sunset_profile(**over: object) -> dict:
    p = {
        "name": "sunset",
        "window": {"daily_utc": {"start": "02:00", "end": "04:00"}},
        "interval_s": 1.0,
        "sink": {"kind": "sunset", "phase": "sunset", "window_id": "w1"},
    }
    p.update(over)
    return p


# --- legacy configs -------------------------------------------------------


def test_legacy_config_becomes_one_sunset_profile_with_todays_behaviour() -> None:
    [p] = profiles_from_config(legacy_cfg())
    assert p.name == "sunset"
    assert p.interval_s == 1.0
    assert p.sink == {"kind": "sunset", "phase": "sunset", "window_id": "w1"}
    # Today's loop sleeps a fixed interval after each capture; keep that.
    assert p.align_to_clock is False
    assert isinstance(p.window, AbsoluteWindow)
    assert p.is_active(utc(2026, 5, 3, 1, 30)) is True
    assert p.is_active(utc(2026, 5, 3, 2, 30)) is False


# --- windows --------------------------------------------------------------


def test_daily_window_repeats_every_day() -> None:
    w = DailyWindow(start=time(9, 0), end=time(17, 0))
    assert w.contains(utc(2026, 9, 18, 12, 0)) is True
    assert w.contains(utc(2027, 1, 2, 12, 0)) is True
    assert w.contains(utc(2026, 9, 18, 8, 59)) is False


def test_daily_window_wraps_midnight() -> None:
    # Pacific daytime is 16:00 -> 01:00 UTC.
    w = DailyWindow(start=time(16, 0), end=time(1, 0))
    assert w.contains(utc(2026, 9, 18, 20, 0)) is True
    assert w.contains(utc(2026, 9, 19, 0, 30)) is True
    assert w.contains(utc(2026, 9, 19, 1, 0)) is False
    assert w.contains(utc(2026, 9, 19, 12, 0)) is False


def test_daily_window_is_start_inclusive_end_exclusive() -> None:
    w = DailyWindow(start=time(9, 0), end=time(17, 0))
    assert w.contains(utc(2026, 9, 18, 9, 0)) is True
    assert w.contains(utc(2026, 9, 18, 17, 0)) is False


def test_daily_window_converts_non_utc_now() -> None:
    from datetime import timedelta

    pacific = timezone(timedelta(hours=-7))
    w = DailyWindow(start=time(16, 0), end=time(1, 0))
    # 10:00 PDT == 17:00 UTC
    assert w.contains(datetime(2026, 9, 18, 10, 0, tzinfo=pacific)) is True


def test_naive_now_is_rejected() -> None:
    [p] = profiles_from_config({"camera_id": 1, "profiles": [clouds()]})
    with pytest.raises(ValueError):
        p.is_active(datetime(2026, 9, 18, 20, 0))


# --- parsing and validation -----------------------------------------------


def test_parses_a_cloud_profile() -> None:
    [p] = profiles_from_config({"camera_id": 1, "profiles": [clouds()]})
    assert p.name == "clouds"
    assert p.interval_s == 300.0
    assert p.align_to_clock is True
    assert p.window == DailyWindow(start=time(16, 0), end=time(1, 0))
    assert p.sink["url"] == "http://192.168.1.20:8000"


def test_parses_an_absolute_window() -> None:
    prof = clouds(
        window={"absolute_utc": {"start": "2026-09-20T16:00:00Z", "end": "2026-09-20T20:00:00Z"}}
    )
    [p] = profiles_from_config({"camera_id": 1, "profiles": [prof]})
    assert p.is_active(utc(2026, 9, 20, 17, 0)) is True
    assert p.is_active(utc(2026, 9, 21, 17, 0)) is False


@pytest.mark.parametrize(
    "bad, match",
    [
        ({"name": ""}, "name"),
        ({"interval_s": 0}, "interval_s"),
        ({"interval_s": "300"}, "interval_s"),
        ({"window": {"weekly": {}}}, "window"),
        ({"window": {"daily_utc": {"start": "25:00", "end": "01:00"}}}, "HH:MM"),
        ({"window": {"daily_utc": {"start": "16:00", "end": "16:00"}}}, "empty"),
        ({"window": {"absolute_utc": {"start": "2026-09-20T20:00:00Z", "end": "2026-09-20T16:00:00Z"}}}, "after"),
        ({"sink": {"kind": "ftp"}}, "sink"),
        ({"sink": {"kind": "welkin"}}, "url"),
        ({"sink": {"kind": "welkin", "url": "192.168.1.20:8000"}}, "http"),
        ({"align_to_clock": "yes"}, "align_to_clock"),
    ],
)
def test_rejects_invalid_profiles(bad: dict, match: str) -> None:
    with pytest.raises(ProfileError, match=match):
        profiles_from_config({"camera_id": 1, "profiles": [clouds(**bad)]})


def test_rejects_empty_profile_list() -> None:
    with pytest.raises(ProfileError, match="at least one"):
        profiles_from_config({"camera_id": 1, "profiles": []})


def test_rejects_duplicate_names() -> None:
    with pytest.raises(ProfileError, match="duplicate"):
        profiles_from_config(
            {"camera_id": 1, "profiles": [clouds(), clouds(window={"daily_utc": {"start": "02:00", "end": "03:00"}})]}
        )


def test_rejects_overlapping_daily_windows() -> None:
    # 16:00->01:00 and 00:30->02:00 overlap across midnight.
    other = sunset_profile(window={"daily_utc": {"start": "00:30", "end": "02:00"}})
    cfg = {"camera_id": 1, "api_base": "https://x", "device_token": "t", "profiles": [clouds(), other]}
    with pytest.raises(ProfileError, match="overlap"):
        profiles_from_config(cfg)


def test_sunset_sink_requires_identity_and_phase() -> None:
    with pytest.raises(ProfileError, match="api_base"):
        profiles_from_config({"camera_id": 1, "profiles": [sunset_profile()]})
    with pytest.raises(ProfileError, match="phase"):
        profiles_from_config(
            {
                "camera_id": 1,
                "api_base": "https://x",
                "device_token": "t",
                "profiles": [sunset_profile(sink={"kind": "sunset", "phase": "noon", "window_id": "w"})],
            }
        )


def test_cloud_only_config_needs_no_sunset_identity() -> None:
    # A Welkin cloud camera never talks to the sunset app.
    profiles_from_config({"camera_id": 1, "profiles": [clouds()]})


# --- choosing and timing --------------------------------------------------


def test_active_profile_picks_the_one_whose_window_is_open() -> None:
    cfg = {"camera_id": 1, "api_base": "https://x", "device_token": "t", "profiles": [clouds(), sunset_profile()]}
    profiles = profiles_from_config(cfg)
    assert active_profile(profiles, utc(2026, 9, 18, 20, 0)).name == "clouds"
    assert active_profile(profiles, utc(2026, 9, 18, 3, 0)).name == "sunset"
    assert active_profile(profiles, utc(2026, 9, 18, 12, 0)) is None


def test_next_tick_aligns_to_the_clock() -> None:
    assert next_tick(utc(2026, 9, 18, 12, 3, 17), 300) == utc(2026, 9, 18, 12, 5, 0)
    assert next_tick(utc(2026, 9, 18, 12, 5, 0), 300) == utc(2026, 9, 18, 12, 10, 0)
    assert next_tick(utc(2026, 9, 18, 23, 58, 0), 600) == utc(2026, 9, 19, 0, 0, 0)


def test_idle_poll_is_capped_and_independent_of_cadence() -> None:
    # A 1 s legacy profile must not make the idle loop spin once a second all day.
    assert idle_poll_s(profiles_from_config(legacy_cfg())) == 30.0
    assert idle_poll_s(profiles_from_config({"camera_id": 1, "profiles": [clouds()]})) == 30.0
    # Legacy absolute window: before it opens, sleep to the opening (capped).
    [legacy] = profiles_from_config(legacy_cfg())
    assert idle_poll_s([legacy], utc(2026, 5, 3, 0, 59, 50)) == pytest.approx(10.0)
    # After it has closed for good there is nothing to wait for: cap.
    assert idle_poll_s([legacy], utc(2026, 5, 4, 0, 0)) == 30.0


# --- window boundaries and window-aware sleeps (review findings 2) ------------

from sunset_cam.profiles import seconds_until_next_capture  # noqa: E402


def test_daily_window_next_boundary_is_end_when_inside_and_start_when_outside() -> None:
    w = DailyWindow(start=time(16, 0), end=time(1, 0))
    assert w.next_boundary(utc(2026, 9, 18, 20, 0)) == utc(2026, 9, 19, 1, 0)
    assert w.next_boundary(utc(2026, 9, 19, 0, 30)) == utc(2026, 9, 19, 1, 0)
    assert w.next_boundary(utc(2026, 9, 19, 1, 0)) == utc(2026, 9, 19, 16, 0)
    assert w.next_boundary(utc(2026, 9, 19, 12, 0)) == utc(2026, 9, 19, 16, 0)


def test_absolute_window_next_boundary() -> None:
    w = AbsoluteWindow(start=utc(2026, 9, 20, 16, 0), end=utc(2026, 9, 20, 20, 0))
    assert w.next_boundary(utc(2026, 9, 20, 15, 0)) == utc(2026, 9, 20, 16, 0)
    assert w.next_boundary(utc(2026, 9, 20, 17, 0)) == utc(2026, 9, 20, 20, 0)
    assert w.next_boundary(utc(2026, 9, 20, 21, 0)) is None


def test_sleep_never_crosses_the_windows_end_even_when_the_cadence_would() -> None:
    # 420 s ticks land at 00:58:00 and 01:05:00; the window ends 01:00. The
    # loop must wake at 01:00 so a sunset profile starting then is not late.
    [p] = profiles_from_config({"camera_id": 1, "profiles": [clouds(interval_s=420)]})
    after_work = utc(2026, 9, 19, 0, 58, 2)
    assert seconds_until_next_capture(p, after_work) == pytest.approx(118.0)


def test_sleep_inside_the_window_is_the_aligned_tick() -> None:
    [p] = profiles_from_config({"camera_id": 1, "profiles": [clouds()]})
    assert seconds_until_next_capture(p, utc(2026, 9, 18, 20, 5, 2)) == pytest.approx(298.0)


def test_idle_poll_sleeps_exactly_to_the_next_opening_when_it_is_close() -> None:
    profiles = profiles_from_config({"camera_id": 1, "profiles": [clouds()]})
    assert idle_poll_s(profiles, utc(2026, 9, 18, 15, 59, 45)) == pytest.approx(15.0)
    assert idle_poll_s(profiles, utc(2026, 9, 18, 12, 0)) == 30.0
    assert idle_poll_s(profiles) == 30.0


def test_idle_poll_with_two_profiles_targets_the_earliest_opening() -> None:
    cfg = {"camera_id": 1, "api_base": "https://x", "device_token": "t", "profiles": [clouds(), sunset_profile()]}
    profiles = profiles_from_config(cfg)
    # Between 04:00 and 16:00 nothing is open; at 15:59:50 the clouds window is 10 s away.
    assert idle_poll_s(profiles, utc(2026, 9, 18, 15, 59, 50)) == pytest.approx(10.0)
