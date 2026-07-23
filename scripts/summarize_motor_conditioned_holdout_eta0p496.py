#!/usr/bin/env python3

from __future__ import annotations

import csv
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


PROJECT = Path.cwd()
LOG_DIR = PROJECT / "logs"

ROOT = Path(
    "results/final/pinv_baseline/"
    "seeded_eta0p496/motor_conditioned_holdout"
)

TRIAL_OUTPUT = ROOT / "holdout_trial_summaries.csv"
AGGREGATE_OUTPUT = ROOT / "holdout_aggregate_by_motor.csv"
MANIFEST_OUTPUT = ROOT / "holdout_manifest.txt"
AUDIT_OUTPUT = ROOT / "holdout_audit.txt"
REPORT_OUTPUT = ROOT / "holdout_report.md"

ETA = 0.496

VERTICAL_SPEED_LIMIT = 0.35
HORIZONTAL_SPEED_LIMIT = 0.25
TILT_LIMIT_DEG = 12.0
ANGULAR_RATE_LIMIT_RADPS = 1.5
DRIFT_LIMIT_M = 0.75

MIN_VALID_FAULT_Z = 0.50
MAX_VALID_FAULT_ABS_VZ = 0.25

DEVELOPMENT_SAFE_COUNTS = {
    1: 30,
    2: 30,
    3: 29,
    4: 23,
}


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
    value = first_text(row, names)

    if not value:
        raise ValueError(
            f"Missing numeric field from {tuple(names)}"
        )

    return float(value)


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


def expected_trial(
    motor: int,
    repetition: int,
) -> dict[str, object]:
    seed = (
        motor * 10_000_000
        + 5_080_000
        + repetition
    )

    if motor == 2:
        configuration = "pinv"
        filename = (
            f"qp_event_allocator_m2_eta0p496_"
            f"seededpinv_pinv_m2_eta0p496_"
            f"seed{seed}.csv"
        )
    else:
        configuration = "cem_tuned"
        filename = (
            f"qp_event_allocator_m{motor}_eta0p496_"
            f"seededfine_cem_m{motor}_eta0p496_"
            f"seed{seed}.csv"
        )

    return {
        "motor": motor,
        "repetition": repetition,
        "trial_seed": seed,
        "configuration": configuration,
        "path": LOG_DIR / filename,
    }


def evaluate_trial(
    specification: dict[str, object],
) -> dict[str, object]:
    path = Path(specification["path"])
    motor = int(specification["motor"])
    seed = int(specification["trial_seed"])
    configuration = str(
        specification["configuration"]
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
        "protocol_id",
        "allocator_config",
        "z",
        "vz",
        "x",
        "y",
        "vx",
        "vy",
        "roll_deg",
        "pitch_deg",
    }

    missing = required - fields

    if missing:
        raise ValueError(
            f"{path}: missing columns={sorted(missing)}"
        )

    csv_seed = int(
        float(rows[0]["trial_seed"])
    )

    if csv_seed != seed:
        raise ValueError(
            f"{path}: expected seed={seed}, "
            f"CSV seed={csv_seed}"
        )

    protocol_ids = {
        row.get("protocol_id", "").strip()
        for row in rows
        if row.get("protocol_id", "").strip()
    }

    if protocol_ids != {"seeded_ic_v1"}:
        raise ValueError(
            f"{path}: protocols={sorted(protocol_ids)}"
        )

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

    if configuration == "cem_tuned":
        if "seededfine_cem" not in path.name.lower():
            raise ValueError(
                f"{path}: filename does not identify CEM"
            )

        if not any(
            "cem" in value
            for value in allocator_values
        ):
            raise ValueError(
                f"{path}: CEM allocator metadata missing"
            )

        if (
            controller_values
            and controller_values != {"qplite"}
        ):
            raise ValueError(
                f"{path}: unexpected runtime controller="
                f"{sorted(controller_values)}"
            )

    elif configuration == "pinv":
        if "seededpinv_pinv" not in path.name.lower():
            raise ValueError(
                f"{path}: filename does not identify PINV"
            )

        if controller_values != {"pinv"}:
            raise ValueError(
                f"{path}: controllers="
                f"{sorted(controller_values)}"
            )

        if not any(
            "pinv_bounded_wls" in value
            for value in allocator_values
        ):
            raise ValueError(
                f"{path}: PINV allocator metadata missing"
            )

    else:
        raise ValueError(
            f"Unknown configuration={configuration}"
        )

    fault_index = None

    for index, row in enumerate(rows):
        if row.get("phase", "").strip() == "fault_event":
            fault_index = index
            break

    if fault_index is None:
        raise ValueError(
            f"{path}: no fault_event row"
        )

    fault_row = rows[fault_index]
    fault_t = row_time(fault_row)

    fault_z = first_float(
        fault_row,
        ("z",),
    )
    fault_vz = first_float(
        fault_row,
        ("vz",),
    )

    if fault_z < MIN_VALID_FAULT_Z:
        raise ValueError(
            f"{path}: invalid fault_z={fault_z}"
        )

    if abs(fault_vz) > MAX_VALID_FAULT_ABS_VZ:
        raise ValueError(
            f"{path}: invalid fault_vz={fault_vz}"
        )

    post_fault_rows = rows[fault_index:]

    contact_row = None
    contact_index = None

    for index, row in enumerate(
        post_fault_rows,
        start=fault_index,
    ):
        if first_float(row, ("z",)) <= 0.03:
            contact_row = row
            contact_index = index
            break

    if contact_row is None:
        raise ValueError(
            f"{path}: first contact was not found"
        )

    contact_t = row_time(contact_row)

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

    pinv_scaling_verified = ""

    if configuration == "pinv":
        active_mask = int(
            float(
                first_text(
                    contact_row,
                    ("pinv_active_mask",),
                )
            )
        )

        allocation = int(
            float(
                first_text(
                    contact_row,
                    ("pinv_alloc_m2",),
                )
            )
        )

        applied = int(
            float(
                first_text(
                    contact_row,
                    ("motor_m2",),
                )
            )
        )

        expected_applied = math.floor(
            ETA * allocation
        )

        if active_mask != 2:
            raise ValueError(
                f"{path}: contact PINV mask={active_mask}"
            )

        if allocation != 65535:
            raise ValueError(
                f"{path}: contact M2 allocation={allocation}"
            )

        if abs(applied - expected_applied) > 1:
            adjacent_rows = rows[
                max(0, contact_index - 1):
                min(len(rows), contact_index + 2)
            ]

            adjacent_applied = [
                int(float(row.get("motor_m2", "0")))
                for row in adjacent_rows
            ]

            if not any(
                abs(value - expected_applied) <= 1
                for value in adjacent_applied
            ):
                raise ValueError(
                    f"{path}: PINV scaling mismatch; "
                    f"allocation={allocation}, "
                    f"expected={expected_applied}, "
                    f"contact_applied={applied}, "
                    f"adjacent={adjacent_applied}"
                )

        pinv_scaling_verified = True

    return {
        "motor": motor,
        "repetition":
            int(specification["repetition"]),
        "trial_seed": seed,
        "configuration": configuration,
        "source_csv": str(path),
        "rows": len(rows),
        "actual_fault_t": fault_t,
        "fault_z": fault_z,
        "fault_vz": fault_vz,
        "contact_found": True,
        "contact_t": contact_t,
        "fault_to_contact_s":
            contact_t - fault_t,
        "contact_phase":
            contact_row.get("phase", ""),
        "selected_candidate":
            contact_row.get("selected_candidate", ""),
        "safe_touchdown": all(checks.values()),
        "vertical_speed_mps": vertical_speed,
        "vertical_speed_margin_mps":
            VERTICAL_SPEED_LIMIT - vertical_speed,
        "horizontal_speed_mps": horizontal_speed,
        "max_tilt_deg": max_tilt,
        "angular_rate_radps": angular_rate,
        "horizontal_drift_m": horizontal_drift,
        **checks,
        "pinv_scaling_verified":
            pinv_scaling_verified,
    }


ROOT.mkdir(parents=True, exist_ok=True)

specifications = [
    expected_trial(motor, repetition)
    for motor in (1, 2, 3, 4)
    for repetition in range(1, 31)
]

trial_rows = []
errors = []

for index, specification in enumerate(
    specifications,
    start=1,
):
    try:
        trial_rows.append(
            evaluate_trial(specification)
        )
    except Exception as error:
        errors.append(str(error))

    if index % 20 == 0:
        print(
            f"[PROGRESS] audited={index}/120"
        )

if errors:
    for error in errors:
        print(f"[ERROR] {error}")

    raise SystemExit(
        f"[FAIL] Holdout audit found "
        f"{len(errors)} error(s)."
    )

if len(trial_rows) != 120:
    raise SystemExit(
        f"[FAIL] Valid trials={len(trial_rows)}"
    )

by_motor: dict[
    int,
    list[dict[str, object]],
] = defaultdict(list)

for row in trial_rows:
    by_motor[int(row["motor"])].append(row)

aggregate_rows = []

print()
print(
    "========== MOTOR-CONDITIONED "
    "FRESH-SEED HOLDOUT =========="
)

for motor in (1, 2, 3, 4):
    group = by_motor[motor]

    if len(group) != 30:
        raise SystemExit(
            f"[FAIL] M{motor}: n={len(group)}"
        )

    safe_count = sum(
        bool(row["safe_touchdown"])
        for row in group
    )

    contact_count = sum(
        bool(row["contact_found"])
        for row in group
    )

    vertical_speeds = [
        float(row["vertical_speed_mps"])
        for row in group
    ]

    margins = [
        float(row["vertical_speed_margin_mps"])
        for row in group
    ]

    lower, upper = wilson_interval(
        safe_count,
        len(group),
    )

    vertical_failures = sum(
        not bool(row["vertical_speed_ok"])
        for row in group
    )

    horizontal_failures = sum(
        not bool(row["horizontal_speed_ok"])
        for row in group
    )

    tilt_failures = sum(
        not bool(row["roll_pitch_ok"])
        for row in group
    )

    angular_rate_failures = sum(
        not bool(row["angular_rate_ok"])
        for row in group
    )

    drift_failures = sum(
        not bool(row["drift_ok"])
        for row in group
    )

    configuration = str(
        group[0]["configuration"]
    )

    aggregate = {
        "motor": motor,
        "configuration": configuration,
        "n": len(group),
        "contact_count": contact_count,
        "safe_count": safe_count,
        "unsafe_count": len(group) - safe_count,
        "safe_rate": safe_count / len(group),
        "safe_rate_wilson95_lower": lower,
        "safe_rate_wilson95_upper": upper,
        "development_safe_count":
            DEVELOPMENT_SAFE_COUNTS[motor],
        "holdout_minus_development_safe_count":
            safe_count
            - DEVELOPMENT_SAFE_COUNTS[motor],
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
        "minimum_vertical_speed_margin_mps":
            min(margins),
        "vertical_speed_failure_count":
            vertical_failures,
        "horizontal_speed_failure_count":
            horizontal_failures,
        "tilt_failure_count":
            tilt_failures,
        "angular_rate_failure_count":
            angular_rate_failures,
        "drift_failure_count":
            drift_failures,
    }

    aggregate_rows.append(aggregate)

    print(
        f"M{motor}: "
        f"policy={configuration} "
        f"contact={contact_count}/30 "
        f"safe={safe_count}/30 "
        f"rate={safe_count / 30:.3f} "
        f"Wilson95=[{lower:.3f}, {upper:.3f}] "
        f"mean_vz="
        f"{statistics.mean(vertical_speeds):.6f} "
        f"range=["
        f"{min(vertical_speeds):.6f}, "
        f"{max(vertical_speeds):.6f}] "
        f"vertical_failures={vertical_failures}"
    )

overall_safe = sum(
    int(row["safe_count"])
    for row in aggregate_rows
)

overall_contact = sum(
    int(row["contact_count"])
    for row in aggregate_rows
)

overall_lower, overall_upper = wilson_interval(
    overall_safe,
    120,
)

non_vertical_failures = sum(
    int(row["horizontal_speed_failure_count"])
    + int(row["tilt_failure_count"])
    + int(row["angular_rate_failure_count"])
    + int(row["drift_failure_count"])
    for row in aggregate_rows
)

print()
print("========== OVERALL HOLDOUT ==========")
print(f"contact={overall_contact}/120")
print(f"safe={overall_safe}/120")
print(f"safe_rate={overall_safe / 120:.6f}")
print(
    f"Wilson95=[{overall_lower:.6f}, "
    f"{overall_upper:.6f}]"
)
print(
    "development_selected_policy="
    "112/120"
)
print(
    "holdout_minus_development_safe_count="
    f"{overall_safe - 112}"
)
print(
    f"non_vertical_safety_failures="
    f"{non_vertical_failures}"
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


write_csv(TRIAL_OUTPUT, trial_rows)
write_csv(AGGREGATE_OUTPUT, aggregate_rows)

MANIFEST_OUTPUT.write_text(
    "\n".join(
        str(row["source_csv"])
        for row in trial_rows
    )
    + "\n"
)

configuration_counts = Counter(
    str(row["configuration"])
    for row in trial_rows
)

audit_lines = [
    "expected_trials=120",
    f"validated_trials={len(trial_rows)}",
    f"contact_trials={overall_contact}",
    "eta=0.496",
    "protocol_id=seeded_ic_v1",
    "base_seed=120000",
    "holdout_seed_offset=5080000",
    (
        "policy="
        "M1:CEM-tuned,M2:PINV,"
        "M3:CEM-tuned,M4:CEM-tuned"
    ),
    (
        f"cem_tuned_trials="
        f"{configuration_counts['cem_tuned']}"
    ),
    (
        f"pinv_trials="
        f"{configuration_counts['pinv']}"
    ),
]

AUDIT_OUTPUT.write_text(
    "\n".join(audit_lines) + "\n"
)

report_lines = [
    "# Motor-Conditioned Allocator Fresh-Seed Holdout",
    "",
    "## Fixed policy",
    "",
    "- M1: CEM-tuned QP-lite",
    "- M2: bounded weighted least squares/PINV",
    "- M3: CEM-tuned QP-lite",
    "- M4: CEM-tuned QP-lite",
    "",
    "The policy was selected using the previous matched "
    "development seed block and evaluated here on a fresh "
    "30-seed block per motor.",
    "",
    "## Holdout outcomes",
    "",
    "| Motor | Configuration | Safe | Rate | Wilson 95% CI | Mean vertical speed |",
    "|---:|:---|---:|---:|---:|---:|",
]

for row in aggregate_rows:
    report_lines.append(
        f"| M{row['motor']} "
        f"| {row['configuration']} "
        f"| {row['safe_count']}/30 "
        f"| {100 * float(row['safe_rate']):.1f}% "
        f"| "
        f"[{100 * float(row['safe_rate_wilson95_lower']):.1f}%, "
        f"{100 * float(row['safe_rate_wilson95_upper']):.1f}%] "
        f"| {float(row['mean_vertical_speed_mps']):.6f} m/s |"
    )

report_lines.extend(
    [
        "",
        (
            f"Overall holdout performance: "
            f"**{overall_safe}/120 "
            f"({100 * overall_safe / 120:.1f}%)**."
        ),
        "",
        (
            "Overall Wilson 95% interval: "
            f"**[{100 * overall_lower:.1f}%, "
            f"{100 * overall_upper:.1f}%]**."
        ),
        "",
        (
            "Development selected-policy result: "
            "**112/120 (93.3%)**."
        ),
        "",
        (
            "This is a fresh-seed validation under the same "
            "simulator and initial-condition distribution. "
            "It is not evidence of transfer to hardware or "
            "to a different fault distribution."
        ),
    ]
)

REPORT_OUTPUT.write_text(
    "\n".join(report_lines) + "\n"
)

print()
print(f"[SAVED] {TRIAL_OUTPUT}")
print(f"[SAVED] {AGGREGATE_OUTPUT}")
print(f"[SAVED] {MANIFEST_OUTPUT}")
print(f"[SAVED] {AUDIT_OUTPUT}")
print(f"[SAVED] {REPORT_OUTPUT}")
print(
    "[PASS] Fresh-seed motor-conditioned "
    "holdout evaluation complete."
)
