#!/usr/bin/env python3

from __future__ import annotations

import csv
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable


ROOT = Path(
    "results/final/pinv_baseline/"
    "seeded_eta0p496/production_30"
)

PINV_SUMMARIES = ROOT / "all_trial_summaries.csv"
PAIRING_AUDIT = ROOT / "comparator_pairing_audit.csv"

RECOMPUTED_OUTPUT = (
    ROOT / "qplite_cem_recomputed_trial_summaries.csv"
)
PAIRED_OUTPUT = (
    ROOT / "three_controller_paired_trials.csv"
)
MOTOR_OUTPUT = (
    ROOT / "three_controller_summary_by_motor.csv"
)
PAIRWISE_OUTPUT = (
    ROOT / "three_controller_pairwise_by_motor.csv"
)
REPORT_OUTPUT = (
    ROOT / "three_controller_paired_report.md"
)

MOTORS = (1, 2, 3, 4)

CONTROLLERS = (
    "pinv",
    "qplite",
    "cem_tuned",
)

PAIRWISE_COMPARISONS = (
    ("pinv", "qplite"),
    ("pinv", "cem_tuned"),
    ("qplite", "cem_tuned"),
)

VERTICAL_SPEED_LIMIT = 0.35
HORIZONTAL_SPEED_LIMIT = 0.25
TILT_LIMIT_DEG = 12.0
ANGULAR_RATE_LIMIT_RADPS = 1.5
DRIFT_LIMIT_M = 0.75

MIN_VALID_FAULT_Z = 0.50
MAX_VALID_FAULT_ABS_VZ = 0.25


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


def first_float(
    row: dict[str, str],
    names: Iterable[str],
) -> float:
    text = first_text(row, names)

    if not text:
        raise ValueError(
            f"Missing numeric field from {tuple(names)}"
        )

    return float(text)


def row_time(row: dict[str, str]) -> float:
    return first_float(
        row,
        (
            "t",
            "time",
            "time_s",
            "elapsed_s",
        ),
    )


def exact_mcnemar_p(
    first_only: int,
    second_only: int,
) -> float:
    discordant = first_only + second_only

    if discordant == 0:
        return 1.0

    lower = min(first_only, second_only)

    one_tail = sum(
        math.comb(discordant, count)
        for count in range(lower + 1)
    ) / (2 ** discordant)

    return min(1.0, 2.0 * one_tail)


def bootstrap_mean_interval(
    values: list[float],
    seed: int,
    repetitions: int = 20_000,
) -> tuple[float, float]:
    if not values:
        return math.nan, math.nan

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

    lower_index = int(
        0.025 * (repetitions - 1)
    )
    upper_index = int(
        0.975 * (repetitions - 1)
    )

    return (
        estimates[lower_index],
        estimates[upper_index],
    )


def holm_adjust(
    p_values: list[float],
) -> list[float]:
    number = len(p_values)

    order = sorted(
        range(number),
        key=lambda index: p_values[index],
    )

    adjusted = [1.0] * number
    running_maximum = 0.0

    for rank, index in enumerate(order):
        multiplier = number - rank

        candidate = min(
            1.0,
            multiplier * p_values[index],
        )

        running_maximum = max(
            running_maximum,
            candidate,
        )

        adjusted[index] = running_maximum

    return adjusted


def cochran_q(
    matrix: list[list[int]],
) -> tuple[float, float]:
    if not matrix:
        return math.nan, math.nan

    treatments = len(matrix[0])

    column_sums = [
        sum(row[column] for row in matrix)
        for column in range(treatments)
    ]

    row_sums = [
        sum(row)
        for row in matrix
    ]

    total = sum(column_sums)

    denominator = (
        treatments * total
        - sum(value * value for value in row_sums)
    )

    if denominator <= 0:
        return 0.0, 1.0

    numerator = (
        (treatments - 1)
        * (
            treatments
            * sum(value * value for value in column_sums)
            - total * total
        )
    )

    statistic = numerator / denominator

    # There are three controllers, so Cochran's Q has df=2.
    # The chi-square survival function for df=2 is exp(-Q/2).
    p_value = math.exp(-statistic / 2.0)

    return statistic, p_value


def evaluate_event_allocator_trial(
    path: Path,
    expected_motor: int,
    expected_configuration: str,
) -> dict[str, object]:
    with path.open(newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        fields = set(reader.fieldnames or [])

    if not 3500 <= len(rows) <= 5000:
        raise ValueError(
            f"{path}: unexpected row count={len(rows)}"
        )

    required = {
        "phase",
        "z",
        "vz",
        "vx",
        "vy",
        "x",
        "y",
        "roll_deg",
        "pitch_deg",
        "trial_seed",
    }

    missing = required - fields

    if missing:
        raise ValueError(
            f"{path}: missing columns={sorted(missing)}"
        )

    filename = path.name.lower()
    allocator_values = {
        row.get("allocator_config", "").strip().lower()
        for row in rows
        if row.get("allocator_config", "").strip()
    }

    controller_values = {
        row.get("controller", "").strip().lower()
        for row in rows
        if row.get("controller", "").strip()
    }

    if expected_configuration == "qplite":
        if "seededfine_qplite" not in filename:
            raise ValueError(
                f"{path}: filename does not identify QP-lite"
            )

        if any(
            "cem" in value
            for value in allocator_values
        ):
            raise ValueError(
                f"{path}: QP-lite log contains CEM allocator metadata"
            )

    elif expected_configuration == "cem_tuned":
        if "seededfine_cem" not in filename:
            raise ValueError(
                f"{path}: filename does not identify CEM-tuned run"
            )

        if not any(
            "cem" in value
            for value in allocator_values
        ):
            raise ValueError(
                f"{path}: CEM-tuned allocator metadata missing"
            )

    else:
        raise ValueError(
            f"Unknown configuration: {expected_configuration}"
        )

    # Both baseline and CEM-tuned configurations execute through
    # the QP-lite runtime allocator.
    if controller_values and controller_values != {"qplite"}:
        raise ValueError(
            f"{path}: unexpected runtime controllers="
            f"{sorted(controller_values)}"
        )

    seed = int(
        float(rows[0]["trial_seed"])
    )

    fault_index = None

    for index, row in enumerate(rows):
        if row.get("phase", "").strip() == "fault_event":
            fault_index = index
            break

    if fault_index is not None:
        fault_row = rows[fault_index]
        fault_t = row_time(fault_row)
    else:
        fault_time_text = ""

        for row in rows:
            fault_time_text = first_text(
                row,
                (
                    "fault_time_cmd",
                    "fault_time",
                    "fault_time_s",
                ),
            )

            if fault_time_text:
                break

        if not fault_time_text:
            raise ValueError(
                f"{path}: no fault event or fault time"
            )

        fault_t = float(fault_time_text)

        post_fault_candidates = [
            row
            for row in rows
            if row_time(row) >= fault_t
        ]

        if not post_fault_candidates:
            raise ValueError(
                f"{path}: no post-fault samples"
            )

        fault_row = post_fault_candidates[0]

    fault_z = first_float(
        fault_row,
        ("z",),
    )
    fault_vz = first_float(
        fault_row,
        ("vz",),
    )

    if (
        fault_z < MIN_VALID_FAULT_Z
        or abs(fault_vz)
        > MAX_VALID_FAULT_ABS_VZ
    ):
        raise ValueError(
            f"{path}: invalid pre-fault state "
            f"z={fault_z}, vz={fault_vz}"
        )

    post_fault_rows = [
        row
        for row in rows
        if row_time(row) >= fault_t
    ]

    contact_row = None

    for row in post_fault_rows:
        if first_float(row, ("z",)) <= 0.03:
            contact_row = row
            break

    if contact_row is None:
        raise ValueError(
            f"{path}: no first-contact row"
        )

    vertical_speed = abs(
        first_float(contact_row, ("vz",))
    )

    horizontal_speed = math.hypot(
        first_float(contact_row, ("vx",)),
        first_float(contact_row, ("vy",)),
    )

    max_tilt = max(
        abs(first_float(contact_row, ("roll_deg",))),
        abs(first_float(contact_row, ("pitch_deg",))),
    )

    gyro_x = first_float(
        contact_row,
        (
            "gyro_x_deg_s",
            "gyro_x",
        ),
    )
    gyro_y = first_float(
        contact_row,
        (
            "gyro_y_deg_s",
            "gyro_y",
        ),
    )
    gyro_z = first_float(
        contact_row,
        (
            "gyro_z_deg_s",
            "gyro_z",
        ),
    )

    angular_rate = math.radians(
        math.sqrt(
            gyro_x * gyro_x
            + gyro_y * gyro_y
            + gyro_z * gyro_z
        )
    )

    horizontal_drift = math.hypot(
        first_float(contact_row, ("x",)),
        first_float(contact_row, ("y",)),
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
            horizontal_drift <= DRIFT_LIMIT_M,
    }

    return {
        "configuration": expected_configuration,
        "motor": expected_motor,
        "trial_seed": seed,
        "source_csv": str(path),
        "rows": len(rows),
        "actual_fault_t": fault_t,
        "fault_z": fault_z,
        "fault_vz": fault_vz,
        "contact_found": True,
        "contact_t": row_time(contact_row),
        "fault_to_contact_s":
            row_time(contact_row) - fault_t,
        "safe_touchdown": all(checks.values()),
        "vertical_speed_mps": vertical_speed,
        "vertical_speed_margin_mps":
            VERTICAL_SPEED_LIMIT - vertical_speed,
        "horizontal_speed_mps": horizontal_speed,
        "max_tilt_deg": max_tilt,
        "angular_rate_radps": angular_rate,
        "horizontal_drift_m": horizontal_drift,
        **checks,
    }


with PINV_SUMMARIES.open(newline="") as file:
    pinv_rows = list(csv.DictReader(file))

if len(pinv_rows) != 120:
    raise SystemExit(
        f"[FAIL] Expected 120 PINV summaries; "
        f"found {len(pinv_rows)}"
    )

trial_data: dict[
    tuple[str, int, int],
    dict[str, object],
] = {}

for row in pinv_rows:
    key = (
        "pinv",
        int(row["motor"]),
        int(float(row["trial_seed"])),
    )

    trial_data[key] = {
        "configuration": "pinv",
        "motor": int(row["motor"]),
        "trial_seed": int(float(row["trial_seed"])),
        "safe_touchdown":
            as_bool(row["safe_touchdown"]),
        "vertical_speed_mps":
            float(row["vertical_speed_mps"]),
        "source_csv":
            row.get("summary_file", ""),
    }


with PAIRING_AUDIT.open(newline="") as file:
    audit_rows = list(csv.DictReader(file))

recomputed_rows = []

for audit_controller, configuration in (
    ("qplite", "qplite"),
    ("cem", "cem_tuned"),
):
    for motor in MOTORS:
        candidates = [
            row
            for row in audit_rows
            if (
                row["controller"] == audit_controller
                and int(row["motor"]) == motor
                and row["pairing_status"]
                == "exact_seed_paired"
                and int(row["n"]) == 30
            )
        ]

        if len(candidates) != 1:
            raise SystemExit(
                f"[FAIL] {configuration} M{motor}: "
                f"expected one exact block; "
                f"found {len(candidates)}"
            )

        paths = [
            Path(value)
            for value in candidates[0]["paths"].split("|")
            if value
        ]

        if len(paths) != 30:
            raise SystemExit(
                f"[FAIL] {configuration} M{motor}: "
                f"path count={len(paths)}"
            )

        for path in paths:
            result = evaluate_event_allocator_trial(
                path,
                expected_motor=motor,
                expected_configuration=configuration,
            )

            key = (
                configuration,
                motor,
                int(result["trial_seed"]),
            )

            if key in trial_data:
                raise SystemExit(
                    f"[FAIL] Duplicate trial key={key}"
                )

            trial_data[key] = result
            recomputed_rows.append(result)


if len(recomputed_rows) != 240:
    raise SystemExit(
        f"[FAIL] Expected 240 recomputed rows; "
        f"found {len(recomputed_rows)}"
    )


paired_rows = []

for motor in MOTORS:
    expected_seeds = {
        motor * 10_000_000
        + 4_980_000
        + repetition
        for repetition in range(1, 31)
    }

    for configuration in CONTROLLERS:
        actual_seeds = {
            seed
            for (
                controller,
                trial_motor,
                seed,
            ) in trial_data
            if (
                controller == configuration
                and trial_motor == motor
            )
        }

        if actual_seeds != expected_seeds:
            raise SystemExit(
                f"[FAIL] {configuration} M{motor}: "
                "seed-set mismatch"
            )

    for seed in sorted(expected_seeds):
        pinv = trial_data[("pinv", motor, seed)]
        qplite = trial_data[("qplite", motor, seed)]
        cem = trial_data[("cem_tuned", motor, seed)]

        paired_rows.append(
            {
                "motor": motor,
                "trial_seed": seed,
                "pinv_safe":
                    bool(pinv["safe_touchdown"]),
                "qplite_safe":
                    bool(qplite["safe_touchdown"]),
                "cem_tuned_safe":
                    bool(cem["safe_touchdown"]),
                "pinv_vertical_speed_mps":
                    float(pinv["vertical_speed_mps"]),
                "qplite_vertical_speed_mps":
                    float(qplite["vertical_speed_mps"]),
                "cem_tuned_vertical_speed_mps":
                    float(cem["vertical_speed_mps"]),
            }
        )


by_motor = defaultdict(list)

for row in paired_rows:
    by_motor[int(row["motor"])].append(row)


motor_rows = []
pairwise_rows = []

print(
    "========== EXACT MATCHED THREE-CONTROLLER "
    "COMPARISON =========="
)

for motor in MOTORS:
    group = by_motor[motor]

    matrix = [
        [
            int(bool(row["pinv_safe"])),
            int(bool(row["qplite_safe"])),
            int(bool(row["cem_tuned_safe"])),
        ]
        for row in group
    ]

    q_statistic, q_p_value = cochran_q(matrix)

    counts = {
        controller: sum(
            bool(row[f"{controller}_safe"])
            for row in group
        )
        for controller in CONTROLLERS
    }

    means = {
        controller: statistics.mean(
            float(
                row[
                    f"{controller}_vertical_speed_mps"
                ]
            )
            for row in group
        )
        for controller in CONTROLLERS
    }

    motor_rows.append(
        {
            "motor": motor,
            "n_pairs": len(group),
            "pinv_safe_count": counts["pinv"],
            "qplite_safe_count": counts["qplite"],
            "cem_tuned_safe_count":
                counts["cem_tuned"],
            "pinv_mean_vertical_speed_mps":
                means["pinv"],
            "qplite_mean_vertical_speed_mps":
                means["qplite"],
            "cem_tuned_mean_vertical_speed_mps":
                means["cem_tuned"],
            "cochran_q": q_statistic,
            "cochran_q_p": q_p_value,
        }
    )

    print(
        f"M{motor}: "
        f"PINV={counts['pinv']}/30 "
        f"QP-lite={counts['qplite']}/30 "
        f"CEM-tuned={counts['cem_tuned']}/30 "
        f"Cochran_Q={q_statistic:.6f} "
        f"p={q_p_value:.8f}"
    )

    for comparison_index, (
        first,
        second,
    ) in enumerate(PAIRWISE_COMPARISONS):
        first_only = sum(
            bool(row[f"{first}_safe"])
            and not bool(row[f"{second}_safe"])
            for row in group
        )

        second_only = sum(
            bool(row[f"{second}_safe"])
            and not bool(row[f"{first}_safe"])
            for row in group
        )

        both_safe = sum(
            bool(row[f"{first}_safe"])
            and bool(row[f"{second}_safe"])
            for row in group
        )

        both_unsafe = sum(
            not bool(row[f"{first}_safe"])
            and not bool(row[f"{second}_safe"])
            for row in group
        )

        differences = [
            float(
                row[
                    f"{first}_vertical_speed_mps"
                ]
            )
            - float(
                row[
                    f"{second}_vertical_speed_mps"
                ]
            )
            for row in group
        ]

        lower, upper = bootstrap_mean_interval(
            differences,
            seed=(
                20260718
                + motor * 100
                + comparison_index
            ),
        )

        pairwise_rows.append(
            {
                "motor": motor,
                "first": first,
                "second": second,
                "n_pairs": len(group),
                "first_safe_count": counts[first],
                "second_safe_count": counts[second],
                "both_safe": both_safe,
                "first_only_safe": first_only,
                "second_only_safe": second_only,
                "both_unsafe": both_unsafe,
                "mcnemar_exact_p":
                    exact_mcnemar_p(
                        first_only,
                        second_only,
                    ),
                "mean_speed_difference_first_minus_second":
                    statistics.mean(differences),
                "median_speed_difference_first_minus_second":
                    statistics.median(differences),
                "bootstrap95_mean_difference_lower":
                    lower,
                "bootstrap95_mean_difference_upper":
                    upper,
            }
        )


global_adjusted = holm_adjust(
    [
        float(row["mcnemar_exact_p"])
        for row in pairwise_rows
    ]
)

for row, adjusted in zip(
    pairwise_rows,
    global_adjusted,
):
    row["mcnemar_holm12_p"] = adjusted


for motor in MOTORS:
    indices = [
        index
        for index, row in enumerate(pairwise_rows)
        if int(row["motor"]) == motor
    ]

    adjusted = holm_adjust(
        [
            float(pairwise_rows[index]["mcnemar_exact_p"])
            for index in indices
        ]
    )

    for index, value in zip(indices, adjusted):
        pairwise_rows[index][
            "mcnemar_holm_within_motor_p"
        ] = value


print()
print("========== PAIRWISE TESTS ==========")

for row in pairwise_rows:
    print(
        f"M{row['motor']} "
        f"{row['first']} vs {row['second']}: "
        f"{row['first_safe_count']}/30 vs "
        f"{row['second_safe_count']}/30 "
        f"discordant="
        f"{row['first_only_safe']}:"
        f"{row['second_only_safe']} "
        f"p={float(row['mcnemar_exact_p']):.8f} "
        f"Holm12="
        f"{float(row['mcnemar_holm12_p']):.8f} "
        f"mean_delta_vz="
        f"{float(row['mean_speed_difference_first_minus_second']):+.6f} "
        f"CI=["
        f"{float(row['bootstrap95_mean_difference_lower']):+.6f}, "
        f"{float(row['bootstrap95_mean_difference_upper']):+.6f}]"
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


write_csv(RECOMPUTED_OUTPUT, recomputed_rows)
write_csv(PAIRED_OUTPUT, paired_rows)
write_csv(MOTOR_OUTPUT, motor_rows)
write_csv(PAIRWISE_OUTPUT, pairwise_rows)


report_lines = [
    "# Exact Matched Three-Controller Comparison",
    "",
    "## Design",
    "",
    "- Fault effectiveness: `eta = 0.496`",
    "- Four failed-motor geometries",
    "- 30 identical seeds per motor and configuration",
    "- Total: 360 controller-trial observations",
    "- PINV: bounded weighted least-squares allocator",
    "- QP-lite: baseline event allocator",
    "- CEM-tuned: QP-lite runtime allocator using weights "
    "tuned offline by cross-entropy method",
    "",
    "## Motor-level outcomes",
    "",
    "| Motor | PINV | QP-lite | CEM-tuned | Cochran Q p |",
    "|---:|---:|---:|---:|---:|",
]

for row in motor_rows:
    report_lines.append(
        f"| M{row['motor']} "
        f"| {row['pinv_safe_count']}/30 "
        f"| {row['qplite_safe_count']}/30 "
        f"| {row['cem_tuned_safe_count']}/30 "
        f"| {float(row['cochran_q_p']):.6g} |"
    )

report_lines.extend(
    [
        "",
        "Pairwise safety comparisons use exact two-sided "
        "McNemar tests. `mcnemar_holm12_p` adjusts across all "
        "12 motor-comparison tests.",
        "",
        "Touchdown-speed differences are paired as "
        "`first - second`; negative values favor the first "
        "configuration.",
    ]
)

REPORT_OUTPUT.write_text(
    "\n".join(report_lines) + "\n"
)

print()
print(f"[SAVED] {RECOMPUTED_OUTPUT}")
print(f"[SAVED] {PAIRED_OUTPUT}")
print(f"[SAVED] {MOTOR_OUTPUT}")
print(f"[SAVED] {PAIRWISE_OUTPUT}")
print(f"[SAVED] {REPORT_OUTPUT}")
print("[PASS] Exact 360-observation paired analysis complete.")
