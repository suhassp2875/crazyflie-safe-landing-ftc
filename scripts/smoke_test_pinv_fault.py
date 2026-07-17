#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
import time
from pathlib import Path
from typing import Any

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie


URI = "udp://127.0.0.1:19850"

HOVER_HEIGHT_M = 0.60
SETPOINT_PERIOD_S = 0.02
FAULT_DURATION_S = 1.00

MAX_ALLOWED_TILT_DEG = 25.0
MIN_ALLOWED_FAULT_Z_M = 0.15


def set_param(
    scf: SyncCrazyflie,
    name: str,
    value: str,
) -> None:
    scf.cf.param.set_value(name, value)
    time.sleep(0.06)

    actual = scf.cf.param.get_value(name)
    print(f"[PARAM] {name} requested={value} actual={actual}")


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        raise RuntimeError(f"No rows available for {path}")

    fieldnames: list[str] = []

    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_hover_segment(
    commander,
    duration_s: float,
    height_m: float,
    latest_state: dict[str, float],
    fault_active: bool = False,
) -> bool:
    end_time = time.monotonic() + duration_s

    while time.monotonic() < end_time:
        commander.send_hover_setpoint(
            0.0,
            0.0,
            0.0,
            height_m,
        )

        if fault_active and latest_state:
            z = latest_state.get("stateEstimate.z", math.nan)
            roll = latest_state.get("stateEstimate.roll", math.nan)
            pitch = latest_state.get("stateEstimate.pitch", math.nan)

            if all(math.isfinite(v) for v in (z, roll, pitch)):
                tilt = max(abs(roll), abs(pitch))

                if z < MIN_ALLOWED_FAULT_Z_M:
                    print(
                        f"[ABORT] Altitude fell to {z:.3f} m "
                        "during the fault."
                    )
                    return False

                if tilt > MAX_ALLOWED_TILT_DEG:
                    print(
                        f"[ABORT] Tilt reached {tilt:.2f} deg "
                        "during the fault."
                    )
                    return False

        time.sleep(SETPOINT_PERIOD_S)

    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--motor", type=int, default=1)
    parser.add_argument("--eta", type=float, default=0.496)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "results/final/pinv_baseline/smoke/"
            "motor1_eta0p496"
        ),
    )
    args = parser.parse_args()

    if args.motor not in (1, 2, 3, 4):
        raise SystemExit("--motor must be 1, 2, 3, or 4")

    if not 0.0 <= args.eta <= 1.0:
        raise SystemExit("--eta must be between 0 and 1")

    motor_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    state_rows: list[dict[str, Any]] = []

    latest_state: dict[str, float] = {}
    log_errors: list[str] = []

    phase = {"name": "initialization"}
    start_time = time.monotonic()

    cflib.crtp.init_drivers()

    with SyncCrazyflie(
        URI,
        cf=Crazyflie(rw_cache="./cache"),
    ) as scf:
        print("[CONNECTED]")

        required_params = {
            "sitlFault.enable",
            "sitlFault.motor",
            "sitlFault.eta",
            "sitlFtc.enable",
            "sitlPinv.enable",
            "sitlPinv.wThrust",
            "sitlPinv.wRoll",
            "sitlPinv.wPitch",
            "sitlPinv.wYaw",
            "sitlPinv.lambda",
        }

        available_params = {
            f"{group}.{name}"
            for group, variables in scf.cf.param.toc.toc.items()
            for name in variables
        }

        missing_params = required_params - available_params

        if missing_params:
            raise SystemExit(
                f"[FAIL] Missing parameters: {sorted(missing_params)}"
            )

        set_param(scf, "sitlFault.enable", "0")
        set_param(scf, "sitlFtc.enable", "0")

        set_param(scf, "sitlPinv.wThrust", "1.0")
        set_param(scf, "sitlPinv.wRoll", "1.0")
        set_param(scf, "sitlPinv.wPitch", "1.0")
        set_param(scf, "sitlPinv.wYaw", "0.2")
        set_param(scf, "sitlPinv.lambda", "0.000001")
        set_param(scf, "sitlPinv.enable", "1")

        set_param(scf, "sitlFault.motor", str(args.motor))
        set_param(scf, "sitlFault.eta", str(args.eta))

        motor_log = LogConfig(
            name="pinv_fault_motors",
            period_in_ms=20,
        )

        for variable in (
            "pinvAlloc.nom1",
            "pinvAlloc.nom2",
            "pinvAlloc.nom3",
            "pinvAlloc.nom4",
            "pinvAlloc.alloc1",
            "pinvAlloc.alloc2",
            "pinvAlloc.alloc3",
            "pinvAlloc.alloc4",
            "pinvAlloc.active",
        ):
            motor_log.add_variable(variable)

        error_log = LogConfig(
            name="pinv_fault_errors",
            period_in_ms=20,
        )

        for variable in (
            "pinvAlloc.errT",
            "pinvAlloc.errR",
            "pinvAlloc.errP",
            "pinvAlloc.errY",
            "pinvAlloc.objective",
        ):
            error_log.add_variable(variable, "float")

        state_log = LogConfig(
            name="pinv_fault_state",
            period_in_ms=20,
        )

        for variable in (
            "stateEstimate.x",
            "stateEstimate.y",
            "stateEstimate.z",
            "stateEstimate.roll",
            "stateEstimate.pitch",
        ):
            state_log.add_variable(variable, "float")

        def make_callback(target: list[dict[str, Any]]):
            def callback(
                timestamp: int,
                data: dict[str, float],
                logconf: LogConfig,
            ) -> None:
                del logconf

                row: dict[str, Any] = {
                    "host_time_s": time.monotonic() - start_time,
                    "firmware_timestamp_ms": timestamp,
                    "phase": phase["name"],
                }

                row.update(data)
                target.append(row)

                if target is state_rows:
                    latest_state.update(
                        {
                            key: float(value)
                            for key, value in data.items()
                        }
                    )

            return callback

        def on_error(
            logconf: LogConfig,
            message: str,
        ) -> None:
            log_errors.append(f"{logconf.name}: {message}")

        configurations = (
            (motor_log, motor_rows),
            (error_log, error_rows),
            (state_log, state_rows),
        )

        for config, target in configurations:
            config.data_received_cb.add_callback(
                make_callback(target)
            )
            config.error_cb.add_callback(on_error)
            scf.cf.log.add_config(config)
            config.start()

        commander = scf.cf.commander

        try:
            phase["name"] = "settle"
            print("[FLIGHT] Initial settling")

            if not run_hover_segment(
                commander,
                duration_s=1.0,
                height_m=0.15,
                latest_state=latest_state,
            ):
                raise RuntimeError("Unexpected settle failure")

            phase["name"] = "takeoff"
            print("[FLIGHT] Controlled takeoff")

            takeoff_start = time.monotonic()
            takeoff_duration = 2.5

            while True:
                elapsed = time.monotonic() - takeoff_start

                if elapsed >= takeoff_duration:
                    break

                alpha = elapsed / takeoff_duration
                target_z = 0.15 + alpha * (
                    HOVER_HEIGHT_M - 0.15
                )

                commander.send_hover_setpoint(
                    0.0,
                    0.0,
                    0.0,
                    target_z,
                )
                time.sleep(SETPOINT_PERIOD_S)

            phase["name"] = "pre_fault_hover"
            print("[FLIGHT] Pre-fault hover")

            run_hover_segment(
                commander,
                duration_s=1.5,
                height_m=HOVER_HEIGHT_M,
                latest_state=latest_state,
            )

            phase["name"] = "fault_enable_transition"
            print(
                f"[FAULT] Enabling motor={args.motor}, "
                f"eta={args.eta:.6f}"
            )

            set_param(scf, "sitlFault.enable", "1")
            phase["name"] = "fault_active"

            fault_completed = run_hover_segment(
                commander,
                duration_s=FAULT_DURATION_S,
                height_m=HOVER_HEIGHT_M,
                latest_state=latest_state,
                fault_active=True,
            )

            phase["name"] = "fault_disable_transition"
            set_param(scf, "sitlFault.enable", "0")

            if not fault_completed:
                print("[FAULT] Fault phase aborted by safety gate")
            else:
                print("[FAULT] Fault interval completed")

            phase["name"] = "recovery"
            print("[FLIGHT] Healthy recovery hover")

            run_hover_segment(
                commander,
                duration_s=1.5,
                height_m=HOVER_HEIGHT_M,
                latest_state=latest_state,
            )

            phase["name"] = "descent"
            print("[FLIGHT] Controlled descent")

            descent_start = time.monotonic()
            descent_duration = 2.5

            while True:
                elapsed = time.monotonic() - descent_start

                if elapsed >= descent_duration:
                    break

                alpha = elapsed / descent_duration
                target_z = HOVER_HEIGHT_M + alpha * (
                    0.08 - HOVER_HEIGHT_M
                )

                commander.send_hover_setpoint(
                    0.0,
                    0.0,
                    0.0,
                    max(target_z, 0.08),
                )
                time.sleep(SETPOINT_PERIOD_S)

            phase["name"] = "stop"

            for _ in range(20):
                commander.send_hover_setpoint(
                    0.0,
                    0.0,
                    0.0,
                    0.05,
                )
                time.sleep(SETPOINT_PERIOD_S)

        finally:
            set_param(scf, "sitlFault.enable", "0")
            set_param(scf, "sitlPinv.enable", "0")
            commander.send_stop_setpoint()
            time.sleep(0.5)

            for config, _ in configurations:
                config.stop()

    if log_errors:
        print("[LOG ERRORS]")
        for message in log_errors:
            print(message)

        raise SystemExit("[FAIL] Logging errors occurred")

    write_rows(args.output_dir / "motor_samples.csv", motor_rows)
    write_rows(args.output_dir / "error_samples.csv", error_rows)
    write_rows(args.output_dir / "state_samples.csv", state_rows)

    fault_motor_rows = [
        row
        for row in motor_rows
        if row["phase"] == "fault_active"
    ]

    fault_error_rows = [
        row
        for row in error_rows
        if row["phase"] == "fault_active"
    ]

    fault_state_rows = [
        row
        for row in state_rows
        if row["phase"] == "fault_active"
    ]

    if not fault_motor_rows:
        raise SystemExit("[FAIL] No motor samples during fault")

    if not fault_error_rows:
        raise SystemExit("[FAIL] No error samples during fault")

    if not fault_state_rows:
        raise SystemExit("[FAIL] No state samples during fault")

    allocation_key = f"pinvAlloc.alloc{args.motor}"

    maximum_fault_command = max(
        float(row[allocation_key])
        for row in fault_motor_rows
    )

    saturation_samples = sum(
        float(row[allocation_key]) >= 65535.0
        for row in fault_motor_rows
    )

    active_samples = sum(
        float(row["pinvAlloc.active"]) != 0.0
        for row in fault_motor_rows
    )

    minimum_z = min(
        float(row["stateEstimate.z"])
        for row in fault_state_rows
    )

    maximum_tilt = max(
        max(
            abs(float(row["stateEstimate.roll"])),
            abs(float(row["stateEstimate.pitch"])),
        )
        for row in fault_state_rows
    )

    print("\n========== FAULT SMOKE SUMMARY ==========")
    print(f"motor={args.motor}")
    print(f"eta={args.eta:.6f}")
    print(f"fault_motor_max_command={maximum_fault_command:.1f}")
    print(
        f"fault_motor_saturation_samples="
        f"{saturation_samples}/{len(fault_motor_rows)}"
    )
    print(
        f"active_mask_nonzero_samples="
        f"{active_samples}/{len(fault_motor_rows)}"
    )
    print(f"minimum_fault_altitude_m={minimum_z:.4f}")
    print(f"maximum_fault_tilt_deg={maximum_tilt:.4f}")

    for variable in (
        "pinvAlloc.errT",
        "pinvAlloc.errR",
        "pinvAlloc.errP",
        "pinvAlloc.errY",
        "pinvAlloc.objective",
    ):
        maximum = max(
            abs(float(row[variable]))
            for row in fault_error_rows
        )

        print(f"{variable}_max_abs={maximum:.6f}")

    print(f"[SAVED] {args.output_dir}")


if __name__ == "__main__":
    main()
