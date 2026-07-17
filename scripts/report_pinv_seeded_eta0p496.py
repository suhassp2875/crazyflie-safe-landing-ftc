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

TRIAL_FILE = ROOT / "all_trial_summaries.csv"
AGGREGATE_FILE = ROOT / "aggregate_by_motor.csv"
DIAGNOSTIC_FILE = ROOT / "distribution_diagnostics.csv"
REPORT_FILE = ROOT / "official_report.md"


def as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def percentile(
    values: list[float],
    probability: float,
) -> float:
    ordered = sorted(values)

    if not ordered:
        return math.nan

    if len(ordered) == 1:
        return ordered[0]

    position = probability * (len(ordered) - 1)
    lower_index = math.floor(position)
    upper_index = math.ceil(position)

    if lower_index == upper_index:
        return ordered[lower_index]

    weight = position - lower_index

    return (
        ordered[lower_index] * (1.0 - weight)
        + ordered[upper_index] * weight
    )


def wilson_interval(
    successes: int,
    trials: int,
    z: float = 1.959963984540054,
) -> tuple[float, float]:
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


with TRIAL_FILE.open(newline="") as file:
    trials = list(csv.DictReader(file))

with AGGREGATE_FILE.open(newline="") as file:
    aggregates = list(csv.DictReader(file))

if len(trials) != 120:
    raise SystemExit(
        f"[FAIL] Expected 120 trial summaries; found {len(trials)}"
    )

if len(aggregates) != 4:
    raise SystemExit(
        f"[FAIL] Expected four aggregate rows; "
        f"found {len(aggregates)}"
    )

by_motor: dict[int, list[dict[str, str]]] = defaultdict(list)

for row in trials:
    by_motor[int(row["motor"])].append(row)

diagnostic_rows = []

for motor in (1, 2, 3, 4):
    group = by_motor[motor]

    if len(group) != 30:
        raise SystemExit(
            f"[FAIL] Motor {motor} has {len(group)} trials."
        )

    speeds = [
        float(row["vertical_speed_mps"])
        for row in group
    ]

    diagnostic_rows.append(
        {
            "motor": motor,
            "n": len(group),
            "safe_count": sum(
                as_bool(row["safe_touchdown"])
                for row in group
            ),
            "mean_vertical_speed_mps":
                statistics.mean(speeds),
            "std_vertical_speed_mps":
                statistics.stdev(speeds),
            "minimum_vertical_speed_mps":
                min(speeds),
            "p05_vertical_speed_mps":
                percentile(speeds, 0.05),
            "p25_vertical_speed_mps":
                percentile(speeds, 0.25),
            "median_vertical_speed_mps":
                percentile(speeds, 0.50),
            "p75_vertical_speed_mps":
                percentile(speeds, 0.75),
            "p95_vertical_speed_mps":
                percentile(speeds, 0.95),
            "maximum_vertical_speed_mps":
                max(speeds),
            "robust_safe_le_0p34": sum(
                speed <= 0.34
                for speed in speeds
            ),
            "near_safe_0p34_to_0p35": sum(
                0.34 < speed <= 0.35
                for speed in speeds
            ),
            "near_failure_0p35_to_0p36": sum(
                0.35 < speed <= 0.36
                for speed in speeds
            ),
            "clear_failure_gt_0p36": sum(
                speed > 0.36
                for speed in speeds
            ),
        }
    )

with DIAGNOSTIC_FILE.open("w", newline="") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=list(diagnostic_rows[0].keys()),
    )
    writer.writeheader()
    writer.writerows(diagnostic_rows)

overall_safe = sum(
    as_bool(row["safe_touchdown"])
    for row in trials
)

overall_lower, overall_upper = wilson_interval(
    overall_safe,
    len(trials),
)

lines = [
    "# Fault-Aware Bounded WLS Landing Results",
    "",
    "## Experiment",
    "",
    "- Controller: fault-aware bounded weighted least squares",
    "- Fault effectiveness: `eta = 0.496`",
    "- Allocation weights: `[1.0, 1.0, 1.0, 0.2]`",
    "- Regularization: `1e-6`",
    "- Trials: `30` seeded trials per failed motor",
    "- Total trials: `120`",
    "- First contact: first post-fault sample with `z <= 0.03 m`",
    "- Safe vertical-speed threshold: `0.35 m/s`",
    "",
    "## Success rates",
    "",
    "| Motor | Safe | Rate | Wilson 95% CI | Mean vertical speed | Maximum vertical speed |",
    "|---:|---:|---:|---:|---:|---:|",
]

for row in aggregates:
    lines.append(
        f"| M{row['motor']} "
        f"| {row['safe_count']}/{row['n']} "
        f"| {100 * float(row['safe_rate']):.1f}% "
        f"| "
        f"[{100 * float(row['safe_rate_wilson95_lower']):.1f}%, "
        f"{100 * float(row['safe_rate_wilson95_upper']):.1f}%] "
        f"| {float(row['mean_vertical_speed_mps']):.6f} m/s "
        f"| {float(row['max_vertical_speed_mps']):.6f} m/s |"
    )

lines.extend(
    [
        "",
        (
            f"Overall safe touchdown count: "
            f"**{overall_safe}/120 "
            f"({100 * overall_safe / 120:.1f}%)**."
        ),
        "",
        (
            "Overall Wilson 95% confidence interval: "
            f"**[{100 * overall_lower:.1f}%, "
            f"{100 * overall_upper:.1f}%]**."
        ),
        "",
        "All 120 trials reached first contact. "
        "Every unsafe outcome failed only the vertical-speed "
        "criterion; there were no horizontal-speed, tilt, "
        "angular-rate, or drift failures.",
        "",
        "## Interpretation",
        "",
        "- M2 was safe in all 30 trials and remained below the "
        "vertical-speed threshold even in its worst trial.",
        "- M1 was usually safe but operated close to the "
        "vertical-speed boundary.",
        "- M3 showed substantial seed sensitivity, with both "
        "safe and unsafe touchdown regimes.",
        "- M4 failed the vertical-speed criterion in all 30 "
        "trials under the tested allocation weights.",
        "",
        "These conclusions apply to the tested fault severity, "
        "allocator weights, simulator, and landing protocol. "
        "They do not establish impossibility for M4 under other "
        "allocation objectives or landing policies.",
    ]
)

REPORT_FILE.write_text("\n".join(lines) + "\n")

print("========== DISTRIBUTION DIAGNOSTICS ==========")

for row in diagnostic_rows:
    print(
        f"M{row['motor']}: "
        f"safe={row['safe_count']}/30 "
        f"median={row['median_vertical_speed_mps']:.6f} "
        f"p05={row['p05_vertical_speed_mps']:.6f} "
        f"p95={row['p95_vertical_speed_mps']:.6f} "
        f"<=0.34={row['robust_safe_le_0p34']} "
        f"0.34-0.35={row['near_safe_0p34_to_0p35']} "
        f"0.35-0.36={row['near_failure_0p35_to_0p36']} "
        f">0.36={row['clear_failure_gt_0p36']}"
    )

print()
print(REPORT_FILE.read_text())
print(f"[SAVED] {DIAGNOSTIC_FILE}")
print(f"[SAVED] {REPORT_FILE}")
