"""Tests for the MPU6050 driver — mocked I2C inputs."""
from __future__ import annotations

import math
from sunset_cam.gyro_driver import read_orientation, accel_to_roll_pitch


def test_accel_to_roll_pitch_returns_zero_when_flat():
    # Phone flat: gravity is entirely along Z axis.
    roll, pitch = accel_to_roll_pitch(0.0, 0.0, 1.0)
    assert abs(roll) < 0.1
    assert abs(pitch) < 0.1


def test_accel_to_roll_pitch_returns_90_when_on_right_side():
    # Phone on its right side: gravity along +Y → roll = 90°.
    roll, pitch = accel_to_roll_pitch(0.0, 1.0, 0.0)
    assert abs(roll - 90.0) < 0.5


def test_accel_to_roll_pitch_returns_negative_90_when_on_left_side():
    roll, pitch = accel_to_roll_pitch(0.0, -1.0, 0.0)
    assert abs(roll - (-90.0)) < 0.5


def test_accel_to_roll_pitch_pitch_when_tilted_forward():
    # Phone tilted forward: gravity along +X → pitch ≈ -90°.
    roll, pitch = accel_to_roll_pitch(1.0, 0.0, 0.0)
    assert abs(pitch - (-90.0)) < 0.5


def test_accel_to_roll_pitch_returns_180_or_negative_180_upside_down():
    # Phone upside down: gravity along -Z. Roll wraps to ±180°.
    roll, pitch = accel_to_roll_pitch(0.0, 0.0, -1.0)
    assert abs(abs(roll) - 180.0) < 0.5


def test_read_orientation_calls_smbus_with_correct_address():
    # MPU6050 default address 0x68; accel registers start at 0x3B.
    # The driver should issue an I2C read for 6 bytes starting at 0x3B.
    calls = []

    class FakeBus:
        def read_i2c_block_data(self, addr, reg, length):
            calls.append((addr, reg, length))
            # 6 bytes of raw accel: 0x00 0x00 0x00 0x00 0x40 0x00
            # → x=0, y=0, z=16384 (=1g for ±2g full scale)
            return [0x00, 0x00, 0x00, 0x00, 0x40, 0x00]

    bus = FakeBus()
    roll, pitch = read_orientation(bus)

    assert calls == [(0x68, 0x3B, 6)]
    assert abs(roll) < 0.1
    assert abs(pitch) < 0.1


def test_read_orientation_handles_negative_raw_values():
    # Two's-complement: raw=0xFFFF means -1, raw=0xC000 = -16384 (=-1g).
    class FakeBus:
        def read_i2c_block_data(self, addr, reg, length):
            # x=0, y=0, z=-16384 → upside down
            return [0x00, 0x00, 0x00, 0x00, 0xC0, 0x00]

    bus = FakeBus()
    roll, pitch = read_orientation(bus)
    assert abs(abs(roll) - 180.0) < 0.5
