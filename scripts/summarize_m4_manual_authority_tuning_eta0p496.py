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


def as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value

    return str(value).strip().lower() == "true"


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

    rank = max(
        1,
        math.ceil(probability * len(ordered)),
    )

    return ordered[rank - 1]


def exact_mcnemar(
    first_only: int,
    second_only: int,
) -> float:
    discordant = first_only + second_only

    if discordant == 0:
        return 1.0

    lower = min(first_only, second_only)

    probability = sum(
        math.comb(discordant, index)
        for index in range(lower + 1)
    ) / (2 ** discordant)

    return min(1.0, 2.0 * probability)


def bootstrap_mean_interval(
    values: list[float],
    seed: int,
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
    default="m4_authority_tuning",
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

if len(schedule) != 120:
    raise SystemExit(
        f"[FAIL] Expected 120 scheduled trials; "
        f"found {len(schedule)}"
    )

trial_rows = []
errors = []

for index, specification in enumerate(schedule, start=1):
    path = Path(specification["expected_csv"])
    strength = int(specification["strength"])
    expected_seed = int(specification["trial_seed"])
    expected_name = specification["manual_name"]

    try:
        if not path.is_file():
            raise ValueError(f"Missing trial: {path}")

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
                f"{path}: seed mismatch "
                f"{actual_seed} != {expected_seed}"
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

        if float(fault_row["z"]) < MIN_VALID_FAULT_Z:
            raise ValueError(
                f"{path}: invalid fault height"
            )

        if (
            abs(float(fault_row["vz"]))
            > MAX_VALID_FAULT_ABS_VZ
        ):
            raise ValueError(
                f"{path}: invalid pre-fault vertical speed"
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
                f"{path}: first contact missing"
            )

        controller = contact["controller"].strip().lower()
        candidate = contact["selected_candidate"].strip()

        residuals = (
            int(float(contact["r1"])),
            int(float(contact["r2"])),
            int(float(contact["r3"])),
            int(float(contact["r4"])),
        )

        if controller != "qplite":
            raise ValueError(
                f"{path}: controller={controller}"
            )

        if candidate != expected_name:
            raise ValueError(
                f"{path}: candidate={candidate}, "
                f"expected={expected_name}"
            )

        if residuals != (0, strength, 0, 0):
            raise ValueError(
                f"{path}: residuals={residuals}"
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

    if index % 20 == 0:
        print(f"[PROGRESS] audited={index}/120")

if errors:
    for error in errors:
        print(f"[ERROR] {error}")

    raise SystemExit(
        f"[FAIL] Found {len(errors)} audit errors."
    )

groups = defaultdict(list)

for row in trial_rows:
    groups[int(row["strength"])].append(row)

strengths = sorted(groups)

if strengths != [12000, 13000, 14000, 15000]:
    raise SystemExit(
        f"[FAIL] Unexpected strengths={strengths}"
    )

seed_sets = {
    strength: {
        int(row["trial_seed"])
        for row in group
    }
    for strength, group in groups.items()
}

reference_seed_set = seed_sets[12000]

for strength, seed_set in seed_sets.items():
    if seed_set != reference_seed_set:
        raise SystemExit(
            f"[FAIL] Seed mismatch for strength={strength}"
        )

aggregate_rows = []

print()
print("========== PAIRED M4 AUTHORITY SWEEP ==========")

for strength in strengths:
    group = groups[strength]

    if len(group) != 30:
        raise SystemExit(
            f"[FAIL] strength={strength}: n={len(group)}"
        )

    safe_count = sum(
        as_bool(row["safe_touchdown"])
        for row in group
    )

    vertical_speeds = [
        float(row["vertical_speed_mps"])
        for row in group
    ]

    lower, upper = wilson_interval(
        safe_count,
        len(group),
    )

    other_failures = sum(
        (
            not as_bool(row["horizontal_speed_ok"])
            or not as_bool(row["roll_pitch_ok"])
            or not as_bool(row["angular_rate_ok"])
            or not as_bool(row["drift_ok"])
        )
        for row in group
    )

    aggregate = {
        "strength": strength,
        "n": len(group),
        "safe_count": safe_count,
        "unsafe_count": len(group) - safe_count,
        "safe_rate": safe_count / len(group),
        "safe_rate_wilson95_lower": lower,
        "safe_rate_wilson95_upper": upper,
        "mean_vertical_speed_mps":
            statistics.mean(vertical_speeds),
        "median_vertical_speed_mps":
            statistics.median(vertical_speeds),
        "q90_vertical_speed_mps":
            nearest_rank(vertical_speeds, 0.90),
        "q95_vertical_speed_mps":
            nearest_rank(vertical_speeds, 0.95),
        "max_vertical_speed_mps":
            max(vertical_speeds),
        "vertical_failure_count": sum(
            not as_bool(row["vertical_speed_ok"])
            for row in group
        ),
        "other_failure_count": other_failures,
    }

    aggregate_rows.append(aggregate)

    print(
        f"r2={strength}: "
        f"safe={safe_count}/30 "
        f"rate={safe_count / 30:.3f} "
        f"mean_vz={statistics.mean(vertical_speeds):.6f} "
        f"q90={aggregate['q90_vertical_speed_mps']:.6f} "
        f"q95={aggregate['q95_vertical_speed_mps']:.6f} "
        f"max={max(vertical_speeds):.6f} "
        f"vertical_failures="
        f"{aggregate['vertical_failure_count']} "
        f"other_failures={other_failures}"
    )

baseline = {
    int(row["trial_seed"]): row
    for row in groups[12000]
}

pairwise_rows = []

print()
print("========== PAIRED VS R2=12000 ==========")

for comparison_index, strength in enumerate(
    strengths[1:],
    start=1,
):
    comparison = {
        int(row["trial_seed"]): row
        for row in groups[strength]
    }

    both_safe = 0
    baseline_only = 0
    comparison_only = 0
    both_unsafe = 0
    speed_differences = []

    for seed in sorted(reference_seed_set):
        first = baseline[seed]
        second = comparison[seed]

        first_safe = as_bool(first["safe_touchdown"])
        second_safe = as_bool(second["safe_touchdown"])

        if first_safe and second_safe:
            both_safe += 1
        elif first_safe:
            baseline_only += 1
        elif second_safe:
            comparison_only += 1
        else:
            both_unsafe += 1

        speed_differences.append(
            float(second["vertical_speed_mps"])
            - float(first["vertical_speed_mps"])
        )

    lower, upper = bootstrap_mean_interval(
        speed_differences,
        seed=20260724 + comparison_index,
    )

    pairwise = {
        "baseline_strength": 12000,
        "comparison_strength": strength,
        "n_pairs": 30,
        "both_safe": both_safe,
        "baseline_only_safe": baseline_only,
        "comparison_only_safe": comparison_only,
        "both_unsafe": both_unsafe,
        "mcnemar_exact_p":
            exact_mcnemar(
                baseline_only,
                comparison_only,
            ),
        "mean_vertical_speed_difference_comparison_minus_baseline":
            statistics.mean(speed_differences),
        "bootstrap95_difference_lower": lower,
        "bootstrap95_difference_upper": upper,
    }

    pairwise_rows.append(pairwise)

    print(
        f"r2={strength} vs 12000: "
        f"discordant="
        f"{baseline_only}:{comparison_only} "
        f"p={pairwise['mcnemar_exact_p']:.8f} "
        f"mean_delta_vz="
        f"{pairwise['mean_vertical_speed_difference_comparison_minus_baseline']:+.6f} "
        f"CI=[{lower:+.6f}, {upper:+.6f}]"
    )

trial_rows.sort(
    key=lambda row: (
        int(row["strength"]),
        int(row["trial_seed"]),
    )
)

trial_output = root / "authority_trial_summaries.csv"
aggregate_output = root / "authority_aggregate.csv"
pairwise_output = root / "authority_pairwise_vs_12000.csv"

write_csv(trial_output, trial_rows)
write_csv(aggregate_output, aggregate_rows)
write_csv(pairwise_output, pairwise_rows)

print()
print(f"[SAVED] {trial_output}")
print(f"[SAVED] {aggregate_output}")
print(f"[SAVED] {pairwise_output}")
print("[PASS] Paired M4 authority analysis complete.")
