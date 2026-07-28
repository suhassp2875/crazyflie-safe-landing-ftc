#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


VERTICAL_SPEED_LIMIT = 0.35
HORIZONTAL_SPEED_LIMIT = 0.25
TILT_LIMIT_DEG = 12.0
ANGULAR_RATE_LIMIT_RADPS = 1.5
DRIFT_LIMIT_M = 0.75

MIN_VALID_FAULT_Z = 0.50
MAX_VALID_FAULT_ABS_VZ = 0.25


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
        ("t", "time", "time_s", "elapsed_s"),
    )


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


def evaluate_trial(
    specification: dict[str, str],
) -> dict[str, object]:
    path = Path(specification["expected_csv"])
    motor = int(specification["motor"])
    seed = int(specification["trial_seed"])

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
            f"{path}: unexpected row count={len(rows)}"
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
    }

    missing = required - fields

    if missing:
        raise ValueError(
            f"{path}: missing columns={sorted(missing)}"
        )

    actual_seed = int(float(rows[0]["trial_seed"]))

    if actual_seed != seed:
        raise ValueError(
            f"{path}: expected seed={seed}, "
            f"actual seed={actual_seed}"
        )

    controllers = {
        row["controller"].strip().lower()
        for row in rows
        if row["controller"].strip()
    }

    allocators = {
        row["allocator_config"].strip().lower()
        for row in rows
        if row["allocator_config"].strip()
    }

    expected_policy = specification["selected_policy"]

    if motor == 2:
        policy_ok = (
            expected_policy == "pinv_bounded_wls"
            and controllers == {"pinv"}
            and any(
                "pinv_bounded_wls" in value
                for value in allocators
            )
        )
    else:
        policy_ok = (
            expected_policy == "cem_tuned_qplite"
            and controllers == {"qplite"}
            and any(
                "cem" in value
                for value in allocators
            )
        )

    if not policy_ok:
        raise ValueError(
            f"{path}: policy mismatch; "
            f"scheduled={expected_policy}, "
            f"controllers={sorted(controllers)}, "
            f"allocators={sorted(allocators)}"
        )

    fault_index = next(
        (
            index
            for index, row in enumerate(rows)
            if row["phase"].strip() == "fault_event"
        ),
        None,
    )

    if fault_index is None:
        raise ValueError(
            f"{path}: fault_event row missing"
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

    contact_row = next(
        (
            row
            for row in rows[fault_index:]
            if float(row["z"]) <= 0.03
        ),
        None,
    )

    if contact_row is None:
        raise ValueError(
            f"{path}: no first-contact row"
        )

    vertical_speed = abs(float(contact_row["vz"]))

    horizontal_speed = math.hypot(
        float(contact_row["vx"]),
        float(contact_row["vy"]),
    )

    max_tilt = max(
        abs(float(contact_row["roll_deg"])),
        abs(float(contact_row["pitch_deg"])),
    )

    angular_rate = math.radians(
        math.sqrt(
            float(contact_row["gyro_x_deg_s"]) ** 2
            + float(contact_row["gyro_y_deg_s"]) ** 2
            + float(contact_row["gyro_z_deg_s"]) ** 2
        )
    )

    horizontal_drift = math.hypot(
        float(contact_row["x"]),
        float(contact_row["y"]),
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
        "sequence_index":
            int(specification["sequence_index"]),
        "motor": motor,
        "repetition_within_motor":
            int(specification["repetition_within_motor"]),
        "trial_seed": seed,
        "selected_policy": expected_policy,
        "runtime_controller":
            next(iter(controllers)),
        "source_csv": str(path),
        "rows": len(rows),
        "fault_z": fault_z,
        "fault_vz": fault_vz,
        "contact_t": row_time(contact_row),
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
    required=True,
)
arguments = parser.parse_args()

root = Path(
    "results/final/pinv_baseline/"
    "seeded_eta0p496/randomized_supervisor"
) / arguments.run_id

schedule_path = root / "schedule.csv"

if not schedule_path.is_file():
    raise SystemExit(
        f"[FAIL] Missing schedule: {schedule_path}"
    )

with schedule_path.open(newline="") as file:
    schedule = list(csv.DictReader(file))

expected_trials = len(schedule)

if expected_trials <= 0:
    raise SystemExit("[FAIL] Empty schedule.")

trial_rows = []
errors = []

for index, specification in enumerate(
    schedule,
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
            f"[PROGRESS] audited={index}/{expected_trials}"
        )

if errors:
    for error in errors:
        print(f"[ERROR] {error}")

    raise SystemExit(
        f"[FAIL] Supervisor audit found "
        f"{len(errors)} error(s)."
    )

trial_rows.sort(
    key=lambda row: int(row["sequence_index"])
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
    "========== RANDOMIZED MOTOR SUPERVISOR =========="
)

for motor in (1, 2, 3, 4):
    group = by_motor[motor]

    if not group:
        raise SystemExit(
            f"[FAIL] No M{motor} trials."
        )

    safe_count = sum(
        bool(row["safe_touchdown"])
        for row in group
    )

    speeds = [
        float(row["vertical_speed_mps"])
        for row in group
    ]

    lower, upper = wilson_interval(
        safe_count,
        len(group),
    )

    failure_counts = {
        "vertical_speed_failure_count": sum(
            not bool(row["vertical_speed_ok"])
            for row in group
        ),
        "horizontal_speed_failure_count": sum(
            not bool(row["horizontal_speed_ok"])
            for row in group
        ),
        "tilt_failure_count": sum(
            not bool(row["roll_pitch_ok"])
            for row in group
        ),
        "angular_rate_failure_count": sum(
            not bool(row["angular_rate_ok"])
            for row in group
        ),
        "drift_failure_count": sum(
            not bool(row["drift_ok"])
            for row in group
        ),
    }

    aggregate = {
        "motor": motor,
        "selected_policy":
            group[0]["selected_policy"],
        "n": len(group),
        "safe_count": safe_count,
        "unsafe_count": len(group) - safe_count,
        "safe_rate": safe_count / len(group),
        "safe_rate_wilson95_lower": lower,
        "safe_rate_wilson95_upper": upper,
        "mean_vertical_speed_mps":
            statistics.mean(speeds),
        "median_vertical_speed_mps":
            statistics.median(speeds),
        "std_vertical_speed_mps":
            statistics.stdev(speeds)
            if len(speeds) > 1
            else 0.0,
        "min_vertical_speed_mps": min(speeds),
        "max_vertical_speed_mps": max(speeds),
        **failure_counts,
    }

    aggregate_rows.append(aggregate)

    print(
        f"M{motor}: "
        f"policy={aggregate['selected_policy']} "
        f"safe={safe_count}/{len(group)} "
        f"rate={aggregate['safe_rate']:.3f} "
        f"Wilson95=[{lower:.3f}, {upper:.3f}] "
        f"mean_vz={statistics.mean(speeds):.6f} "
        f"range=[{min(speeds):.6f}, "
        f"{max(speeds):.6f}] "
        f"vertical_failures="
        f"{failure_counts['vertical_speed_failure_count']}"
    )

motor_counts = Counter(
    int(row["motor"])
    for row in trial_rows
)

overall_safe = sum(
    bool(row["safe_touchdown"])
    for row in trial_rows
)

overall_lower, overall_upper = wilson_interval(
    overall_safe,
    len(trial_rows),
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
print(f"validated_trials={len(trial_rows)}")
print(f"motor_counts={dict(sorted(motor_counts.items()))}")
print(f"safe={overall_safe}/{len(trial_rows)}")
print(f"safe_rate={overall_safe / len(trial_rows):.6f}")
print(
    f"Wilson95=[{overall_lower:.6f}, "
    f"{overall_upper:.6f}]"
)
print(f"non_vertical_failures={non_vertical_failures}")

trial_output = root / "supervisor_trial_summaries.csv"
aggregate_output = root / "supervisor_aggregate_by_motor.csv"
audit_output = root / "supervisor_audit.txt"
report_output = root / "supervisor_report.md"

write_csv(trial_output, trial_rows)
write_csv(aggregate_output, aggregate_rows)

audit_output.write_text(
    "\n".join(
        [
            f"run_id={arguments.run_id}",
            f"scheduled_trials={expected_trials}",
            f"validated_trials={len(trial_rows)}",
            f"overall_safe={overall_safe}",
            f"overall_unsafe={len(trial_rows) - overall_safe}",
            "eta=0.496",
            "policy_id=oracle_motor_conditioned_v1",
            (
                "policy="
                "M1:CEM-tuned,M2:PINV,"
                "M3:CEM-tuned,M4:CEM-tuned"
            ),
            (
                "motor_counts="
                + ",".join(
                    f"M{motor}:{motor_counts[motor]}"
                    for motor in sorted(motor_counts)
                )
            ),
        ]
    )
    + "\n"
)

report_lines = [
    "# Randomized Oracle Motor-Conditioned Supervisor",
    "",
    f"- Run ID: `{arguments.run_id}`",
    f"- Trials: {len(trial_rows)}",
    "- Fault effectiveness: `eta = 0.496`",
    "- Motor order randomized before execution",
    "- Failed-motor identity supplied by the experiment",
    "",
    "| Motor | Policy | Safe | Rate | Wilson 95% CI | Mean vertical speed |",
    "|---:|:---|---:|---:|---:|---:|",
]

for row in aggregate_rows:
    report_lines.append(
        f"| M{row['motor']} "
        f"| {row['selected_policy']} "
        f"| {row['safe_count']}/{row['n']} "
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
            f"Overall: **{overall_safe}/{len(trial_rows)} "
            f"({100 * overall_safe / len(trial_rows):.1f}%)**."
        ),
        "",
        (
            "This validates integrated allocator selection "
            "using known failed-motor identity. It does not "
            "validate online fault diagnosis."
        ),
    ]
)

report_output.write_text(
    "\n".join(report_lines) + "\n"
)

print()
print(f"[SAVED] {trial_output}")
print(f"[SAVED] {aggregate_output}")
print(f"[SAVED] {audit_output}")
print(f"[SAVED] {report_output}")
print("[PASS] Randomized supervisor evaluation complete.")
