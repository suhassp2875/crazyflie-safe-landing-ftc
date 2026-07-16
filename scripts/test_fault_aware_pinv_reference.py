#!/usr/bin/env python3

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np

from src.controllers.fault_aware_pinv_reference import (
    MIXER_EFFECTIVENESS,
    allocate_fault_aware_pinv,
    legacy_mix,
)


def assert_close(
    actual,
    expected,
    tolerance: float,
    message: str,
):
    actual = np.asarray(actual, dtype=float)
    expected = np.asarray(expected, dtype=float)

    error = float(np.max(np.abs(actual - expected)))

    if error > tolerance:
        raise AssertionError(
            f"{message}: max error={error}, "
            f"actual={actual}, expected={expected}"
        )


def test_legacy_mixer_matrix():
    u = legacy_mix(
        thrust=32000.0,
        roll_command=1200.0,
        pitch_command=-800.0,
        yaw_command=250.0,
    )

    reconstructed = MIXER_EFFECTIVENESS @ u

    expected = np.array(
        [
            4.0 * 32000.0,
            4.0 * (1200.0 / 2.0),
            4.0 * (-800.0 / 2.0),
            4.0 * 250.0,
        ],
        dtype=float,
    )

    assert_close(
        reconstructed,
        expected,
        tolerance=1e-8,
        message="Legacy mixer matrix convention mismatch",
    )


def test_healthy_invariance():
    test_vectors = [
        np.array([32000.0, 32000.0, 32000.0, 32000.0]),
        np.array([30000.0, 31000.0, 32000.0, 33000.0]),
        legacy_mix(33000.0, 1500.0, -900.0, 300.0),
    ]

    for fault_motor in (1, 2, 3, 4):
        for u0 in test_vectors:
            result = allocate_fault_aware_pinv(
                nominal_pwm=u0,
                fault_motor=fault_motor,
                eta=1.0,
            )

            assert_close(
                result.requested_pwm,
                u0,
                tolerance=1e-5,
                message=(
                    "Healthy eta=1 allocation did not reproduce "
                    f"nominal mixer for motor {fault_motor}"
                ),
            )

            assert_close(
                result.achieved_generalized,
                result.desired_generalized,
                tolerance=1e-5,
                message=(
                    "Healthy eta=1 generalized command changed "
                    f"for motor {fault_motor}"
                ),
            )


def test_fault_compensation_unclipped():
    u0 = np.array(
        [20000.0, 20000.0, 20000.0, 20000.0],
        dtype=float,
    )

    for fault_motor in (1, 2, 3, 4):
        result = allocate_fault_aware_pinv(
            nominal_pwm=u0,
            fault_motor=fault_motor,
            eta=0.8,
            regularization=1e-10,
        )

        if np.any(result.clipped):
            raise AssertionError(
                "Unexpected clipping in low-command compensation test"
            )

        assert_close(
            result.achieved_generalized,
            result.desired_generalized,
            tolerance=1e-2,
            message=(
                "Unclipped allocator failed to preserve generalized "
                f"command for motor {fault_motor}"
            ),
        )


def print_boundary_example():
    u0 = np.array(
        [32500.0, 32700.0, 32600.0, 32800.0],
        dtype=float,
    )

    print("\n[BOUNDARY EXAMPLES AT ETA=0.496]")

    for fault_motor in (1, 2, 3, 4):
        result = allocate_fault_aware_pinv(
            nominal_pwm=u0,
            fault_motor=fault_motor,
            eta=0.496,
        )

        print(
            f"motor={fault_motor} "
            f"requested={np.round(result.requested_pwm, 2)} "
            f"applied={np.round(result.applied_pwm, 2)} "
            f"clipped={result.clipped.astype(int)} "
            f"error={np.round(result.generalized_error, 2)}"
        )


def main():
    test_legacy_mixer_matrix()
    print("[PASS] Legacy mixer matrix convention")

    test_healthy_invariance()
    print("[PASS] eta=1 healthy invariance")

    test_fault_compensation_unclipped()
    print("[PASS] Unclipped fault compensation")

    print_boundary_example()

    print("\n[DONE] Fault-aware pseudo-inverse reference tests passed.")


if __name__ == "__main__":
    main()
