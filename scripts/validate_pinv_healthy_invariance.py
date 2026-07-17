#!/usr/bin/env python3

from __future__ import annotations

import math
import time
from collections import defaultdict
from pathlib import Path

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie


URI = "udp://127.0.0.1:19850"
CACHE_DIR = Path("./cache")

HOVER_HEIGHT_M = 0.50
HOVER_DURATION_S = 3.0
SETPOINT_PERIOD_S = 0.02


def set_param(scf: SyncCrazyflie, name: str, value: str) -> None:
    scf.cf.param.set_value(name, value)
    time.sleep(0.05)

    actual = scf.cf.param.get_value(name)
    print(f"[PARAM] {name} requested={value} actual={actual}")


def main() -> None:
    samples: dict[str, list[float]] = defaultdict(list)
    log_errors: list[str] = []

    cflib.crtp.init_drivers()

    with SyncCrazyflie(
        URI,
        cf=Crazyflie(rw_cache=str(CACHE_DIR)),
    ) as scf:
        print("[CONNECTED]")

        # Disable every pre-existing fault-compensation path first.
        set_param(scf, "sitlFault.enable", "0")
        set_param(scf, "sitlFtc.enable", "0")

        # Explicit allocator configuration.
        set_param(scf, "sitlPinv.wThrust", "1.0")
        set_param(scf, "sitlPinv.wRoll", "1.0")
        set_param(scf, "sitlPinv.wPitch", "1.0")
        set_param(scf, "sitlPinv.wYaw", "0.2")
        set_param(scf, "sitlPinv.lambda", "0.000001")
        set_param(scf, "sitlPinv.enable", "1")

        motor_log = LogConfig(
            name="pinv_motor_invariance",
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
            name="pinv_error_invariance",
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

        def on_data(
            timestamp: int,
            data: dict[str, float],
            logconf: LogConfig,
        ) -> None:
            del timestamp, logconf

            for key, value in data.items():
                samples[key].append(float(value))

        def on_error(
            logconf: LogConfig,
            message: str,
        ) -> None:
            log_errors.append(f"{logconf.name}: {message}")

        for config in (motor_log, error_log):
            config.data_received_cb.add_callback(on_data)
            config.error_cb.add_callback(on_error)
            scf.cf.log.add_config(config)
            config.start()

        time.sleep(0.5)

        commander = scf.cf.commander

        print("[FLIGHT] Settling at low command")
        settle_end = time.monotonic() + 1.0

        while time.monotonic() < settle_end:
            commander.send_hover_setpoint(
                0.0,
                0.0,
                0.0,
                0.15,
            )
            time.sleep(SETPOINT_PERIOD_S)

        print("[FLIGHT] Rising to hover")
        rise_start = time.monotonic()
        rise_duration = 2.0

        while True:
            elapsed = time.monotonic() - rise_start

            if elapsed >= rise_duration:
                break

            alpha = elapsed / rise_duration
            height = 0.15 + alpha * (
                HOVER_HEIGHT_M - 0.15
            )

            commander.send_hover_setpoint(
                0.0,
                0.0,
                0.0,
                height,
            )
            time.sleep(SETPOINT_PERIOD_S)

        print("[FLIGHT] Healthy allocator hover")
        hover_end = time.monotonic() + HOVER_DURATION_S

        while time.monotonic() < hover_end:
            commander.send_hover_setpoint(
                0.0,
                0.0,
                0.0,
                HOVER_HEIGHT_M,
            )
            time.sleep(SETPOINT_PERIOD_S)

        print("[FLIGHT] Controlled descent")
        descent_start = time.monotonic()
        descent_duration = 2.0

        while True:
            elapsed = time.monotonic() - descent_start

            if elapsed >= descent_duration:
                break

            alpha = elapsed / descent_duration
            height = HOVER_HEIGHT_M + alpha * (
                0.08 - HOVER_HEIGHT_M
            )

            commander.send_hover_setpoint(
                0.0,
                0.0,
                0.0,
                max(height, 0.08),
            )
            time.sleep(SETPOINT_PERIOD_S)

        for _ in range(20):
            commander.send_hover_setpoint(
                0.0,
                0.0,
                0.0,
                0.05,
            )
            time.sleep(SETPOINT_PERIOD_S)

        commander.send_stop_setpoint()
        time.sleep(0.5)

        for config in (motor_log, error_log):
            config.stop()

        # Always disable the allocator after the validation run.
        set_param(scf, "sitlPinv.enable", "0")

    if log_errors:
        print("\n[LOG ERRORS]")
        for message in log_errors:
            print(message)

        raise SystemExit("[FAIL] Logging errors occurred.")

    required = [
        *(f"pinvAlloc.nom{i}" for i in range(1, 5)),
        *(f"pinvAlloc.alloc{i}" for i in range(1, 5)),
        "pinvAlloc.active",
        "pinvAlloc.errT",
        "pinvAlloc.errR",
        "pinvAlloc.errP",
        "pinvAlloc.errY",
        "pinvAlloc.objective",
    ]

    missing = [
        name
        for name in required
        if not samples.get(name)
    ]

    if missing:
        raise SystemExit(
            f"[FAIL] No samples received for: {missing}"
        )

    print("\n========== HEALTHY INVARIANCE SUMMARY ==========")

    maximum_pwm_difference = 0.0

    for motor in range(1, 5):
        nominal = samples[f"pinvAlloc.nom{motor}"]
        allocated = samples[f"pinvAlloc.alloc{motor}"]

        count = min(len(nominal), len(allocated))

        differences = [
            abs(allocated[index] - nominal[index])
            for index in range(count)
        ]

        maximum = max(differences)
        maximum_pwm_difference = max(
            maximum_pwm_difference,
            maximum,
        )

        print(
            f"motor={motor} "
            f"samples={count} "
            f"max_abs_alloc_minus_nom={maximum:.3f}"
        )

    active_values = samples["pinvAlloc.active"]
    nonzero_active_count = sum(
        value != 0.0
        for value in active_values
    )

    print(
        f"active_mask_nonzero_samples="
        f"{nonzero_active_count}/{len(active_values)}"
    )

    error_limits = {
        "pinvAlloc.errT": 4.0,
        "pinvAlloc.errR": 4.0,
        "pinvAlloc.errP": 4.0,
        "pinvAlloc.errY": 4.0,
    }

    errors_pass = True

    for name, limit in error_limits.items():
        values = samples[name]

        if not all(math.isfinite(value) for value in values):
            raise SystemExit(
                f"[FAIL] Non-finite value detected in {name}."
            )

        maximum = max(abs(value) for value in values)
        print(f"{name}_max_abs={maximum:.6f}")

        if maximum > limit:
            errors_pass = False

    objectives = samples["pinvAlloc.objective"]

    if not all(math.isfinite(value) for value in objectives):
        raise SystemExit(
            "[FAIL] Non-finite allocator objective."
        )

    print(
        "pinvAlloc.objective_max="
        f"{max(objectives):.6f}"
    )

    passed = (
        maximum_pwm_difference <= 1.0
        and nonzero_active_count == 0
        and errors_pass
    )

    if not passed:
        raise SystemExit(
            "[FAIL] Healthy allocator invariance check failed."
        )

    print("[PASS] Healthy allocator invariance verified.")


if __name__ == "__main__":
    main()
