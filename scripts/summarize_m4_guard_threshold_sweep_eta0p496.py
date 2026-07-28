#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
from collections import defaultdict
from itertools import combinations
from pathlib import Path


VERTICAL_LIMIT = 0.35
HORIZONTAL_LIMIT = 0.25
TILT_LIMIT = 12.0
ANGULAR_RATE_LIMIT = 1.5
DRIFT_LIMIT = 0.75

EXPECTED_THRESHOLDS = (0.16, 0.18, 0.20)


def parse_bool(value: object) -> bool:
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
    rank = max(1, math.ceil(probability * len(ordered)))
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
            values[
                generator.randrange(sample_size)
            ]
            for _ in range(sample_size)
        ]

        estimates.append(
            statistics.mean(sample)
        )

    estimates.sort()

    return (
        estimates[
            int(0.025 * (repetitions - 1))
        ],
        estimates[
            int(0.975 * (repetitions - 1))
        ],
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
    default="fresh30",
)

arguments = parser.parse_args()

root = Path(
    "results/final/pinv_baseline/"
    "seeded_eta0p496/m4_guard/"
    "threshold_sweep"
) / arguments.run_id

schedule_path = root / "schedule.csv"

if not schedule_path.is_file():
    raise SystemExit(
        f"[FAIL] Missing schedule: {schedule_path}"
    )

with schedule_path.open(newline="") as file:
    schedule = list(csv.DictReader(file))

if len(schedule) != 90:
    raise SystemExit(
        f"[FAIL] Expected 90 scheduled trials; "
        f"found {len(schedule)}"
    )

trial_rows = []
errors = []

for index, specification in enumerate(
    schedule,
    start=1,
):
    path = Path(specification["expected_csv"])

    threshold = float(
        specification["guard_threshold_mps"]
    )

    expected_seed = int(
        specification["trial_seed"]
    )

    try:
        if not path.is_file():
            raise ValueError(
                f"Missing trial: {path}"
            )

        if path.stat().st_size == 0:
            raise ValueError(
                f"Empty trial: {path}"
            )

        with path.open(newline="") as file:
            reader = csv.DictReader(file)
            rows = list(reader)
            fields = set(reader.fieldnames or [])

        if not 3500 <= len(rows) <= 5000:
            raise ValueError(
                f"{path}: rows={len(rows)}"
            )

        required = {
            "phase",
            "trial_seed",
            "controller",
            "allocator_config",
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
            "m4_guard_enabled",
            "m4_guard_threshold_mps",
            "m4_guard_initial_r2",
            "m4_guard_fallback_r2",
            "m4_guard_active_r2",
            "m4_guard_switched",
            "m4_guard_switch_event",
            "m4_guard_switch_tau",
            "m4_guard_switch_z",
            "m4_guard_switch_vz",
        }

        missing = required - fields

        if missing:
            raise ValueError(
                f"{path}: missing={sorted(missing)}"
            )

        actual_seed = int(
            float(rows[0]["trial_seed"])
        )

        if actual_seed != expected_seed:
            raise ValueError(
                f"{path}: seed={actual_seed}, "
                f"expected={expected_seed}"
            )

        fault_index = next(
            (
                row_index
                for row_index, row in enumerate(rows)
                if row["phase"].strip()
                == "fault_event"
            ),
            None,
        )

        if fault_index is None:
            raise ValueError(
                f"{path}: fault_event missing"
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

        controllers = {
            row["controller"].strip().lower()
            for row in rows
            if row["controller"].strip()
        }

        pre_fault_allocators = {
            row["allocator_config"].strip()
            for row in rows[:fault_index]
            if row["allocator_config"].strip()
        }

        post_fault_allocators = {
            row["allocator_config"].strip()
            for row in rows[fault_index:]
            if row["allocator_config"].strip()
        }

        candidates = {
            row["selected_candidate"].strip()
            for row in rows[fault_index:]
            if row["selected_candidate"].strip()
        }

        if controllers != {"qplite"}:
            raise ValueError(
                f"{path}: controllers={controllers}"
            )

        if pre_fault_allocators != {
            "qplite_builtin"
        }:
            raise ValueError(
                f"{path}: pre_fault_allocators="
                f"{pre_fault_allocators}"
            )

        if post_fault_allocators != {
            "manual_residual_guarded_v1"
        }:
            raise ValueError(
                f"{path}: post_fault_allocators="
                f"{post_fault_allocators}"
            )

        if candidates != {
            "guarded_opp_m2_14000_to_12000_v1"
        }:
            raise ValueError(
                f"{path}: candidates={candidates}"
            )

        logged_threshold = float(
            contact["m4_guard_threshold_mps"]
        )

        if not math.isclose(
            logged_threshold,
            threshold,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        ):
            raise ValueError(
                f"{path}: threshold="
                f"{logged_threshold}, expected={threshold}"
            )

        if int(float(
            contact["m4_guard_initial_r2"]
        )) != 14000:
            raise ValueError(
                f"{path}: wrong initial r2"
            )

        if int(float(
            contact["m4_guard_fallback_r2"]
        )) != 12000:
            raise ValueError(
                f"{path}: wrong fallback r2"
            )

        switch_rows = [
            row
            for row in rows[fault_index:]
            if parse_bool(
                row["m4_guard_switch_event"]
            )
        ]

        if len(switch_rows) > 1:
            raise ValueError(
                f"{path}: switch_count="
                f"{len(switch_rows)}"
            )

        switched = len(switch_rows) == 1

        if switched:
            switch = switch_rows[0]

            switch_tau = float(
                switch["m4_guard_switch_tau"]
            )

            switch_z = float(
                switch["m4_guard_switch_z"]
            )

            switch_vz = float(
                switch["m4_guard_switch_vz"]
            )

            expected_contact_r2 = 12000
        else:
            switch_tau = ""
            switch_z = ""
            switch_vz = ""
            expected_contact_r2 = 14000

        contact_r = (
            int(float(contact["r1"])),
            int(float(contact["r2"])),
            int(float(contact["r3"])),
            int(float(contact["r4"])),
        )

        expected_residual = (
            0,
            expected_contact_r2,
            0,
            0,
        )

        if contact_r != expected_residual:
            raise ValueError(
                f"{path}: contact residual="
                f"{contact_r}, expected="
                f"{expected_residual}"
            )

        vertical_speed = abs(
            float(contact["vz"])
        )

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
                vertical_speed <= VERTICAL_LIMIT,
            "horizontal_speed_ok":
                horizontal_speed <= HORIZONTAL_LIMIT,
            "roll_pitch_ok":
                max_tilt <= TILT_LIMIT,
            "angular_rate_ok":
                angular_rate <= ANGULAR_RATE_LIMIT,
            "drift_ok":
                drift <= DRIFT_LIMIT,
        }

        trial_rows.append(
            {
                "sequence_index":
                    int(specification[
                        "sequence_index"
                    ]),
                "guard_threshold_mps":
                    threshold,
                "repetition":
                    int(specification["repetition"]),
                "trial_seed": expected_seed,
                "guard_switched": switched,
                "switch_tau_s": switch_tau,
                "switch_z_m": switch_z,
                "switch_vz_mps": switch_vz,
                "contact_r2": expected_contact_r2,
                "safe_touchdown":
                    all(checks.values()),
                "vertical_speed_mps":
                    vertical_speed,
                "vertical_speed_margin_mps":
                    VERTICAL_LIMIT
                    - vertical_speed,
                "horizontal_speed_mps":
                    horizontal_speed,
                "max_tilt_deg": max_tilt,
                "angular_rate_radps":
                    angular_rate,
                "horizontal_drift_m": drift,
                **checks,
                "source_csv": str(path),
            }
        )

    except Exception as error:
        errors.append(str(error))

    if index % 15 == 0:
        print(
            f"[PROGRESS] audited={index}/90"
        )

if errors:
    for error in errors:
        print(f"[ERROR] {error}")

    raise SystemExit(
        f"[FAIL] Found {len(errors)} "
        "threshold-sweep audit errors."
    )

groups = defaultdict(list)

for row in trial_rows:
    groups[
        float(row["guard_threshold_mps"])
    ].append(row)

if tuple(sorted(groups)) != EXPECTED_THRESHOLDS:
    raise SystemExit(
        f"[FAIL] Thresholds={sorted(groups)}"
    )

seed_sets = {
    threshold: {
        int(row["trial_seed"])
        for row in rows
    }
    for threshold, rows in groups.items()
}

reference_seeds = seed_sets[EXPECTED_THRESHOLDS[0]]

for threshold, seed_set in seed_sets.items():
    if seed_set != reference_seeds:
        raise SystemExit(
            f"[FAIL] Seed mismatch at "
            f"threshold={threshold}"
        )

aggregate_rows = []

print()
print("========== FRESH M4 GUARD THRESHOLD SWEEP ==========")

for threshold in EXPECTED_THRESHOLDS:
    rows = groups[threshold]

    if len(rows) != 30:
        raise SystemExit(
            f"[FAIL] threshold={threshold}: "
            f"n={len(rows)}"
        )

    safe_count = sum(
        bool(row["safe_touchdown"])
        for row in rows
    )

    speeds = [
        float(row["vertical_speed_mps"])
        for row in rows
    ]

    switch_rows = [
        row
        for row in rows
        if bool(row["guard_switched"])
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
        "guard_threshold_mps": threshold,
        "n": len(rows),
        "safe_count": safe_count,
        "unsafe_count":
            len(rows) - safe_count,
        "safe_rate":
            safe_count / len(rows),
        "safe_rate_wilson95_lower":
            lower,
        "safe_rate_wilson95_upper":
            upper,
        "mean_vertical_speed_mps":
            statistics.mean(speeds),
        "median_vertical_speed_mps":
            statistics.median(speeds),
        "q90_vertical_speed_mps":
            nearest_rank(speeds, 0.90),
        "q95_vertical_speed_mps":
            nearest_rank(speeds, 0.95),
        "max_vertical_speed_mps":
            max(speeds),
        "vertical_failure_count":
            vertical_failures,
        "other_failure_count":
            other_failures,
        "switch_count":
            len(switch_rows),
        "switch_rate":
            len(switch_rows) / len(rows),
        "mean_switch_tau_s": (
            statistics.mean(
                float(row["switch_tau_s"])
                for row in switch_rows
            )
            if switch_rows
            else ""
        ),
        "mean_switch_z_m": (
            statistics.mean(
                float(row["switch_z_m"])
                for row in switch_rows
            )
            if switch_rows
            else ""
        ),
    }

    aggregate_rows.append(aggregate)

    print(
        f"guard={threshold:.2f}: "
        f"safe={safe_count}/30 "
        f"rate={safe_count / 30:.3f} "
        f"mean_vz="
        f"{statistics.mean(speeds):.6f} "
        f"q90="
        f"{aggregate['q90_vertical_speed_mps']:.6f} "
        f"q95="
        f"{aggregate['q95_vertical_speed_mps']:.6f} "
        f"max={max(speeds):.6f} "
        f"switches={len(switch_rows)}/30 "
        f"vertical_failures="
        f"{vertical_failures} "
        f"other_failures={other_failures}"
    )

pairwise_rows = []

print()
print("========== PAIRED THRESHOLD COMPARISONS ==========")

for comparison_index, (
    first_threshold,
    second_threshold,
) in enumerate(
    combinations(EXPECTED_THRESHOLDS, 2),
    start=1,
):
    first = {
        int(row["trial_seed"]): row
        for row in groups[first_threshold]
    }

    second = {
        int(row["trial_seed"]): row
        for row in groups[second_threshold]
    }

    both_safe = 0
    first_only = 0
    second_only = 0
    both_unsafe = 0

    speed_differences = []

    for seed in sorted(reference_seeds):
        first_row = first[seed]
        second_row = second[seed]

        first_safe = bool(
            first_row["safe_touchdown"]
        )

        second_safe = bool(
            second_row["safe_touchdown"]
        )

        if first_safe and second_safe:
            both_safe += 1
        elif first_safe:
            first_only += 1
        elif second_safe:
            second_only += 1
        else:
            both_unsafe += 1

        speed_differences.append(
            float(
                second_row[
                    "vertical_speed_mps"
                ]
            )
            - float(
                first_row[
                    "vertical_speed_mps"
                ]
            )
        )

    lower, upper = bootstrap_mean_interval(
        speed_differences,
        seed=20260728 + comparison_index,
    )

    pairwise = {
        "first_threshold_mps":
            first_threshold,
        "second_threshold_mps":
            second_threshold,
        "n_pairs": 30,
        "both_safe": both_safe,
        "first_only_safe": first_only,
        "second_only_safe": second_only,
        "both_unsafe": both_unsafe,
        "mcnemar_exact_two_sided_p":
            exact_mcnemar(
                first_only,
                second_only,
            ),
        "mean_vertical_speed_difference_second_minus_first":
            statistics.mean(
                speed_differences
            ),
        "bootstrap95_difference_lower":
            lower,
        "bootstrap95_difference_upper":
            upper,
    }

    pairwise_rows.append(pairwise)

    print(
        f"{second_threshold:.2f} "
        f"vs {first_threshold:.2f}: "
        f"discordant="
        f"{first_only}:{second_only} "
        f"p="
        f"{pairwise['mcnemar_exact_two_sided_p']:.8f} "
        f"mean_delta_vz="
        f"{pairwise['mean_vertical_speed_difference_second_minus_first']:+.6f} "
        f"CI=[{lower:+.6f}, "
        f"{upper:+.6f}]"
    )

trial_rows.sort(
    key=lambda row: (
        float(row["guard_threshold_mps"]),
        int(row["trial_seed"]),
    )
)

write_csv(
    root / "guard_trial_summaries.csv",
    trial_rows,
)

write_csv(
    root / "guard_aggregate.csv",
    aggregate_rows,
)

write_csv(
    root / "guard_pairwise.csv",
    pairwise_rows,
)

print()
print(
    f"[SAVED] "
    f"{root / 'guard_trial_summaries.csv'}"
)
print(
    f"[SAVED] "
    f"{root / 'guard_aggregate.csv'}"
)
print(
    f"[SAVED] "
    f"{root / 'guard_pairwise.csv'}"
)
print(
    "[PASS] Fresh paired guard-threshold "
    "analysis complete."
)
