#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path


VERTICAL_SPEED_LIMIT = 0.35
HORIZONTAL_SPEED_LIMIT = 0.25
TILT_LIMIT_DEG = 12.0
ANGULAR_RATE_LIMIT_RADPS = 1.5
DRIFT_LIMIT_M = 0.75

MIN_VALID_FAULT_Z = 0.50
MAX_VALID_FAULT_ABS_VZ = 0.25

BASELINE_STRENGTH = 12000
TUNED_STRENGTH = 14000


def wilson_interval(
    successes: int,
    trials: int,
    z: float = 1.959963984540054,
) -> tuple[float, float]:
    probability = successes / trials
    denominator = 1.0 + z * z / trials

    center = (
        probability
        + z * z / (2.0 * trials)
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


def nearest_rank(
    values: list[float],
    probability: float,
) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(probability * len(ordered)))
    return ordered[rank - 1]


def exact_mcnemar(
    baseline_only: int,
    tuned_only: int,
) -> float:
    discordant = baseline_only + tuned_only

    if discordant == 0:
        return 1.0

    lower = min(baseline_only, tuned_only)

    probability = sum(
        math.comb(discordant, index)
        for index in range(lower + 1)
    ) / (2 ** discordant)

    return min(1.0, 2.0 * probability)


def bootstrap_mean_interval(
    values: list[float],
    seed: int = 20260724,
    repetitions: int = 20_000,
) -> tuple[float, float]:
    generator = random.Random(seed)
    sample_size = len(values)
    estimates = []

    for _ in range(repetitions):
        sample = [
            values[generator.randrange(sample_size)]
            for _ in range(sample_size)
        ]
        estimates.append(statistics.mean(sample))

    estimates.sort()

    return (
        estimates[int(0.025 * (repetitions - 1))],
        estimates[int(0.975 * (repetitions - 1))],
    )


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
) -> None:
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0].keys()),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


parser = argparse.ArgumentParser()
parser.add_argument(
    "--run-id",
    default="m4_authority_holdout",
)
arguments = parser.parse_args()

root = Path(
    "results/final/pinv_baseline/"
    "seeded_eta0p496/m4_authority_tuning"
) / arguments.run_id

schedule_path = root / "schedule.csv"

if not schedule_path.is_file():
    raise SystemExit(
        f"[FAIL] Missing schedule: {schedule_path}"
    )

with schedule_path.open(newline="") as file:
    schedule = list(csv.DictReader(file))

if len(schedule) != 60:
    raise SystemExit(
        f"[FAIL] Expected 60 scheduled trials; "
        f"found {len(schedule)}"
    )

trial_rows = []
errors = []

for index, specification in enumerate(schedule, start=1):
    path = Path(specification["expected_csv"])
    strength = int(specification["strength"])
    expected_seed = int(specification["trial_seed"])
    expected_candidate = specification["manual_name"]

    try:
        if strength not in (
            BASELINE_STRENGTH,
            TUNED_STRENGTH,
        ):
            raise ValueError(
                f"{path}: unexpected strength={strength}"
            )

        if not path.is_file():
            raise ValueError(f"Missing trial: {path}")

        if path.stat().st_size == 0:
            raise ValueError(f"Empty trial: {path}")

        with path.open(newline="") as file:
            reader = csv.DictReader(file)
            rows = list(reader)
            fields = set(reader.fieldnames or [])

        if not 3500 <= len(rows) <= 5000:
            raise ValueError(
                f"{path}: unexpected rows={len(rows)}"
            )

        required = {
            "phase",
            "trial_seed",
            "controller",
            "selected_candidate",
            "r1",
            "r2",
            "r3",
            "r4",
            "z",
            "vz",
            "vx",
            "vy",
            "x",
            "y",
            "roll_deg",
            "pitch_deg",
            "gyro_x_deg_s",
            "gyro_y_deg_s",
            "gyro_z_deg_s",
        }

        missing = required - fields

        if missing:
            raise ValueError(
                f"{path}: missing columns={sorted(missing)}"
            )

        actual_seed = int(float(rows[0]["trial_seed"]))

        if actual_seed != expected_seed:
            raise ValueError(
                f"{path}: seed={actual_seed}, "
                f"expected={expected_seed}"
            )

        fault_index = next(
            (
                row_index
                for row_index, row in enumerate(rows)
                if row["phase"].strip() == "fault_event"
            ),
            None,
        )

        if fault_index is None:
            raise ValueError(
                f"{path}: fault_event missing"
            )

        fault_row = rows[fault_index]

        fault_z = float(fault_row["z"])
        fault_vz = float(fault_row["vz"])

        if fault_z < MIN_VALID_FAULT_Z:
            raise ValueError(
                f"{path}: invalid fault_z={fault_z}"
            )

        if abs(fault_vz) > MAX_VALID_FAULT_ABS_VZ:
            raise ValueError(
                f"{path}: invalid fault_vz={fault_vz}"
            )

        contact = next(
            (
                row
                for row in rows[fault_index:]
                if float(row["z"]) <= 0.03
            ),
            None,
        )

        if contact is None:
            raise ValueError(
                f"{path}: contact missing"
            )

        controller = contact["controller"].strip().lower()
        candidate = contact["selected_candidate"].strip()

        residual = (
            int(float(contact["r1"])),
            int(float(contact["r2"])),
            int(float(contact["r3"])),
            int(float(contact["r4"])),
        )

        if controller != "qplite":
            raise ValueError(
                f"{path}: controller={controller}"
            )

        if candidate != expected_candidate:
            raise ValueError(
                f"{path}: candidate={candidate}, "
                f"expected={expected_candidate}"
            )

        if residual != (0, strength, 0, 0):
            raise ValueError(
                f"{path}: residual={residual}"
            )

        vertical_speed = abs(float(contact["vz"]))

        horizontal_speed = math.hypot(
            float(contact["vx"]),
            float(contact["vy"]),
        )

        max_tilt = max(
            abs(float(contact["roll_deg"])),
            abs(float(contact["pitch_deg"])),
        )

        angular_rate = math.radians(
            math.sqrt(
                float(contact["gyro_x_deg_s"]) ** 2
                + float(contact["gyro_y_deg_s"]) ** 2
                + float(contact["gyro_z_deg_s"]) ** 2
            )
        )

        drift = math.hypot(
            float(contact["x"]),
            float(contact["y"]),
        )

        checks = {
            "vertical_speed_ok":
                vertical_speed <= VERTICAL_SPEED_LIMIT,
            "horizontal_speed_ok":
                horizontal_speed <= HORIZONTAL_SPEED_LIMIT,
            "roll_pitch_ok":
                max_tilt <= TILT_LIMIT_DEG,
            "angular_rate_ok":
                angular_rate <= ANGULAR_RATE_LIMIT_RADPS,
            "drift_ok":
                drift <= DRIFT_LIMIT_M,
        }

        trial_rows.append(
            {
                "sequence_index":
                    int(specification["sequence_index"]),
                "strength": strength,
                "repetition":
                    int(specification["repetition"]),
                "trial_seed": expected_seed,
                "selected_candidate": candidate,
                "safe_touchdown": all(checks.values()),
                "vertical_speed_mps": vertical_speed,
                "vertical_speed_margin_mps":
                    VERTICAL_SPEED_LIMIT - vertical_speed,
                "horizontal_speed_mps": horizontal_speed,
                "max_tilt_deg": max_tilt,
                "angular_rate_radps": angular_rate,
                "horizontal_drift_m": drift,
                **checks,
                "source_csv": str(path),
            }
        )

    except Exception as error:
        errors.append(str(error))

    if index % 10 == 0:
        print(f"[PROGRESS] audited={index}/60")

if errors:
    for error in errors:
        print(f"[ERROR] {error}")

    raise SystemExit(
        f"[FAIL] Found {len(errors)} holdout audit errors."
    )

groups = defaultdict(list)

for row in trial_rows:
    groups[int(row["strength"])].append(row)

if sorted(groups) != [
    BASELINE_STRENGTH,
    TUNED_STRENGTH,
]:
    raise SystemExit(
        f"[FAIL] Strength groups={sorted(groups)}"
    )

for strength in groups:
    if len(groups[strength]) != 30:
        raise SystemExit(
            f"[FAIL] strength={strength}, "
            f"n={len(groups[strength])}"
        )

seed_sets = {
    strength: {
        int(row["trial_seed"])
        for row in rows
    }
    for strength, rows in groups.items()
}

if (
    seed_sets[BASELINE_STRENGTH]
    != seed_sets[TUNED_STRENGTH]
):
    raise SystemExit(
        "[FAIL] Baseline and tuned seed sets differ."
    )

aggregate_rows = []

print()
print("========== M4 AUTHORITY FRESH-SEED HOLDOUT ==========")

for strength in (
    BASELINE_STRENGTH,
    TUNED_STRENGTH,
):
    rows = groups[strength]

    safe_count = sum(
        bool(row["safe_touchdown"])
        for row in rows
    )

    speeds = [
        float(row["vertical_speed_mps"])
        for row in rows
    ]

    lower, upper = wilson_interval(
        safe_count,
        len(rows),
    )

    vertical_failures = sum(
        not bool(row["vertical_speed_ok"])
        for row in rows
    )

    other_failures = sum(
        (
            not bool(row["horizontal_speed_ok"])
            or not bool(row["roll_pitch_ok"])
            or not bool(row["angular_rate_ok"])
            or not bool(row["drift_ok"])
        )
        for row in rows
    )

    aggregate = {
        "strength": strength,
        "n": len(rows),
        "safe_count": safe_count,
        "unsafe_count": len(rows) - safe_count,
        "safe_rate": safe_count / len(rows),
        "safe_rate_wilson95_lower": lower,
        "safe_rate_wilson95_upper": upper,
        "mean_vertical_speed_mps":
            statistics.mean(speeds),
        "median_vertical_speed_mps":
            statistics.median(speeds),
        "q90_vertical_speed_mps":
            nearest_rank(speeds, 0.90),
        "q95_vertical_speed_mps":
            nearest_rank(speeds, 0.95),
        "maximum_vertical_speed_mps": max(speeds),
        "vertical_failure_count": vertical_failures,
        "other_failure_count": other_failures,
    }

    aggregate_rows.append(aggregate)

    print(
        f"r2={strength}: "
        f"safe={safe_count}/30 "
        f"rate={safe_count / 30:.3f} "
        f"Wilson95=[{lower:.3f}, {upper:.3f}] "
        f"mean_vz={statistics.mean(speeds):.6f} "
        f"q90={aggregate['q90_vertical_speed_mps']:.6f} "
        f"q95={aggregate['q95_vertical_speed_mps']:.6f} "
        f"max={max(speeds):.6f} "
        f"vertical_failures={vertical_failures} "
        f"other_failures={other_failures}"
    )

baseline = {
    int(row["trial_seed"]): row
    for row in groups[BASELINE_STRENGTH]
}

tuned = {
    int(row["trial_seed"]): row
    for row in groups[TUNED_STRENGTH]
}

both_safe = 0
baseline_only = 0
tuned_only = 0
both_unsafe = 0
speed_differences = []

paired_rows = []

for seed in sorted(seed_sets[BASELINE_STRENGTH]):
    baseline_row = baseline[seed]
    tuned_row = tuned[seed]

    baseline_safe = bool(
        baseline_row["safe_touchdown"]
    )
    tuned_safe = bool(
        tuned_row["safe_touchdown"]
    )

    if baseline_safe and tuned_safe:
        outcome = "both_safe"
        both_safe += 1
    elif baseline_safe:
        outcome = "baseline_only_safe"
        baseline_only += 1
    elif tuned_safe:
        outcome = "tuned_only_safe"
        tuned_only += 1
    else:
        outcome = "both_unsafe"
        both_unsafe += 1

    difference = (
        float(tuned_row["vertical_speed_mps"])
        - float(baseline_row["vertical_speed_mps"])
    )

    speed_differences.append(difference)

    paired_rows.append(
        {
            "trial_seed": seed,
            "baseline_safe": baseline_safe,
            "tuned_safe": tuned_safe,
            "paired_outcome": outcome,
            "baseline_vertical_speed_mps":
                baseline_row["vertical_speed_mps"],
            "tuned_vertical_speed_mps":
                tuned_row["vertical_speed_mps"],
            "difference_tuned_minus_baseline_mps":
                difference,
        }
    )

mcnemar_p = exact_mcnemar(
    baseline_only,
    tuned_only,
)

ci_lower, ci_upper = bootstrap_mean_interval(
    speed_differences,
)

pairwise_row = {
    "baseline_strength": BASELINE_STRENGTH,
    "tuned_strength": TUNED_STRENGTH,
    "n_pairs": 30,
    "both_safe": both_safe,
    "baseline_only_safe": baseline_only,
    "tuned_only_safe": tuned_only,
    "both_unsafe": both_unsafe,
    "mcnemar_exact_two_sided_p": mcnemar_p,
    "mean_vertical_speed_difference_tuned_minus_baseline":
        statistics.mean(speed_differences),
    "median_vertical_speed_difference_tuned_minus_baseline":
        statistics.median(speed_differences),
    "bootstrap95_mean_difference_lower": ci_lower,
    "bootstrap95_mean_difference_upper": ci_upper,
}

print()
print("========== PAIRED HOLDOUT COMPARISON ==========")
print(
    f"both_safe={both_safe} "
    f"baseline_only={baseline_only} "
    f"tuned_only={tuned_only} "
    f"both_unsafe={both_unsafe}"
)
print(f"McNemar_exact_p={mcnemar_p:.8f}")
print(
    "mean_delta_vz_tuned_minus_baseline="
    f"{statistics.mean(speed_differences):+.6f}"
)
print(
    f"bootstrap95=[{ci_lower:+.6f}, "
    f"{ci_upper:+.6f}]"
)

trial_rows.sort(
    key=lambda row: (
        int(row["strength"]),
        int(row["trial_seed"]),
    )
)

write_csv(
    root / "holdout_trial_summaries.csv",
    trial_rows,
)

write_csv(
    root / "holdout_aggregate.csv",
    aggregate_rows,
)

write_csv(
    root / "holdout_paired_trials.csv",
    paired_rows,
)

write_csv(
    root / "holdout_pairwise_summary.csv",
    [pairwise_row],
)

report_lines = [
    "# M4 Residual-Authority Fresh-Seed Holdout",
    "",
    "- Baseline: `opp_m2_12000`",
    "- Development-selected candidate: `opp_m2_14000`",
    "- Thirty identical fresh seeds per candidate",
    "- Fault effectiveness: `eta = 0.496`",
    "",
    "The 14000 candidate was selected using a separate "
    "development seed block. This experiment evaluates it "
    "against the existing 12000 candidate on fresh paired seeds.",
    "",
    "| Strength | Safe | Rate | Mean vertical speed | "
    "Q90 | Q95 | Maximum |",
    "|---:|---:|---:|---:|---:|---:|---:|",
]

for row in aggregate_rows:
    report_lines.append(
        f"| {row['strength']} "
        f"| {row['safe_count']}/30 "
        f"| {100 * float(row['safe_rate']):.1f}% "
        f"| {float(row['mean_vertical_speed_mps']):.6f} "
        f"| {float(row['q90_vertical_speed_mps']):.6f} "
        f"| {float(row['q95_vertical_speed_mps']):.6f} "
        f"| {float(row['maximum_vertical_speed_mps']):.6f} |"
    )

report_lines.extend(
    [
        "",
        f"Discordant pairs: baseline-only `{baseline_only}`, "
        f"tuned-only `{tuned_only}`.",
        "",
        f"Exact McNemar p-value: `{mcnemar_p:.8f}`.",
        "",
        "Paired touchdown-speed difference is computed as "
        "`14000 - 12000`; negative values favor 14000.",
        "",
        (
            "Mean paired difference: "
            f"`{statistics.mean(speed_differences):+.6f} m/s`."
        ),
        "",
        (
            "Bootstrap 95% interval: "
            f"`[{ci_lower:+.6f}, {ci_upper:+.6f}] m/s`."
        ),
    ]
)

(root / "holdout_report.md").write_text(
    "\n".join(report_lines) + "\n"
)

print()
print(f"[SAVED] {root / 'holdout_trial_summaries.csv'}")
print(f"[SAVED] {root / 'holdout_aggregate.csv'}")
print(f"[SAVED] {root / 'holdout_paired_trials.csv'}")
print(f"[SAVED] {root / 'holdout_pairwise_summary.csv'}")
print(f"[SAVED] {root / 'holdout_report.md'}")
print("[PASS] M4 authority holdout evaluation complete.")
