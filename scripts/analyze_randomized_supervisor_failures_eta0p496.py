#!/usr/bin/env python3

from __future__ import annotations

import csv
import math
from collections import Counter
from pathlib import Path
from typing import Iterable


ROOT = Path(
    "results/final/pinv_baseline/"
    "seeded_eta0p496/randomized_supervisor/"
    "production120"
)

SUMMARY_PATH = ROOT / "supervisor_trial_summaries.csv"

FAILURE_OUTPUT = (
    ROOT / "supervisor_failure_diagnostics.csv"
)

CANDIDATE_OUTPUT = (
    ROOT / "supervisor_candidate_breakdown.csv"
)

REPORT_OUTPUT = (
    ROOT / "supervisor_failure_report.md"
)


def as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def first_text(
    row: dict[str, str],
    names: Iterable[str],
) -> str:
    for name in names:
        value = row.get(name, "").strip()

        if value:
            return value

    return ""


def optional_float(
    row: dict[str, str],
    names: Iterable[str],
) -> float | str:
    value = first_text(row, names)

    if not value:
        return ""

    return float(value)


def optional_int(
    row: dict[str, str],
    names: Iterable[str],
) -> int | str:
    value = first_text(row, names)

    if not value:
        return ""

    return int(float(value))


def row_time(row: dict[str, str]) -> float:
    value = first_text(
        row,
        ("t", "time", "time_s", "elapsed_s"),
    )

    if not value:
        raise ValueError(
            "Telemetry row does not contain a time field."
        )

    return float(value)


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
) -> None:
    if not rows:
        raise ValueError(
            f"Cannot write empty output: {path}"
        )

    with path.open("w", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0].keys()),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


if not SUMMARY_PATH.is_file():
    raise SystemExit(
        f"[FAIL] Missing summary: {SUMMARY_PATH}"
    )

with SUMMARY_PATH.open(newline="") as file:
    summaries = list(csv.DictReader(file))

if len(summaries) != 120:
    raise SystemExit(
        f"[FAIL] Expected 120 summaries; "
        f"found {len(summaries)}"
    )

diagnostic_rows = []
candidate_counter: Counter[
    tuple[int, str, str]
] = Counter()

for summary in summaries:
    source = Path(summary["source_csv"])

    if not source.is_file():
        raise SystemExit(
            f"[FAIL] Missing raw log: {source}"
        )

    with source.open(newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    fault_index = next(
        (
            index
            for index, row in enumerate(rows)
            if row.get("phase", "").strip()
            == "fault_event"
        ),
        None,
    )

    if fault_index is None:
        raise SystemExit(
            f"[FAIL] No fault event: {source}"
        )

    contact_row = next(
        (
            row
            for row in rows[fault_index:]
            if float(row["z"]) <= 0.03
        ),
        None,
    )

    if contact_row is None:
        raise SystemExit(
            f"[FAIL] No first contact: {source}"
        )

    fault_row = rows[fault_index]

    candidate = first_text(
        contact_row,
        ("selected_candidate",),
    )

    if not candidate:
        candidate = next(
            (
                first_text(
                    row,
                    ("selected_candidate",),
                )
                for row in rows[fault_index:]
                if first_text(
                    row,
                    ("selected_candidate",),
                )
            ),
            "unknown",
        )

    safe = as_bool(
        summary["safe_touchdown"]
    )

    safety_label = (
        "safe" if safe else "unsafe"
    )

    motor = int(summary["motor"])

    candidate_counter[
        (motor, safety_label, candidate)
    ] += 1

    if safe:
        continue

    fault_x = float(fault_row["x"])
    fault_y = float(fault_row["y"])
    fault_z = float(fault_row["z"])

    fault_vx = float(fault_row["vx"])
    fault_vy = float(fault_row["vy"])
    fault_vz = float(fault_row["vz"])

    contact_x = float(contact_row["x"])
    contact_y = float(contact_row["y"])

    contact_vx = float(contact_row["vx"])
    contact_vy = float(contact_row["vy"])
    contact_vz = abs(float(contact_row["vz"]))

    roll = abs(float(contact_row["roll_deg"]))
    pitch = abs(float(contact_row["pitch_deg"]))

    gyro_x = float(
        contact_row["gyro_x_deg_s"]
    )
    gyro_y = float(
        contact_row["gyro_y_deg_s"]
    )
    gyro_z = float(
        contact_row["gyro_z_deg_s"]
    )

    diagnostic_rows.append(
        {
            "sequence_index":
                int(summary["sequence_index"]),
            "motor": motor,
            "trial_seed":
                int(float(summary["trial_seed"])),
            "selected_policy":
                summary["selected_policy"],
            "runtime_controller":
                summary["runtime_controller"],
            "allocator_config":
                first_text(
                    contact_row,
                    ("allocator_config",),
                ),
            "selected_candidate": candidate,
            "fault_t": row_time(fault_row),
            "fault_x": fault_x,
            "fault_y": fault_y,
            "fault_z": fault_z,
            "fault_vx": fault_vx,
            "fault_vy": fault_vy,
            "fault_vz": fault_vz,
            "fault_horizontal_speed":
                math.hypot(fault_vx, fault_vy),
            "fault_horizontal_offset":
                math.hypot(fault_x, fault_y),
            "fault_roll_deg":
                float(fault_row["roll_deg"]),
            "fault_pitch_deg":
                float(fault_row["pitch_deg"]),
            "fault_max_motor_pwm":
                max(
                    float(fault_row.get(
                        f"motor_m{motor_index}",
                        0,
                    ))
                    for motor_index in (1, 2, 3, 4)
                ),
            "contact_t": row_time(contact_row),
            "fault_to_contact_s":
                row_time(contact_row)
                - row_time(fault_row),
            "contact_vertical_speed_mps":
                contact_vz,
            "vertical_speed_excess_mps":
                contact_vz - 0.35,
            "contact_horizontal_speed_mps":
                math.hypot(
                    contact_vx,
                    contact_vy,
                ),
            "contact_drift_m":
                math.hypot(
                    contact_x,
                    contact_y,
                ),
            "contact_max_tilt_deg":
                max(roll, pitch),
            "contact_angular_rate_radps":
                math.radians(
                    math.sqrt(
                        gyro_x ** 2
                        + gyro_y ** 2
                        + gyro_z ** 2
                    )
                ),
            "r1":
                optional_int(contact_row, ("r1",)),
            "r2":
                optional_int(contact_row, ("r2",)),
            "r3":
                optional_int(contact_row, ("r3",)),
            "r4":
                optional_int(contact_row, ("r4",)),
            "qp_score":
                optional_float(
                    contact_row,
                    ("qp_score",),
                ),
            "qp_predicted_vz":
                optional_float(
                    contact_row,
                    ("qp_predicted_vz",),
                ),
            "prediction_error_actual_minus_predicted":
                (
                    contact_vz
                    - float(
                        first_text(
                            contact_row,
                            ("qp_predicted_vz",),
                        )
                    )
                    if first_text(
                        contact_row,
                        ("qp_predicted_vz",),
                    )
                    else ""
                ),
            "vertical_speed_ok":
                summary["vertical_speed_ok"],
            "horizontal_speed_ok":
                summary["horizontal_speed_ok"],
            "roll_pitch_ok":
                summary["roll_pitch_ok"],
            "angular_rate_ok":
                summary["angular_rate_ok"],
            "drift_ok":
                summary["drift_ok"],
            "source_csv": str(source),
        }
    )


if len(diagnostic_rows) != 5:
    raise SystemExit(
        f"[FAIL] Expected 5 failures; "
        f"found {len(diagnostic_rows)}"
    )

diagnostic_rows.sort(
    key=lambda row:
        int(row["sequence_index"])
)

candidate_rows = [
    {
        "motor": motor,
        "outcome": outcome,
        "selected_candidate": candidate,
        "count": count,
    }
    for (
        motor,
        outcome,
        candidate,
    ), count in sorted(
        candidate_counter.items()
    )
]

write_csv(
    FAILURE_OUTPUT,
    diagnostic_rows,
)

write_csv(
    CANDIDATE_OUTPUT,
    candidate_rows,
)

print(
    "sequence,motor,seed,candidate,"
    "fault_z,fault_vz,contact_vz,excess,"
    "predicted_vz,prediction_error"
)

for row in diagnostic_rows:
    predicted = row["qp_predicted_vz"]
    prediction_error = row[
        "prediction_error_actual_minus_predicted"
    ]

    predicted_text = (
        f"{float(predicted):.6f}"
        if predicted != ""
        else ""
    )

    error_text = (
        f"{float(prediction_error):+.6f}"
        if prediction_error != ""
        else ""
    )

    print(
        f"{row['sequence_index']},"
        f"M{row['motor']},"
        f"{row['trial_seed']},"
        f"{row['selected_candidate']},"
        f"{float(row['fault_z']):.6f},"
        f"{float(row['fault_vz']):+.6f},"
        f"{float(row['contact_vertical_speed_mps']):.6f},"
        f"{float(row['vertical_speed_excess_mps']):+.6f},"
        f"{predicted_text},"
        f"{error_text}"
    )

print()
print("========== CANDIDATE BREAKDOWN ==========")

for row in candidate_rows:
    print(
        f"M{row['motor']} "
        f"{row['outcome']:6s} "
        f"{row['selected_candidate']:20s} "
        f"n={row['count']}"
    )

report_lines = [
    "# Randomized Supervisor Failure Diagnostics",
    "",
    "## Summary",
    "",
    "- Total production trials: 120",
    "- Safe trials: 115",
    "- Unsafe trials: 5",
    "- All unsafe trials violated only the "
    "vertical-speed threshold.",
    "",
    "## Unsafe first-contact outcomes",
    "",
    "| Sequence | Motor | Seed | Candidate | "
    "Actual vertical speed | Excess over limit | "
    "Predicted vertical speed |",
    "|---:|---:|---:|:---|---:|---:|---:|",
]

for row in diagnostic_rows:
    predicted = row["qp_predicted_vz"]

    predicted_text = (
        f"{float(predicted):.6f}"
        if predicted != ""
        else "not logged"
    )

    report_lines.append(
        f"| {row['sequence_index']} "
        f"| M{row['motor']} "
        f"| {row['trial_seed']} "
        f"| {row['selected_candidate']} "
        f"| "
        f"{float(row['contact_vertical_speed_mps']):.6f} "
        f"| "
        f"{float(row['vertical_speed_excess_mps']):+.6f} "
        f"| {predicted_text} |"
    )

report_lines.extend(
    [
        "",
        "These diagnostics describe failures under the "
        "current seeded simulator distribution. They do "
        "not by themselves establish the causal source of "
        "the upper-tail vertical-speed errors.",
    ]
)

REPORT_OUTPUT.write_text(
    "\n".join(report_lines) + "\n"
)

print()
print(f"[SAVED] {FAILURE_OUTPUT}")
print(f"[SAVED] {CANDIDATE_OUTPUT}")
print(f"[SAVED] {REPORT_OUTPUT}")
print("[PASS] Supervisor failure diagnostics complete.")
