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

QP_OUTPUT = ROOT / "qplite_recomputed_trial_summaries.csv"
PAIRED_OUTPUT = ROOT / "pinv_qplite_paired_trials.csv"
AGGREGATE_OUTPUT = ROOT / "pinv_qplite_paired_by_motor.csv"
REPORT_OUTPUT = ROOT / "pinv_qplite_paired_report.md"

EXPECTED_MOTORS = (1, 2, 3, 4)

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

        if value != "":
            return value

    return ""


def first_float(
    row: dict[str, str],
    names: Iterable[str],
) -> float:
    text = first_text(row, names)

    if text == "":
        raise ValueError(
            f"Missing numeric field from candidates {tuple(names)}"
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
    pinv_only: int,
    qplite_only: int,
) -> float:
    discordant = pinv_only + qplite_only

    if discordant == 0:
        return 1.0

    lower_tail = min(
        pinv_only,
        qplite_only,
    )

    probability = sum(
        math.comb(discordant, count)
        for count in range(lower_tail + 1)
    ) / (2 ** discordant)

    return min(1.0, 2.0 * probability)


def bootstrap_mean_interval(
    values: list[float],
    seed: int,
    repetitions: int = 20_000,
) -> tuple[float, float]:
    if not values:
        return math.nan, math.nan

    generator = random.Random(seed)
    sample_size = len(values)

    bootstrap_means = []

    for _ in range(repetitions):
        sample = [
            values[generator.randrange(sample_size)]
            for _ in range(sample_size)
        ]

        bootstrap_means.append(
            statistics.mean(sample)
        )

    bootstrap_means.sort()

    lower_index = int(
        0.025 * (repetitions - 1)
    )
    upper_index = int(
        0.975 * (repetitions - 1)
    )

    return (
        bootstrap_means[lower_index],
        bootstrap_means[upper_index],
    )


def evaluate_qplite_trial(
    path: Path,
    expected_motor: int,
) -> dict[str, object]:
    with path.open(newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        fieldnames = set(reader.fieldnames or [])

    if not 3500 <= len(rows) <= 5000:
        raise ValueError(
            f"{path}: unexpected row count {len(rows)}"
        )

    if not rows:
        raise ValueError(f"{path}: no data rows")

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

    missing = required - fieldnames

    if missing:
        raise ValueError(
            f"{path}: missing columns {sorted(missing)}"
        )

    controller_values = {
        row.get("controller", "").strip().lower()
        for row in rows
        if row.get("controller", "").strip()
    }

    if controller_values:
        if controller_values != {"qplite"}:
            raise ValueError(
                f"{path}: controller values="
                f"{sorted(controller_values)}"
            )
    elif "qplite" not in path.name.lower():
        raise ValueError(
            f"{path}: controller column is absent and "
            "the filename does not identify a QP-lite log"
        )

    seed = int(
        float(
            first_text(
                rows[0],
                ("trial_seed",),
            )
        )
    )

    fault_index = None

    for index, row in enumerate(rows):
        if row.get("phase", "").strip() == "fault_event":
            fault_index = index
            break

    if fault_index is not None:
        fault_t = row_time(rows[fault_index])
        fault_row = rows[fault_index]
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
                f"{path}: no fault-event row or fault-time field"
            )

        fault_t = float(fault_time_text)

        post_fault_candidates = [
            row
            for row in rows
            if row_time(row) >= fault_t
        ]

        if not post_fault_candidates:
            raise ValueError(
                f"{path}: no samples after fault time"
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

    pre_fault_valid = (
        fault_z >= MIN_VALID_FAULT_Z
        and abs(fault_vz)
        <= MAX_VALID_FAULT_ABS_VZ
    )

    if not pre_fault_valid:
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
            f"{path}: no first-contact row found"
        )

    vertical_speed = abs(
        first_float(
            contact_row,
            ("vz",),
        )
    )

    vx = first_float(
        contact_row,
        ("vx",),
    )
    vy = first_float(
        contact_row,
        ("vy",),
    )
    horizontal_speed = math.hypot(vx, vy)

    roll = first_float(
        contact_row,
        ("roll_deg",),
    )
    pitch = first_float(
        contact_row,
        ("pitch_deg",),
    )
    max_tilt = max(
        abs(roll),
        abs(pitch),
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

    x = first_float(
        contact_row,
        ("x",),
    )
    y = first_float(
        contact_row,
        ("y",),
    )
    horizontal_drift = math.hypot(x, y)

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

    safe_touchdown = all(checks.values())

    return {
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
        "contact_phase":
            contact_row.get("phase", ""),
        "safe_touchdown": safe_touchdown,
        "vertical_speed_mps": vertical_speed,
        "vertical_speed_margin_mps":
            VERTICAL_SPEED_LIMIT - vertical_speed,
        "horizontal_speed_mps": horizontal_speed,
        "max_tilt_deg": max_tilt,
        "angular_rate_radps": angular_rate,
        "horizontal_drift_m": horizontal_drift,
        **checks,
    }


# ----------------------------------------------------------
# Load production PINV summaries.
# ----------------------------------------------------------

with PINV_SUMMARIES.open(newline="") as file:
    pinv_rows = list(csv.DictReader(file))

if len(pinv_rows) != 120:
    raise SystemExit(
        f"[FAIL] Expected 120 PINV summaries; "
        f"found {len(pinv_rows)}"
    )

pinv_by_key: dict[
    tuple[int, int],
    dict[str, str],
] = {}

for row in pinv_rows:
    key = (
        int(row["motor"]),
        int(float(row["trial_seed"])),
    )

    if key in pinv_by_key:
        raise SystemExit(
            f"[FAIL] Duplicate PINV key {key}"
        )

    pinv_by_key[key] = row


# ----------------------------------------------------------
# Select the exact-seed-paired QP-lite blocks.
# ----------------------------------------------------------

with PAIRING_AUDIT.open(newline="") as file:
    audit_rows = list(csv.DictReader(file))

qplite_paths_by_motor: dict[int, list[Path]] = {}

for motor in EXPECTED_MOTORS:
    candidates = [
        row
        for row in audit_rows
        if (
            row["controller"] == "qplite"
            and int(row["motor"]) == motor
            and row["pairing_status"]
            == "exact_seed_paired"
            and int(row["n"]) == 30
        )
    ]

    if len(candidates) != 1:
        raise SystemExit(
            f"[FAIL] M{motor}: expected one exact paired "
            f"QP-lite block; found {len(candidates)}"
        )

    paths = [
        Path(text)
        for text in candidates[0]["paths"].split("|")
        if text
    ]

    if len(paths) != 30:
        raise SystemExit(
            f"[FAIL] M{motor}: audit contains "
            f"{len(paths)} paths"
        )

    qplite_paths_by_motor[motor] = paths


# ----------------------------------------------------------
# Recompute QP-lite outcomes from raw telemetry.
# ----------------------------------------------------------

qplite_rows: list[dict[str, object]] = []

for motor in EXPECTED_MOTORS:
    for path in qplite_paths_by_motor[motor]:
        if not path.is_file():
            raise SystemExit(
                f"[FAIL] Missing QP-lite log: {path}"
            )

        qplite_rows.append(
            evaluate_qplite_trial(
                path,
                expected_motor=motor,
            )
        )

if len(qplite_rows) != 120:
    raise SystemExit(
        f"[FAIL] Expected 120 QP-lite evaluations; "
        f"found {len(qplite_rows)}"
    )

qplite_by_key: dict[
    tuple[int, int],
    dict[str, object],
] = {}

for row in qplite_rows:
    key = (
        int(row["motor"]),
        int(row["trial_seed"]),
    )

    if key in qplite_by_key:
        raise SystemExit(
            f"[FAIL] Duplicate QP-lite key {key}"
        )

    qplite_by_key[key] = row


# ----------------------------------------------------------
# Pair by motor and exact trial seed.
# ----------------------------------------------------------

paired_rows: list[dict[str, object]] = []

for motor in EXPECTED_MOTORS:
    pinv_keys = {
        key
        for key in pinv_by_key
        if key[0] == motor
    }

    qplite_keys = {
        key
        for key in qplite_by_key
        if key[0] == motor
    }

    if pinv_keys != qplite_keys:
        missing_from_qplite = sorted(
            pinv_keys - qplite_keys
        )
        missing_from_pinv = sorted(
            qplite_keys - pinv_keys
        )

        raise SystemExit(
            f"[FAIL] M{motor} pairing mismatch: "
            f"missing_from_qplite={missing_from_qplite}, "
            f"missing_from_pinv={missing_from_pinv}"
        )

    if len(pinv_keys) != 30:
        raise SystemExit(
            f"[FAIL] M{motor} paired keys={len(pinv_keys)}"
        )

    for key in sorted(pinv_keys):
        pinv = pinv_by_key[key]
        qplite = qplite_by_key[key]

        pinv_safe = as_bool(
            pinv["safe_touchdown"]
        )
        qplite_safe = bool(
            qplite["safe_touchdown"]
        )

        pinv_speed = float(
            pinv["vertical_speed_mps"]
        )
        qplite_speed = float(
            qplite["vertical_speed_mps"]
        )

        paired_rows.append(
            {
                "motor": motor,
                "trial_seed": key[1],
                "pinv_safe": pinv_safe,
                "qplite_safe": qplite_safe,
                "pinv_vertical_speed_mps":
                    pinv_speed,
                "qplite_vertical_speed_mps":
                    qplite_speed,
                "vertical_speed_difference_pinv_minus_qplite":
                    pinv_speed - qplite_speed,
                "both_safe":
                    pinv_safe and qplite_safe,
                "pinv_only_safe":
                    pinv_safe and not qplite_safe,
                "qplite_only_safe":
                    qplite_safe and not pinv_safe,
                "both_unsafe":
                    not pinv_safe and not qplite_safe,
                "qplite_source_csv":
                    qplite["source_csv"],
            }
        )


# ----------------------------------------------------------
# Aggregate paired outcomes.
# ----------------------------------------------------------

paired_by_motor: dict[
    int,
    list[dict[str, object]],
] = defaultdict(list)

for row in paired_rows:
    paired_by_motor[int(row["motor"])].append(row)

aggregate_rows: list[dict[str, object]] = []

print(
    "========== PAIRED PINV VS QP-LITE "
    "AT ETA=0.496 =========="
)

for motor in EXPECTED_MOTORS:
    group = paired_by_motor[motor]

    if len(group) != 30:
        raise SystemExit(
            f"[FAIL] M{motor}: paired n={len(group)}"
        )

    pinv_safe_count = sum(
        bool(row["pinv_safe"])
        for row in group
    )
    qplite_safe_count = sum(
        bool(row["qplite_safe"])
        for row in group
    )

    both_safe = sum(
        bool(row["both_safe"])
        for row in group
    )
    pinv_only = sum(
        bool(row["pinv_only_safe"])
        for row in group
    )
    qplite_only = sum(
        bool(row["qplite_only_safe"])
        for row in group
    )
    both_unsafe = sum(
        bool(row["both_unsafe"])
        for row in group
    )

    differences = [
        float(
            row[
                "vertical_speed_difference_pinv_minus_qplite"
            ]
        )
        for row in group
    ]

    lower, upper = bootstrap_mean_interval(
        differences,
        seed=20260717 + motor,
    )

    aggregate = {
        "motor": motor,
        "n_pairs": len(group),
        "pinv_safe_count": pinv_safe_count,
        "qplite_safe_count": qplite_safe_count,
        "safe_count_difference_pinv_minus_qplite":
            pinv_safe_count - qplite_safe_count,
        "both_safe": both_safe,
        "pinv_only_safe": pinv_only,
        "qplite_only_safe": qplite_only,
        "both_unsafe": both_unsafe,
        "mcnemar_exact_two_sided_p":
            exact_mcnemar_p(
                pinv_only,
                qplite_only,
            ),
        "mean_pinv_vertical_speed_mps":
            statistics.mean(
                float(row["pinv_vertical_speed_mps"])
                for row in group
            ),
        "mean_qplite_vertical_speed_mps":
            statistics.mean(
                float(row["qplite_vertical_speed_mps"])
                for row in group
            ),
        "mean_speed_difference_pinv_minus_qplite":
            statistics.mean(differences),
        "median_speed_difference_pinv_minus_qplite":
            statistics.median(differences),
        "bootstrap95_mean_difference_lower":
            lower,
        "bootstrap95_mean_difference_upper":
            upper,
    }

    aggregate_rows.append(aggregate)

    print(
        f"M{motor}: "
        f"PINV={pinv_safe_count}/30 "
        f"QP-lite={qplite_safe_count}/30 "
        f"both_safe={both_safe} "
        f"PINV_only={pinv_only} "
        f"QP_only={qplite_only} "
        f"both_unsafe={both_unsafe} "
        f"McNemar_p="
        f"{aggregate['mcnemar_exact_two_sided_p']:.8f} "
        f"mean_delta_vz="
        f"{aggregate['mean_speed_difference_pinv_minus_qplite']:+.6f}"
    )


# ----------------------------------------------------------
# Save trial-level and aggregate outputs.
# ----------------------------------------------------------

with QP_OUTPUT.open("w", newline="") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=list(qplite_rows[0].keys()),
    )
    writer.writeheader()
    writer.writerows(qplite_rows)

with PAIRED_OUTPUT.open("w", newline="") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=list(paired_rows[0].keys()),
    )
    writer.writeheader()
    writer.writerows(paired_rows)

with AGGREGATE_OUTPUT.open("w", newline="") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=list(aggregate_rows[0].keys()),
    )
    writer.writeheader()
    writer.writerows(aggregate_rows)


# ----------------------------------------------------------
# Create concise report.
# ----------------------------------------------------------

lines = [
    "# Paired PINV versus QP-lite Comparison",
    "",
    "## Design",
    "",
    "- Fault effectiveness: `eta = 0.496`",
    "- Pairing key: identical motor and `trial_seed`",
    "- Paired motors: M1, M2, M3, and M4",
    "- Pairs per motor: 30",
    "- Total paired trials: 120",
    "- CEM excluded from paired inference because pairing metadata "
    "is incomplete",
    "",
    "## Results",
    "",
    "| Motor | PINV safe | QP-lite safe | PINV only | QP-lite only | McNemar p | Mean speed difference |",
    "|---:|---:|---:|---:|---:|---:|---:|",
]

for row in aggregate_rows:
    lines.append(
        f"| M{row['motor']} "
        f"| {row['pinv_safe_count']}/30 "
        f"| {row['qplite_safe_count']}/30 "
        f"| {row['pinv_only_safe']} "
        f"| {row['qplite_only_safe']} "
        f"| {float(row['mcnemar_exact_two_sided_p']):.6g} "
        f"| "
        f"{float(row['mean_speed_difference_pinv_minus_qplite']):+.6f} m/s |"
    )

lines.extend(
    [
        "",
        "A negative touchdown-speed difference favors PINV; "
        "a positive difference favors QP-lite.",
        "",
        "McNemar tests use only discordant paired safety outcomes. "
        "Each motor is treated as a separate primary comparison.",
        "",
        "The comparison is paired through the identical seeded "
        "runner inputs. Spatial spawn metadata should not be "
        "interpreted as verified physical simulator perturbation "
        "unless independently confirmed by the launcher.",
    ]
)

REPORT_OUTPUT.write_text(
    "\n".join(lines) + "\n"
)

print()
print(f"[SAVED] {QP_OUTPUT}")
print(f"[SAVED] {PAIRED_OUTPUT}")
print(f"[SAVED] {AGGREGATE_OUTPUT}")
print(f"[SAVED] {REPORT_OUTPUT}")
print("[PASS] Exact 120-trial paired comparison complete.")
