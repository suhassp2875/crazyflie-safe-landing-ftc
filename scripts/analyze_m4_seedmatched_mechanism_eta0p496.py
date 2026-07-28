#!/usr/bin/env python3

from __future__ import annotations

import csv
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(
    "results/final/pinv_baseline/"
    "seeded_eta0p496/m4_authority_tuning/"
    "m4_v2_seedmatched_comparison"
)

TRIAL_PATH = ROOT / "holdout_trial_summaries.csv"
OUTPUT_PATH = ROOT / "paired_mechanism_audit.csv"

BASELINE = 12000
TUNED = 14000


def as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def fault_row(path: Path) -> dict[str, str]:
    rows = read_rows(path)

    return next(
        row
        for row in rows
        if row["phase"].strip() == "fault_event"
    )


def feature_vector(
    row: dict[str, str],
) -> dict[str, float]:
    x = float(row["x"])
    y = float(row["y"])
    z = float(row["z"])

    vx = float(row["vx"])
    vy = float(row["vy"])
    vz = float(row["vz"])

    roll = float(row["roll_deg"])
    pitch = float(row["pitch_deg"])

    gyro_x = float(row["gyro_x_deg_s"])
    gyro_y = float(row["gyro_y_deg_s"])
    gyro_z = float(row["gyro_z_deg_s"])

    return {
        "fault_x": x,
        "fault_y": y,
        "fault_z": z,
        "fault_vx": vx,
        "fault_vy": vy,
        "fault_vz": vz,
        "fault_horizontal_offset":
            math.hypot(x, y),
        "fault_horizontal_speed":
            math.hypot(vx, vy),
        "fault_roll_deg": roll,
        "fault_pitch_deg": pitch,
        "fault_max_tilt_deg":
            max(abs(roll), abs(pitch)),
        "fault_angular_rate_radps":
            math.radians(
                math.sqrt(
                    gyro_x ** 2
                    + gyro_y ** 2
                    + gyro_z ** 2
                )
            ),
    }


if not TRIAL_PATH.is_file():
    raise SystemExit(
        f"[FAIL] Missing {TRIAL_PATH}"
    )

trials = read_rows(TRIAL_PATH)

groups: dict[
    int,
    dict[int, dict[str, str]],
] = defaultdict(dict)

for row in trials:
    seed = int(float(row["trial_seed"]))
    strength = int(row["strength"])
    groups[seed][strength] = row

if len(groups) != 30:
    raise SystemExit(
        f"[FAIL] Expected 30 seeds; found {len(groups)}"
    )

records = []

for seed in sorted(groups):
    pair = groups[seed]

    if set(pair) != {BASELINE, TUNED}:
        raise SystemExit(
            f"[FAIL] Seed {seed} strengths={sorted(pair)}"
        )

    baseline = pair[BASELINE]
    tuned = pair[TUNED]

    baseline_safe = as_bool(
        baseline["safe_touchdown"]
    )
    tuned_safe = as_bool(
        tuned["safe_touchdown"]
    )

    if baseline_safe and tuned_safe:
        outcome = "both_safe"
    elif baseline_safe:
        outcome = "baseline_only_safe"
    elif tuned_safe:
        outcome = "tuned_only_safe"
    else:
        outcome = "both_unsafe"

    baseline_source = Path(
        baseline["source_csv"]
    )
    tuned_source = Path(
        tuned["source_csv"]
    )

    baseline_fault = feature_vector(
        fault_row(baseline_source)
    )
    tuned_fault = feature_vector(
        fault_row(tuned_source)
    )

    paired_state_difference = math.sqrt(
        sum(
            (
                baseline_fault[name]
                - tuned_fault[name]
            ) ** 2
            for name in (
                "fault_x",
                "fault_y",
                "fault_z",
                "fault_vx",
                "fault_vy",
                "fault_vz",
            )
        )
    )

    baseline_vz = float(
        baseline["vertical_speed_mps"]
    )
    tuned_vz = float(
        tuned["vertical_speed_mps"]
    )

    records.append(
        {
            "trial_seed": seed,
            "paired_outcome": outcome,
            "baseline_safe": baseline_safe,
            "tuned_safe": tuned_safe,
            "baseline_vertical_speed_mps":
                baseline_vz,
            "tuned_vertical_speed_mps":
                tuned_vz,
            "difference_14000_minus_12000_mps":
                tuned_vz - baseline_vz,
            "paired_fault_state_difference":
                paired_state_difference,
            **baseline_fault,
            "baseline_source_csv":
                str(baseline_source),
            "tuned_source_csv":
                str(tuned_source),
        }
    )

with OUTPUT_PATH.open("w", newline="") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=list(records[0].keys()),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(records)

counts = Counter(
    row["paired_outcome"]
    for row in records
)

oracle_safe = (
    counts["both_safe"]
    + counts["baseline_only_safe"]
    + counts["tuned_only_safe"]
)

print("========== PAIRED OUTCOME COUNTS ==========")

for outcome in (
    "both_safe",
    "baseline_only_safe",
    "tuned_only_safe",
    "both_unsafe",
):
    print(f"{outcome}={counts[outcome]}")

print(f"posthoc_oracle_safe={oracle_safe}/30")

print()
print("========== DISCORDANT AND BOTH-UNSAFE SEEDS ==========")

print(
    "seed,outcome,fault_z,fault_vz,"
    "horizontal_offset,horizontal_speed,"
    "max_tilt,angular_rate,"
    "vz_12000,vz_14000,delta"
)

interesting = [
    row
    for row in records
    if row["paired_outcome"] != "both_safe"
]

for row in sorted(
    interesting,
    key=lambda item:
        float(
            item[
                "difference_14000_minus_12000_mps"
            ]
        ),
):
    print(
        f"{row['trial_seed']},"
        f"{row['paired_outcome']},"
        f"{float(row['fault_z']):.6f},"
        f"{float(row['fault_vz']):+.6f},"
        f"{float(row['fault_horizontal_offset']):.6f},"
        f"{float(row['fault_horizontal_speed']):.6f},"
        f"{float(row['fault_max_tilt_deg']):.6f},"
        f"{float(row['fault_angular_rate_radps']):.6f},"
        f"{float(row['baseline_vertical_speed_mps']):.6f},"
        f"{float(row['tuned_vertical_speed_mps']):.6f},"
        f"{float(row['difference_14000_minus_12000_mps']):+.6f}"
    )

print()
print("========== GROUP FEATURE MEANS ==========")

feature_names = (
    "fault_z",
    "fault_vz",
    "fault_horizontal_offset",
    "fault_horizontal_speed",
    "fault_max_tilt_deg",
    "fault_angular_rate_radps",
)

for outcome in (
    "baseline_only_safe",
    "tuned_only_safe",
    "both_unsafe",
):
    group = [
        row
        for row in records
        if row["paired_outcome"] == outcome
    ]

    if not group:
        continue

    print(f"[{outcome}] n={len(group)}")

    for feature in feature_names:
        values = [
            float(row[feature])
            for row in group
        ]

        print(
            f"  {feature}: "
            f"mean={statistics.mean(values):+.6f} "
            f"range=[{min(values):+.6f}, "
            f"{max(values):+.6f}]"
        )

max_pair_difference = max(
    float(row["paired_fault_state_difference"])
    for row in records
)

print()
print(
    "max_paired_fault_state_difference="
    f"{max_pair_difference:.9f}"
)
print(f"[SAVED] {OUTPUT_PATH}")
print("[PASS] M4 paired mechanism audit complete.")
