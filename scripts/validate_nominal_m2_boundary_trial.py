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

EXPECTED_PINV_CONFIG_PREFIX = "pinv_bounded_wls_"
EXPECTED_CEM_CONFIG = "cem_tuned_boundary"


def fvalue(
    row: dict[str, str],
    key: str,
    default: float | None = None,
) -> float | None:
    value = row.get(key, "").strip()

    if value == "":
        return default

    try:
        return float(value)
    except ValueError:
        return default


def unique_nonempty(
    rows: list[dict[str, str]],
    key: str,
) -> set[str]:
    return {
        row.get(key, "").strip()
        for row in rows
        if row.get(key, "").strip()
    }


def render(value: object) -> object:
    if value is None:
        return ""

    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--controller",
        choices=["pinv", "cem"],
        required=True,
    )
    parser.add_argument(
        "--eta",
        type=float,
        required=True,
    )
    parser.add_argument(
        "--seed",
        type=int,
        required=True,
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        required=True,
    )
    args = parser.parse_args()

    if not args.csv.is_file():
        raise SystemExit(
            f"[FAIL] Missing trial CSV: {args.csv}"
        )

    with args.csv.open(newline="") as file:
        rows = list(csv.DictReader(file))

    if not rows:
        raise SystemExit(
            f"[FAIL] Empty trial CSV: {args.csv}"
        )

    fields = set(rows[0])

    required = {
        "protocol_id",
        "trial_seed",
        "controller",
        "phase",
        "t",
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
        "allocator_config",
        "selected_candidate",
        "r1",
        "r2",
        "r3",
        "r4",
        "fault_x",
        "fault_y",
        "fault_z",
        "fault_vz",
    }

    missing = required - fields

    if missing:
        raise SystemExit(
            "[FAIL] Trial CSV is missing columns: "
            f"{sorted(missing)}"
        )

    protocols = unique_nonempty(
        rows,
        "protocol_id",
    )

    if protocols != {"seeded_ic_v1"}:
        raise SystemExit(
            f"[FAIL] Unexpected protocol IDs: {protocols}"
        )

    seeds = {
        int(float(value))
        for value in unique_nonempty(
            rows,
            "trial_seed",
        )
    }

    if seeds != {args.seed}:
        raise SystemExit(
            f"[FAIL] Trial seed mismatch: {seeds} "
            f"!= {{{args.seed}}}"
        )

    event_indices = [
        index
        for index, row in enumerate(rows)
        if row.get(
            "selected_candidate",
            "",
        ).strip() not in {
            "",
            "none",
        }
    ]

    if not event_indices:
        raise SystemExit(
            "[FAIL] No allocator/fault event was logged."
        )

    event_index = event_indices[0]
    post_rows = rows[event_index:]

    internal_controllers = unique_nonempty(
        post_rows,
        "controller",
    )

    expected_internal = (
        "pinv"
        if args.controller == "pinv"
        else "qplite"
    )

    if internal_controllers != {
        expected_internal
    }:
        raise SystemExit(
            "[FAIL] Controller mismatch: "
            f"{internal_controllers} "
            f"!= {{{expected_internal}}}"
        )

    allocator_configs = unique_nonempty(
        post_rows,
        "allocator_config",
    )

    candidates = unique_nonempty(
        post_rows,
        "selected_candidate",
    )

    residuals = {
        (
            int(float(row["r1"])),
            int(float(row["r2"])),
            int(float(row["r3"])),
            int(float(row["r4"])),
        )
        for row in post_rows
        if row.get(
            "selected_candidate",
            "",
        ).strip() not in {
            "",
            "none",
        }
    }

    if args.controller == "pinv":
        if len(allocator_configs) != 1:
            raise SystemExit(
                "[FAIL] PINV allocator configuration "
                f"is not unique: {allocator_configs}"
            )

        pinv_config = next(
            iter(allocator_configs)
        )

        if not pinv_config.startswith(
            EXPECTED_PINV_CONFIG_PREFIX
        ):
            raise SystemExit(
                "[FAIL] Unexpected PINV config: "
                f"{pinv_config}"
            )

        if candidates != {
            "bounded_fault_aware_wls"
        }:
            raise SystemExit(
                "[FAIL] Unexpected PINV candidate: "
                f"{candidates}"
            )

        if residuals != {
            (0, 0, 0, 0)
        }:
            raise SystemExit(
                "[FAIL] PINV residual must remain zero: "
                f"{residuals}"
            )

    else:
        if allocator_configs != {
            EXPECTED_CEM_CONFIG
        }:
            raise SystemExit(
                "[FAIL] Unexpected CEM allocator config: "
                f"{allocator_configs}"
            )

        if not candidates:
            raise SystemExit(
                "[FAIL] CEM selected no candidate."
            )

        # M2 is faulted. Residual authority may only be
        # applied to M1, M3, and M4.
        if any(
            residual[1] != 0
            for residual in residuals
        ):
            raise SystemExit(
                "[FAIL] CEM applied nonzero residual "
                f"to failed M2: {residuals}"
            )

    event_row = rows[event_index]

    fault_z = fvalue(
        event_row,
        "fault_z",
    )
    fault_vz = fvalue(
        event_row,
        "fault_vz",
    )
    fault_x = fvalue(
        event_row,
        "fault_x",
    )
    fault_y = fvalue(
        event_row,
        "fault_y",
    )

    if (
        fault_z is None
        or fault_vz is None
        or fault_x is None
        or fault_y is None
    ):
        raise SystemExit(
            "[FAIL] Fault-state fields are missing."
        )

    valid_prefault = (
        fault_z >= 0.50
        and abs(fault_vz) <= 0.25
    )

    if not valid_prefault:
        raise SystemExit(
            "[FAIL] Pre-fault validity gate violated: "
            f"fault_z={fault_z:.6f}, "
            f"fault_vz={fault_vz:.6f}"
        )

    contact_index: int | None = None

    for index in range(
        event_index + 1,
        len(rows),
    ):
        z = fvalue(
            rows[index],
            "z",
        )

        if z is not None and z <= GROUND_Z:
            contact_index = index
            break

    contact_found = contact_index is not None

    vertical_speed = None
    horizontal_speed = None
    max_tilt = None
    max_angular_rate = None
    max_drift = None
    contact_t = None
    contact_phase = ""

    if contact_found:
        assert contact_index is not None

        contact_row = rows[contact_index]
        trajectory = rows[
            event_index:contact_index + 1
        ]

        contact_t = fvalue(
            contact_row,
            "t",
        )
        contact_phase = contact_row.get(
            "phase",
            "",
        ).strip()

        contact_vx = fvalue(
            contact_row,
            "vx",
            0.0,
        )
        contact_vy = fvalue(
            contact_row,
            "vy",
            0.0,
        )
        contact_vz = fvalue(
            contact_row,
            "vz",
            0.0,
        )

        assert contact_vx is not None
        assert contact_vy is not None
        assert contact_vz is not None

        vertical_speed = abs(contact_vz)

        horizontal_speed = math.hypot(
            contact_vx,
            contact_vy,
        )

        tilt_values = []
        angular_rates = []
        drift_values = []

        for row in trajectory:
            roll = abs(
                fvalue(
                    row,
                    "roll_deg",
                    0.0,
                )
                or 0.0
            )

            pitch = abs(
                fvalue(
                    row,
                    "pitch_deg",
                    0.0,
                )
                or 0.0
            )

            tilt_values.append(
                max(
                    roll,
                    pitch,
                )
            )

            gx = fvalue(
                row,
                "gyro_x_deg_s",
                0.0,
            ) or 0.0

            gy = fvalue(
                row,
                "gyro_y_deg_s",
                0.0,
            ) or 0.0

            gz = fvalue(
                row,
                "gyro_z_deg_s",
                0.0,
            ) or 0.0

            angular_rates.append(
                math.radians(
                    math.sqrt(
                        gx * gx
                        + gy * gy
                        + gz * gz
                    )
                )
            )

            x = fvalue(
                row,
                "x",
                fault_x,
            )
            y = fvalue(
                row,
                "y",
                fault_y,
            )

            assert x is not None
            assert y is not None

            drift_values.append(
                math.hypot(
                    x - fault_x,
                    y - fault_y,
                )
            )

        max_tilt = max(
            tilt_values,
            default=0.0,
        )

        max_angular_rate = max(
            angular_rates,
            default=0.0,
        )

        max_drift = max(
            drift_values,
            default=0.0,
        )

    vertical_ok = (
        contact_found
        and vertical_speed is not None
        and vertical_speed <= LIMIT_VERTICAL_SPEED
    )

    horizontal_ok = (
        contact_found
        and horizontal_speed is not None
        and horizontal_speed
        <= LIMIT_HORIZONTAL_SPEED
    )

    tilt_ok = (
        contact_found
        and max_tilt is not None
        and max_tilt <= LIMIT_TILT_DEG
    )

    angular_ok = (
        contact_found
        and max_angular_rate is not None
        and max_angular_rate
        <= LIMIT_ANGULAR_RATE
    )

    drift_ok = (
        contact_found
        and max_drift is not None
        and max_drift <= LIMIT_DRIFT
    )

    safe_touchdown = all(
        [
            vertical_ok,
            horizontal_ok,
            tilt_ok,
            angular_ok,
            drift_ok,
        ]
    )

    candidate = sorted(candidates)[0]
    residual = sorted(residuals)[0]
    allocator_config = sorted(
        allocator_configs
    )[0]

    summary = {
        "protocol_id":
            "nominal_m2_boundary_localization_v1",
        "ic_protocol": "seeded_ic_v1",
        "controller": args.controller,
        "internal_controller":
            expected_internal,
        "motor": 2,
        "eta": f"{args.eta:.6f}",
        "trial_seed": args.seed,
        "source_csv": str(args.csv),
        "row_count": len(rows),
        "allocator_config": allocator_config,
        "selected_candidate": candidate,
        "r1": residual[0],
        "r2": residual[1],
        "r3": residual[2],
        "r4": residual[3],
        "fault_z": fault_z,
        "fault_vz": fault_vz,
        "valid_prefault": valid_prefault,
        "contact_found": contact_found,
        "contact_t": render(contact_t),
        "contact_phase": contact_phase,
        "vertical_speed_mps":
            render(vertical_speed),
        "horizontal_speed_mps":
            render(horizontal_speed),
        "max_tilt_deg": render(max_tilt),
        "max_angular_rate_radps":
            render(max_angular_rate),
        "max_horizontal_drift_m":
            render(max_drift),
        "vertical_speed_ok": vertical_ok,
        "horizontal_speed_ok": horizontal_ok,
        "tilt_ok": tilt_ok,
        "angular_rate_ok": angular_ok,
        "drift_ok": drift_ok,
        "safe_touchdown": safe_touchdown,
    }

    args.summary_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with args.summary_output.open(
        "w",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(summary),
        )
        writer.writeheader()
        writer.writerow(summary)

    print(
        "[PASS] Trial structure and controller "
        "configuration verified."
    )
    print(
        f"controller={args.controller}"
    )
    print(f"eta={args.eta:.6f}")
    print(f"seed={args.seed}")
    print(
        f"candidate={candidate}"
    )
    print(f"residual={residual}")
    print(
        f"contact_found={contact_found}"
    )
    print(
        f"vertical_speed_mps="
        f"{vertical_speed}"
    )
    print(
        f"safe_touchdown={safe_touchdown}"
    )
    print(
        f"[SAVED] {args.summary_output}"
    )


if __name__ == "__main__":
    main()
