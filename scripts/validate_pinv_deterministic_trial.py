#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


GROUND_Z = 0.03

LIMIT_VERTICAL_SPEED = 0.35
LIMIT_HORIZONTAL_SPEED = 0.25
LIMIT_TILT_DEG = 12.0
LIMIT_ANGULAR_RATE = 1.5
LIMIT_DRIFT = 0.75


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--motor", type=int, required=True)
    parser.add_argument("--eta", type=float, required=True)
    parser.add_argument(
        "--summary-output",
        type=Path,
        required=True,
    )
    parser.add_argument("--min-rows", type=int, default=3500)
    parser.add_argument("--max-rows", type=int, default=5000)

    args = parser.parse_args()

    if args.motor not in (1, 2, 3, 4):
        raise SystemExit("--motor must be 1, 2, 3, or 4")

    rows = read_rows(args.csv)

    if not rows:
        raise SystemExit("[FAIL] CSV contains no rows.")

    required = {
        "controller",
        "allocator_config",
        "protocol_id",
        "trial_seed",
        "fault_time_cmd",
        "t",
        "phase",
        "x",
        "y",
        "z",
        "vx",
        "vy",
        "vz",
        "roll_deg",
        "pitch_deg",
        "gyro_x_deg_s",
        "gyro_y_deg_s",
        "gyro_z_deg_s",
        f"motor_m{args.motor}",
        f"pinv_alloc_m{args.motor}",
        "pinv_active_mask",
        "pinv_err_thrust",
        "pinv_err_yaw",
        "pinv_objective",
    }

    missing = required - set(rows[0])

    if missing:
        raise SystemExit(
            f"[FAIL] Missing fields: {sorted(missing)}"
        )

    if not args.min_rows <= len(rows) <= args.max_rows:
        raise SystemExit(
            f"[FAIL] Unexpected row count: {len(rows)}"
        )

    if rows[-1]["controller"] != "pinv":
        raise SystemExit(
            "[FAIL] Trial was not logged as controller=pinv."
        )

    fault_event_row = next(
        (
            row
            for row in rows
            if row["phase"] == "fault_event"
        ),
        None,
    )

    if fault_event_row is not None:
        actual_fault_t = float(fault_event_row["t"])
    else:
        actual_fault_t = float(rows[0]["fault_time_cmd"])

    post_fault = [
        row
        for row in rows
        if float(row["t"]) >= actual_fault_t
    ]

    active_rows = sum(
        int(float(row["pinv_active_mask"])) != 0
        for row in post_fault
    )

    if active_rows == 0:
        raise SystemExit(
            "[FAIL] PINV allocator never became active."
        )

    contact = next(
        (
            row
            for row in post_fault
            if float(row["z"]) <= GROUND_Z
        ),
        None,
    )

    summary: dict[str, object] = {
        "motor": args.motor,
        "eta": args.eta,
        "protocol_id": rows[-1]["protocol_id"],
        "trial_seed": int(float(rows[-1]["trial_seed"])),
        "controller": rows[-1]["controller"],
        "allocator_config": rows[-1]["allocator_config"],
        "rows": len(rows),
        "actual_fault_t": actual_fault_t,
        "post_fault_rows": len(post_fault),
        "active_post_fault_rows": active_rows,
        "contact_found": contact is not None,
    }

    print("========== DETERMINISTIC PINV VALIDATION ==========")
    print(f"motor={args.motor}")
    print(f"eta={args.eta:.6f}")
    print(f"rows={len(rows)}")
    print(f"actual_fault_t={actual_fault_t:.6f}")
    print(f"post_fault_rows={len(post_fault)}")
    print(f"active_post_fault_rows={active_rows}")

    if contact is None:
        summary.update(
            {
                "safe_touchdown": False,
                "vertical_speed_mps": "",
                "vertical_speed_margin_mps": "",
                "horizontal_speed_mps": "",
                "max_tilt_deg": "",
                "angular_rate_radps": "",
                "horizontal_drift_m": "",
                "fault_to_contact_s": "",
                "fault_motor_allocation": "",
                "expected_applied_pwm": "",
                "logged_applied_pwm": "",
            }
        )

        print("contact_found=False")
        print("safe_touchdown=False")

    else:
        vx = float(contact["vx"])
        vy = float(contact["vy"])
        vz = float(contact["vz"])

        roll = float(contact["roll_deg"])
        pitch = float(contact["pitch_deg"])

        gx = float(contact["gyro_x_deg_s"])
        gy = float(contact["gyro_y_deg_s"])
        gz = float(contact["gyro_z_deg_s"])

        x = float(contact["x"])
        y = float(contact["y"])

        vertical_speed = abs(vz)
        horizontal_speed = math.hypot(vx, vy)
        max_tilt = max(abs(roll), abs(pitch))
        angular_rate = math.radians(
            math.sqrt(gx * gx + gy * gy + gz * gz)
        )
        drift = math.hypot(x, y)

        checks = {
            "vertical_speed_ok":
                vertical_speed <= LIMIT_VERTICAL_SPEED,
            "horizontal_speed_ok":
                horizontal_speed <= LIMIT_HORIZONTAL_SPEED,
            "roll_pitch_ok":
                max_tilt <= LIMIT_TILT_DEG,
            "angular_rate_ok":
                angular_rate <= LIMIT_ANGULAR_RATE,
            "drift_ok":
                drift <= LIMIT_DRIFT,
        }

        safe = all(checks.values())

        allocation = int(
            float(contact[f"pinv_alloc_m{args.motor}"])
        )
        logged_applied = int(
            float(contact[f"motor_m{args.motor}"])
        )
        expected_applied = math.floor(
            args.eta * allocation
        )

        if abs(logged_applied - expected_applied) > 1:
            raise SystemExit(
                "[FAIL] Fault-effectiveness scaling mismatch: "
                f"allocation={allocation}, "
                f"expected={expected_applied}, "
                f"logged={logged_applied}"
            )

        contact_t = float(contact["t"])

        summary.update(
            {
                "safe_touchdown": safe,
                "contact_t": contact_t,
                "fault_to_contact_s":
                    contact_t - actual_fault_t,
                "contact_phase": contact["phase"],
                "vertical_speed_mps": vertical_speed,
                "vertical_speed_margin_mps":
                    LIMIT_VERTICAL_SPEED - vertical_speed,
                "horizontal_speed_mps": horizontal_speed,
                "max_tilt_deg": max_tilt,
                "angular_rate_radps": angular_rate,
                "horizontal_drift_m": drift,
                "vertical_speed_ok":
                    checks["vertical_speed_ok"],
                "horizontal_speed_ok":
                    checks["horizontal_speed_ok"],
                "roll_pitch_ok":
                    checks["roll_pitch_ok"],
                "angular_rate_ok":
                    checks["angular_rate_ok"],
                "drift_ok":
                    checks["drift_ok"],
                "fault_motor_allocation": allocation,
                "expected_applied_pwm": expected_applied,
                "logged_applied_pwm": logged_applied,
                "pinv_active_mask":
                    int(float(contact["pinv_active_mask"])),
                "pinv_err_thrust":
                    float(contact["pinv_err_thrust"]),
                "pinv_err_yaw":
                    float(contact["pinv_err_yaw"]),
                "pinv_objective":
                    float(contact["pinv_objective"]),
            }
        )

        print("contact_found=True")
        print(f"contact_t={contact_t:.6f}")
        print(
            f"fault_to_contact_s="
            f"{contact_t - actual_fault_t:.6f}"
        )
        print(f"contact_phase={contact['phase']}")
        print(f"vertical_speed_mps={vertical_speed:.9f}")
        print(
            f"vertical_speed_margin_mps="
            f"{LIMIT_VERTICAL_SPEED - vertical_speed:.9f}"
        )
        print(
            f"horizontal_speed_mps="
            f"{horizontal_speed:.9f}"
        )
        print(f"max_tilt_deg={max_tilt:.9f}")
        print(
            f"angular_rate_radps={angular_rate:.9f}"
        )
        print(f"horizontal_drift_m={drift:.9f}")
        print(f"checks={checks}")
        print(f"safe_touchdown={safe}")
        print(
            f"fault_motor_allocation={allocation} "
            f"expected_applied={expected_applied} "
            f"logged_applied={logged_applied}"
        )

    args.summary_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with args.summary_output.open("w", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(summary.keys()),
        )
        writer.writeheader()
        writer.writerow(summary)

    print(f"[SAVED] {args.summary_output}")
    print("[PASS] Deterministic PINV telemetry verified.")


if __name__ == "__main__":
    main()
