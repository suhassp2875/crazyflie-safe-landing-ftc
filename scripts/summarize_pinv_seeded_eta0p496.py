#!/usr/bin/env python3

from __future__ import annotations

import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(
    "results/final/pinv_baseline/"
    "seeded_eta0p496/production_30"
)
SUMMARY_DIR = ROOT / "summaries"


def as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def wilson_interval(
    successes: int,
    trials: int,
    z: float = 1.959963984540054,
) -> tuple[float, float]:
    if trials <= 0:
        return math.nan, math.nan

    probability = successes / trials
    denominator = 1.0 + z * z / trials

    center = (
        probability + z * z / (2.0 * trials)
    ) / denominator

    radius = (
        z
        * math.sqrt(
            probability * (1.0 - probability) / trials
            + z * z / (4.0 * trials * trials)
        )
        / denominator
    )

    return center - radius, center + radius


summary_files = sorted(
    SUMMARY_DIR.glob("*_summary.csv")
)

if len(summary_files) != 120:
    raise SystemExit(
        f"[FAIL] Expected 120 summaries; "
        f"found {len(summary_files)}"
    )

trial_rows: list[dict[str, str]] = []

for path in summary_files:
    with path.open(newline="") as file:
        rows = list(csv.DictReader(file))

    if len(rows) != 1:
        raise SystemExit(
            f"[FAIL] Expected one summary row in {path}; "
            f"found {len(rows)}"
        )

    row = rows[0]
    row["summary_file"] = str(path)
    trial_rows.append(row)

by_motor: dict[int, list[dict[str, str]]] = defaultdict(list)

for row in trial_rows:
    motor = int(row["motor"])
    by_motor[motor].append(row)

aggregate_rows: list[dict[str, object]] = []

print(
    "========== PINV ETA=0.496 · "
    "30 SEEDED TRIALS PER MOTOR =========="
)

for motor in (1, 2, 3, 4):
    group = by_motor.get(motor, [])

    if len(group) != 30:
        raise SystemExit(
            f"[FAIL] M{motor} contains {len(group)} trials; "
            "expected 30."
        )

    contact_count = sum(
        as_bool(row["contact_found"])
        for row in group
    )

    safe_count = sum(
        as_bool(row["safe_touchdown"])
        for row in group
    )

    contact_rows = [
        row
        for row in group
        if as_bool(row["contact_found"])
    ]

    vertical_speeds = [
        float(row["vertical_speed_mps"])
        for row in contact_rows
    ]

    margins = [
        float(row["vertical_speed_margin_mps"])
        for row in contact_rows
    ]

    horizontal_speeds = [
        float(row["horizontal_speed_mps"])
        for row in contact_rows
    ]

    tilts = [
        float(row["max_tilt_deg"])
        for row in contact_rows
    ]

    angular_rates = [
        float(row["angular_rate_radps"])
        for row in contact_rows
    ]

    drifts = [
        float(row["horizontal_drift_m"])
        for row in contact_rows
    ]

    fault_to_contact = [
        float(row["fault_to_contact_s"])
        for row in contact_rows
    ]

    failure_counts = {
        "no_contact_count": sum(
            not as_bool(row["contact_found"])
            for row in group
        ),
        "vertical_speed_failure_count": sum(
            row.get("vertical_speed_ok", "").lower() == "false"
            for row in contact_rows
        ),
        "horizontal_speed_failure_count": sum(
            row.get("horizontal_speed_ok", "").lower() == "false"
            for row in contact_rows
        ),
        "tilt_failure_count": sum(
            row.get("roll_pitch_ok", "").lower() == "false"
            for row in contact_rows
        ),
        "angular_rate_failure_count": sum(
            row.get("angular_rate_ok", "").lower() == "false"
            for row in contact_rows
        ),
        "drift_failure_count": sum(
            row.get("drift_ok", "").lower() == "false"
            for row in contact_rows
        ),
    }

    lower, upper = wilson_interval(
        safe_count,
        len(group),
    )

    aggregate = {
        "motor": motor,
        "eta": 0.496,
        "n": len(group),
        "contact_count": contact_count,
        "safe_count": safe_count,
        "unsafe_count": len(group) - safe_count,
        "safe_rate": safe_count / len(group),
        "safe_rate_wilson95_lower": lower,
        "safe_rate_wilson95_upper": upper,
        **failure_counts,
        "mean_vertical_speed_mps":
            statistics.mean(vertical_speeds),
        "median_vertical_speed_mps":
            statistics.median(vertical_speeds),
        "std_vertical_speed_mps":
            statistics.stdev(vertical_speeds),
        "min_vertical_speed_mps":
            min(vertical_speeds),
        "max_vertical_speed_mps":
            max(vertical_speeds),
        "mean_vertical_speed_margin_mps":
            statistics.mean(margins),
        "min_vertical_speed_margin_mps":
            min(margins),
        "max_vertical_speed_margin_mps":
            max(margins),
        "mean_horizontal_speed_mps":
            statistics.mean(horizontal_speeds),
        "max_horizontal_speed_mps":
            max(horizontal_speeds),
        "mean_max_tilt_deg":
            statistics.mean(tilts),
        "max_tilt_deg":
            max(tilts),
        "mean_angular_rate_radps":
            statistics.mean(angular_rates),
        "max_angular_rate_radps":
            max(angular_rates),
        "mean_horizontal_drift_m":
            statistics.mean(drifts),
        "max_horizontal_drift_m":
            max(drifts),
        "mean_fault_to_contact_s":
            statistics.mean(fault_to_contact),
        "min_fault_to_contact_s":
            min(fault_to_contact),
        "max_fault_to_contact_s":
            max(fault_to_contact),
    }

    aggregate_rows.append(aggregate)

    print(
        f"M{motor}: "
        f"contact={contact_count}/30 "
        f"safe={safe_count}/30 "
        f"rate={aggregate['safe_rate']:.3f} "
        f"Wilson95=[{lower:.3f}, {upper:.3f}] "
        f"mean_vz={aggregate['mean_vertical_speed_mps']:.6f} "
        f"range=["
        f"{aggregate['min_vertical_speed_mps']:.6f}, "
        f"{aggregate['max_vertical_speed_mps']:.6f}] "
        f"vertical_failures="
        f"{failure_counts['vertical_speed_failure_count']}"
    )

all_trial_fields: list[str] = []

for row in trial_rows:
    for key in row:
        if key not in all_trial_fields:
            all_trial_fields.append(key)

trial_output = ROOT / "all_trial_summaries.csv"

with trial_output.open("w", newline="") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=all_trial_fields,
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(trial_rows)

aggregate_output = ROOT / "aggregate_by_motor.csv"

with aggregate_output.open("w", newline="") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=list(aggregate_rows[0].keys()),
    )
    writer.writeheader()
    writer.writerows(aggregate_rows)

overall_safe = sum(
    int(row["safe_count"])
    for row in aggregate_rows
)

overall_contact = sum(
    int(row["contact_count"])
    for row in aggregate_rows
)

non_vertical_failures = sum(
    int(row["horizontal_speed_failure_count"])
    + int(row["tilt_failure_count"])
    + int(row["angular_rate_failure_count"])
    + int(row["drift_failure_count"])
    for row in aggregate_rows
)

print()
print("========== OVERALL ==========")
print(f"contact={overall_contact}/120")
print(f"safe={overall_safe}/120")
print(
    f"non_vertical_safety_failures="
    f"{non_vertical_failures}"
)
print(f"[SAVED] {trial_output}")
print(f"[SAVED] {aggregate_output}")

if overall_contact != 120:
    raise SystemExit(
        "[FAIL] One or more trials did not reach contact."
    )

print("[PASS] Official 120-trial aggregation complete.")
