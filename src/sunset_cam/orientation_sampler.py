"""Background-thread orientation sampler.

Polls an injected reader callable at a fixed Hz, applies exponential
smoothing, caches the latest result for synchronous access via ``latest()``.

The reader is injected (not hard-coded to MPU6050) so the sampler can be
unit-tested with a deterministic fake reader and so future hardware ports
(ESP32, different IMU) don't need to fork this module.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional, Tuple


ReadingTuple = Tuple[float, float]  # (roll_deg, pitch_deg)


class OrientationSampler:
    """Polls a reader callable in a daemon thread; caches latest smoothed reading."""

    def __init__(
        self,
        reader: Callable[[], ReadingTuple],
        alpha: float = 0.3,
        hz: int = 10,
    ) -> None:
        self._reader = reader
        self._alpha = alpha
        self._period_s = 1.0 / hz
        self._smoothed: Optional[ReadingTuple] = None
        self._sampled_at: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def sample_once(self) -> None:
        """Take one reading and update the cache (synchronous; for tests)."""
        try:
            raw = self._reader()
        except Exception:
            return  # keep previous cache

        if self._smoothed is None:
            self._smoothed = raw
        else:
            r_prev, p_prev = self._smoothed
            r_new, p_new = raw
            self._smoothed = (
                self._alpha * r_new + (1.0 - self._alpha) * r_prev,
                self._alpha * p_new + (1.0 - self._alpha) * p_prev,
            )
        self._sampled_at = datetime.now(timezone.utc).isoformat()

    def latest(self) -> Optional[dict]:
        """Return the latest cached reading as a JSON-serializable dict, or None."""
        if self._smoothed is None:
            return None
        return {
            "roll_deg": self._smoothed[0],
            "pitch_deg": self._smoothed[1],
            "sampled_at": self._sampled_at,
        }

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.sample_once()
            self._stop_event.wait(timeout=self._period_s)
