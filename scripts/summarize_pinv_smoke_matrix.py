#!/usr/bin/env python3

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path("results/final/pinv_baseline/smoke")
OUTPUT = ROOT / "all_motors_eta0p496_summary.csv"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def selected_rows(
    rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row.get("phase") == "fault_active"
    ]


def summarize(motor: int) -> dict[str, object]:
    directory = ROOT / f"motor{motor}_eta0p496"

    motor_rows = selected_rows(
        read_rows(directory / "motor_samples.csv")
    )
    error_rows = selected_rows(
        read_rows(directory / "error_samples.csv")
    )
    state_rows = selected_rows(
        read_rows(directory / "state_samples.csv")
    )

    if not motor_rows or not error_rows or not state_rows:
        raise RuntimeError(
            f"Missing fault_active samples for motor {motor}"
        )

    command_key = f"pinvAlloc.alloc{motor}"

    return {
        "motor": motor,
        "eta": 0.496,
        "motor_samples": len(motor_rows),
        "error_samples": len(error_rows),
        "state_samples": len(state_rows),
        "max_fault_command": max(
            float(row[command_key])
            for row in motor_rows
        ),
        "saturation_fraction": sum(
            float(row[command_key]) >= 65535.0
            for row in motor_rows
        ) / len(motor_rows),
        "active_fraction": sum(
            float(row["pinvAlloc.active"]) != 0.0
            for row in motor_rows
        ) / len(motor_rows),
        "minimum_altitude_m": min(
            float(row["stateEstimate.z"])
            for row in state_rows
        ),
        "maximum_tilt_deg": max(
            max(
                abs(float(row["stateEstimate.roll"])),
                abs(float(row["stateEstimate.pitch"])),
            )
            for row in state_rows
        ),
        "max_abs_err_thrust": max(
            abs(float(row["pinvAlloc.errT"]))
            for row in error_rows
        ),
        "max_abs_err_roll": max(
            abs(float(row["pinvAlloc.errR"]))
            for row in error_rows
        ),
        "max_abs_err_pitch": max(
            abs(float(row["pinvAlloc.errP"]))
            for row in error_rows
        ),
        "max_abs_err_yaw": max(
            abs(float(row["pinvAlloc.errY"]))
            for row in error_rows
        ),
        "max_objective": max(
            float(row["pinvAlloc.objective"])
            for row in error_rows
        ),
    }


summaries = [summarize(motor) for motor in (1, 2, 3, 4)]

with OUTPUT.open("w", newline="") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=list(summaries[0].keys()),
    )
    writer.writeheader()
    writer.writerows(summaries)

print("========== PINV FOUR-MOTOR SMOKE MATRIX ==========")

for row in summaries:
    print(
        f"M{row['motor']}: "
        f"samples={row['motor_samples']} "
        f"sat={row['saturation_fraction']:.3f} "
        f"active={row['active_fraction']:.3f} "
        f"min_z={row['minimum_altitude_m']:.4f} "
        f"tilt={row['maximum_tilt_deg']:.4f} "
        f"errT={row['max_abs_err_thrust']:.2f} "
        f"errY={row['max_abs_err_yaw']:.2f} "
        f"objective={row['max_objective']:.2f}"
    )

print(f"[SAVED] {OUTPUT}")
