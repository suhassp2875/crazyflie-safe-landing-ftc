#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from src.controllers.fault_aware_pinv_reference import (
    allocate_fault_aware_bounded,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--motor",
        type=int,
        required=True,
    )
    parser.add_argument(
        "--eta",
        type=float,
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--tolerance-pwm",
        type=float,
        default=5.0,
    )
    args = parser.parse_args()

    if args.motor not in (1, 2, 3, 4):
        raise SystemExit("--motor must be 1, 2, 3, or 4")

    rows = read_csv(args.input)

    accepted_fault_phases = {
        "fault",
        "fault_active",
    }

    fault_rows = [
        row
        for row in rows
        if row.get("phase") in accepted_fault_phases
    ]

    if not fault_rows:
        raise SystemExit("[FAIL] No fault-phase rows found")

    comparison_rows: list[dict[str, object]] = []
    active_rows = 0
    transition_rows = 0

    overall_max_difference = 0.0
    exact_rows = 0
    mask_match_rows = 0

    per_motor_differences: dict[int, list[float]] = {
        motor: []
        for motor in range(1, 5)
    }

    weights = np.array(
        [1.0, 1.0, 1.0, 0.20],
        dtype=float,
    )

    for row_index, row in enumerate(fault_rows):
        nominal = np.array(
            [
                float(row[f"pinvAlloc.nom{motor}"])
                for motor in range(1, 5)
            ],
            dtype=float,
        )

        firmware = np.array(
            [
                float(row[f"pinvAlloc.alloc{motor}"])
                for motor in range(1, 5)
            ],
            dtype=float,
        )

        firmware_mask = int(
            float(row["pinvAlloc.active"])
        )

        command_changed = bool(
            np.any(np.abs(firmware - nominal) > 1.0)
        )

        allocator_engaged = (
            firmware_mask != 0
            or command_changed
        )

        if not allocator_engaged:
            transition_rows += 1
            continue

        active_rows += 1

        reference = allocate_fault_aware_bounded(
            nominal_pwm=nominal,
            fault_motor=args.motor,
            eta=args.eta,
            weights=weights,
            regularization=1.0e-6,
        )

        # Firmware conversion from float to uint16_t truncates
        # positive values toward zero.
        expected = np.trunc(
            np.clip(
                reference.requested_pwm,
                0.0,
                65535.0,
            )
        )

        difference = np.abs(firmware - expected)

        reference_mask = 0

        for motor_index, is_active in enumerate(
            reference.clipped
        ):
            if bool(is_active):
                reference_mask |= 1 << motor_index

        row_max_difference = float(np.max(difference))
        overall_max_difference = max(
            overall_max_difference,
            row_max_difference,
        )

        if np.all(difference == 0.0):
            exact_rows += 1

        if firmware_mask == reference_mask:
            mask_match_rows += 1

        for motor_index in range(4):
            per_motor_differences[motor_index + 1].append(
                float(difference[motor_index])
            )

        output_row: dict[str, object] = {
            "row_index": row_index,
            "firmware_timestamp_ms": row.get(
                "firmware_timestamp_ms",
                "",
            ),
            "firmware_active_mask": firmware_mask,
            "reference_active_mask": reference_mask,
            "max_abs_pwm_difference": row_max_difference,
        }

        for motor_index in range(4):
            motor = motor_index + 1

            output_row[f"nominal_m{motor}"] = (
                nominal[motor_index]
            )
            output_row[f"firmware_m{motor}"] = (
                firmware[motor_index]
            )
            output_row[f"reference_m{motor}"] = (
                expected[motor_index]
            )
            output_row[f"abs_difference_m{motor}"] = (
                difference[motor_index]
            )

        comparison_rows.append(output_row)

    if not comparison_rows:
        raise SystemExit(
            "[FAIL] No allocator-engaged fault rows found"
        )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with args.output.open("w", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(comparison_rows[0].keys()),
        )
        writer.writeheader()
        writer.writerows(comparison_rows)

    print(
        "\n========== FIRMWARE / REFERENCE PARITY =========="
    )
    print(f"total_fault_phase_rows={len(fault_rows)}")
    print(f"allocator_engaged_rows={active_rows}")
    print(f"transition_or_healthy_rows={transition_rows}")
    print(
        f"exact_command_match_rows="
        f"{exact_rows}/{active_rows}"
    )
    print(
        f"active_mask_match_rows="
        f"{mask_match_rows}/{active_rows}"
    )

    for motor in range(1, 5):
        values = np.asarray(
            per_motor_differences[motor],
            dtype=float,
        )

        print(
            f"motor={motor} "
            f"max_abs_difference_pwm={np.max(values):.3f} "
            f"mean_abs_difference_pwm={np.mean(values):.3f}"
        )

    print(
        f"overall_max_abs_difference_pwm="
        f"{overall_max_difference:.3f}"
    )
    print(f"[SAVED] {args.output}")

    passed = (
        overall_max_difference <= args.tolerance_pwm
        and mask_match_rows == active_rows
    )

    if not passed:
        raise SystemExit(
            "[FAIL] Firmware does not match the Python "
            "bounded-allocation reference."
        )

    print(
        "[PASS] Firmware matches the bounded-allocation reference."
    )


if __name__ == "__main__":
    main()
