"""Tests for the orientation sampler — uses an injected reader function
plus a fake clock to verify smoothing math without real I2C or real time."""
from __future__ import annotations

import time
from sunset_cam.orientation_sampler import OrientationSampler


def test_initial_sample_is_none():
    sampler = OrientationSampler(reader=lambda: (0.0, 0.0))
    assert sampler.latest() is None


def test_sample_once_caches_the_value():
    sampler = OrientationSampler(reader=lambda: (1.0, 2.0))
    sampler.sample_once()
    latest = sampler.latest()
    assert latest is not None
    assert latest["roll_deg"] == 1.0
    assert latest["pitch_deg"] == 2.0
    assert "sampled_at" in latest


def test_smoothing_with_default_alpha():
    # alpha = 0.3 → first sample is the seed; second is 0.3*new + 0.7*prev
    values = iter([(10.0, 0.0), (20.0, 0.0)])
    sampler = OrientationSampler(reader=lambda: next(values), alpha=0.3)

    sampler.sample_once()
    assert abs(sampler.latest()["roll_deg"] - 10.0) < 0.001

    sampler.sample_once()
    expected = 0.3 * 20.0 + 0.7 * 10.0  # = 13.0
    assert abs(sampler.latest()["roll_deg"] - expected) < 0.001


def test_sample_once_handles_reader_exception():
    # If the reader raises (e.g., I2C glitch), the cache stays at its
    # previous value rather than corrupting to None.
    sampler = OrientationSampler(reader=lambda: (5.0, 6.0))
    sampler.sample_once()
    sampled_before = sampler.latest()

    def broken_reader() -> tuple[float, float]:
        raise OSError("simulated I2C glitch")

    sampler._reader = broken_reader
    sampler.sample_once()  # Should not raise
    assert sampler.latest() == sampled_before


def test_start_stop_runs_sampling_loop():
    # Background thread samples a few times then we stop it.
    count = {"n": 0}

    def counting_reader() -> tuple[float, float]:
        count["n"] += 1
        return (0.0, 0.0)

    sampler = OrientationSampler(reader=counting_reader, hz=50)
    sampler.start()
    time.sleep(0.1)  # ~5 samples at 50 Hz
    sampler.stop()
    assert count["n"] >= 2
