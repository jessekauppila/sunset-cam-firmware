"""MPU6050 / GY-521 6-axis IMU driver.

Reads only the accelerometer for v0.2 (roll + pitch from the gravity vector).
The gyro is on the chip but unused — it's reserved for a future sun-tap
calibration spec.

Spec: docs/superpowers/specs/2026-05-17-pi-side-alignment-tool-design.md §5.4

Wiring (Pi Zero 2 W): VCC→3.3V, GND→GND, SDA→GPIO 2, SCL→GPIO 3.
I2C bus 1, address 0x68 (default — AD0 pin tied low).
"""
from __future__ import annotations

import math
from typing import Callable, Protocol, Tuple


MPU6050_ADDR = 0x68
ACCEL_XOUT_H = 0x3B  # first byte of 6 accel registers (X H, X L, Y H, Y L, Z H, Z L)
ACCEL_FS_LSB_PER_G = 16384.0  # ±2g full-scale → 16384 LSB / g
PWR_MGMT_1 = 0x6B  # power-management register; bit 6 (0x40) is SLEEP, set at power-on


class I2CBus(Protocol):
    """Minimal protocol matching the smbus2.SMBus methods this driver uses."""

    def read_i2c_block_data(self, addr: int, reg: int, length: int) -> list[int]: ...

    def write_byte_data(self, addr: int, reg: int, value: int) -> None: ...


def _u8_pair_to_i16(high: int, low: int) -> int:
    """Combine two unsigned bytes into a signed 16-bit integer (two's complement)."""
    raw = (high << 8) | low
    return raw - 0x10000 if raw & 0x8000 else raw


def accel_to_roll_pitch(ax: float, ay: float, az: float) -> Tuple[float, float]:
    """Convert accelerometer reading (in g, any consistent unit) to roll + pitch degrees.

    Pure function — no I/O. Uses the standard atan2-based gravity-vector formulas:
        roll  = atan2(ay, az)                  — rotation around forward axis
        pitch = atan2(-ax, sqrt(ay² + az²))    — rotation around right axis

    Using atan2(ay, az) for roll (rather than the sqrt form) gives the correct
    ±180° result when the device is upside-down (az < 0, ay = 0) and agrees with
    the sqrt form for all other orientations where az ≠ 0.
    Yaw is NOT recoverable from accelerometer alone (no horizontal reference).
    """
    roll_rad = math.atan2(ay, az)
    pitch_rad = math.atan2(-ax, math.sqrt(ay * ay + az * az))
    return math.degrees(roll_rad), math.degrees(pitch_rad)


def read_orientation(bus: I2CBus, addr: int = MPU6050_ADDR) -> Tuple[float, float]:
    """Read accelerometer once over I2C and return (roll_deg, pitch_deg)."""
    raw = bus.read_i2c_block_data(addr, ACCEL_XOUT_H, 6)
    ax_lsb = _u8_pair_to_i16(raw[0], raw[1])
    ay_lsb = _u8_pair_to_i16(raw[2], raw[3])
    az_lsb = _u8_pair_to_i16(raw[4], raw[5])

    ax_g = ax_lsb / ACCEL_FS_LSB_PER_G
    ay_g = ay_lsb / ACCEL_FS_LSB_PER_G
    az_g = az_lsb / ACCEL_FS_LSB_PER_G

    return accel_to_roll_pitch(ax_g, ay_g, az_g)


def wake(bus: I2CBus, addr: int = MPU6050_ADDR) -> None:
    """Clear the MPU6050 SLEEP bit so the accelerometer produces real data.

    The chip powers up with PWR_MGMT_1 = 0x40 (SLEEP set). Until it is cleared,
    every accel register reads 0 and read_orientation() returns a fake (0, 0).
    Call once after opening the bus, before reading.
    """
    bus.write_byte_data(addr, PWR_MGMT_1, 0x00)


def make_orientation_reader(
    bus: I2CBus, addr: int = MPU6050_ADDR
) -> Callable[[], Tuple[float, float]]:
    """Wake the MPU6050, then return a zero-arg reader for ``OrientationSampler``.

    The sampler takes an injected zero-arg reader and is deliberately unaware of
    the I2C bus. Wiring it with this factory guarantees the chip is awake before
    the first sample, so the sampler can never silently cache (0.0, 0.0) from a
    sleeping sensor — the bug this exists to prevent. Real Pi wiring is:

        bus = smbus2.SMBus(1)
        sampler = OrientationSampler(make_orientation_reader(bus))
    """
    wake(bus, addr)
    return lambda: read_orientation(bus, addr)
