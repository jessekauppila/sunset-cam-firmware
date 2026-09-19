"""capture.py against a fake picamera2 that behaves like the real one where it
matters: stop() leaves the device acquired, only close() releases it, and a
second Picamera2() while one is still acquired fails. Runs on a Mac."""

import sys
import types

import pytest

from sunset_cam import capture


class FakeLibcamera:
    acquired_by: object | None = None


class FakePicamera2:
    instances: list["FakePicamera2"] = []

    def __init__(self) -> None:
        if FakeLibcamera.acquired_by is not None:
            raise RuntimeError("Camera __init__ sequence did not complete.")
        FakeLibcamera.acquired_by = self
        self.started = False
        self.closed = False
        self.captures = 0
        FakePicamera2.instances.append(self)

    def create_still_configuration(self, main: dict) -> dict:
        return {"main": main}

    def configure(self, cfg: dict) -> None:
        self.cfg = cfg

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False  # does NOT release the device, as in picamera2

    def close(self) -> None:
        self.stop()
        self.closed = True
        FakeLibcamera.acquired_by = None

    def capture_file(self, buf, format: str) -> None:
        self.captures += 1
        buf.write(b"\xff\xd8fake\xff\xd9")


@pytest.fixture
def fake_picamera2(monkeypatch: pytest.MonkeyPatch):
    FakeLibcamera.acquired_by = None
    FakePicamera2.instances = []
    mod = types.ModuleType("picamera2")
    mod.Picamera2 = FakePicamera2
    monkeypatch.setitem(sys.modules, "picamera2", mod)
    monkeypatch.setattr(capture, "_camera", None)
    monkeypatch.setattr(capture, "WARMUP_S", 0.0)
    yield mod
    capture.shutdown()


def test_release_then_reacquire_works_across_a_window_gap(fake_picamera2) -> None:
    # Window 1
    assert capture.capture_jpeg().startswith(b"\xff\xd8")
    first = FakePicamera2.instances[0]
    # Idle between windows: the loop releases the camera.
    capture.shutdown()
    assert first.closed is True
    assert FakeLibcamera.acquired_by is None
    # Window 2, next day: must reopen cleanly (this is the P0 the review found).
    assert capture.capture_jpeg().startswith(b"\xff\xd8")
    assert len(FakePicamera2.instances) == 2


def test_a_stop_only_release_would_have_wedged_the_device(fake_picamera2) -> None:
    # Documents why shutdown() must call close(): with the picamera2 semantics
    # above, stop() alone leaves the device acquired and the next open fails.
    capture.capture_jpeg()
    cam = FakePicamera2.instances[0]
    cam.stop()
    with pytest.raises(RuntimeError, match="did not complete"):
        FakePicamera2()


def test_capture_reuses_the_open_camera_within_a_window(fake_picamera2) -> None:
    capture.capture_jpeg()
    capture.capture_jpeg()
    assert len(FakePicamera2.instances) == 1
    assert FakePicamera2.instances[0].captures == 2


def test_shutdown_is_safe_when_nothing_is_open(fake_picamera2) -> None:
    capture.shutdown()
    capture.shutdown()
    assert FakePicamera2.instances == []


def test_shutdown_swallows_close_errors_and_still_forgets_the_camera(fake_picamera2, monkeypatch) -> None:
    capture.capture_jpeg()
    cam = FakePicamera2.instances[0]

    def boom() -> None:
        raise OSError("device gone")

    monkeypatch.setattr(cam, "close", boom)
    capture.shutdown()
    assert capture._camera is None


def test_start_waits_for_exposure_to_settle(fake_picamera2, monkeypatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr(capture, "WARMUP_S", 1.5)
    monkeypatch.setattr(capture.time, "sleep", lambda s: slept.append(s))
    capture.capture_jpeg()
    assert slept == [1.5]
    capture.capture_jpeg()
    assert slept == [1.5]  # only on open, not per frame
