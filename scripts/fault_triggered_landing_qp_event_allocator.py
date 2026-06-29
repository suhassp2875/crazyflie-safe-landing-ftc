#!/usr/bin/env python3

import argparse
import csv
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.syncLogger import SyncLogger

from src.controllers.residual_allocator_qp import AllocatorState, allocate_residual_qp


GROUND_Z = 0.03

LIMIT_VERTICAL_SPEED = 0.35
LIMIT_HORIZONTAL_SPEED = 0.25
LIMIT_TILT_DEG = 12.0
LIMIT_ANGULAR_RATE = 1.5
LIMIT_DRIFT = 0.75


def fget(data, key, default=0.0):
    try:
        return float(data.get(key, default))
    except Exception:
        return float(default)


def set_param(cf, name, value, delay=0.01):
    cf.param.set_value(name, str(value))
    time.sleep(delay)


def reset_sitl_fault_and_ftc(cf):
    set_param(cf, "sitlFault.enable", 0)
    set_param(cf, "sitlFault.motor", 1)
    set_param(cf, "sitlFault.eta", 1.0)

    set_param(cf, "sitlFtc.enable", 0)
    set_param(cf, "sitlFtc.healthyBoost", 0)
    set_param(cf, "sitlFtc.r1", 0)
    set_param(cf, "sitlFtc.r2", 0)
    set_param(cf, "sitlFtc.r3", 0)
    set_param(cf, "sitlFtc.r4", 0)


def inject_fault(cf, motor, eta):
    set_param(cf, "sitlFault.motor", int(motor))
    set_param(cf, "sitlFault.eta", float(eta))
    set_param(cf, "sitlFault.enable", 1)


def apply_residual(cf, r):
    r1, r2, r3, r4 = [int(x) for x in r]

    set_param(cf, "sitlFtc.healthyBoost", 0)
    set_param(cf, "sitlFtc.r1", r1)
    set_param(cf, "sitlFtc.r2", r2)
    set_param(cf, "sitlFtc.r3", r3)
    set_param(cf, "sitlFtc.r4", r4)
    set_param(cf, "sitlFtc.enable", 1)


def clear_residual(cf):
    set_param(cf, "sitlFtc.r1", 0)
    set_param(cf, "sitlFtc.r2", 0)
    set_param(cf, "sitlFtc.r3", 0)
    set_param(cf, "sitlFtc.r4", 0)
    set_param(cf, "sitlFtc.healthyBoost", 0)
    set_param(cf, "sitlFtc.enable", 0)


def make_log_configs(period_ms):
    state_lg = LogConfig(name="qp_state", period_in_ms=period_ms)
    for name, typ in [
        ("stateEstimate.x", "float"),
        ("stateEstimate.y", "float"),
        ("stateEstimate.z", "float"),
        ("stateEstimate.vx", "float"),
        ("stateEstimate.vy", "float"),
        ("stateEstimate.vz", "float"),
    ]:
        state_lg.add_variable(name, typ)

    attitude_lg = LogConfig(name="qp_attitude", period_in_ms=period_ms)
    for name, typ in [
        ("stabilizer.roll", "float"),
        ("stabilizer.pitch", "float"),
        ("stabilizer.yaw", "float"),
        ("gyro.x", "float"),
        ("gyro.y", "float"),
        ("gyro.z", "float"),
    ]:
        attitude_lg.add_variable(name, typ)

    motor_lg = LogConfig(name="qp_motors", period_in_ms=period_ms)
    for name, typ in [
        ("motor.m1", "uint16_t"),
        ("motor.m2", "uint16_t"),
        ("motor.m3", "uint16_t"),
        ("motor.m4", "uint16_t"),
    ]:
        motor_lg.add_variable(name, typ)

    return [state_lg, attitude_lg, motor_lg]


def make_allocator_state(data):
    gx = fget(data, "gyro.x")
    gy = fget(data, "gyro.y")
    gz = fget(data, "gyro.z")
    angular_rate_radps = math.radians(math.sqrt(gx * gx + gy * gy + gz * gz))

    max_motor_pwm = max(
        fget(data, "motor.m1"),
        fget(data, "motor.m2"),
        fget(data, "motor.m3"),
        fget(data, "motor.m4"),
    )

    return AllocatorState(
        z=fget(data, "stateEstimate.z"),
        vz=fget(data, "stateEstimate.vz"),
        x=fget(data, "stateEstimate.x"),
        y=fget(data, "stateEstimate.y"),
        vx=fget(data, "stateEstimate.vx"),
        vy=fget(data, "stateEstimate.vy"),
        roll_deg=fget(data, "stabilizer.roll"),
        pitch_deg=fget(data, "stabilizer.pitch"),
        angular_rate_radps=angular_rate_radps,
        max_motor_pwm=max_motor_pwm,
    )


def evaluate_first_contact(rows, fault_t):
    post = [r for r in rows if r["t"] >= fault_t]
    contact = [r for r in post if r["z"] <= GROUND_Z]

    if contact:
        row = contact[0]
        found = True
    else:
        row = min(post, key=lambda r: r["z"])
        found = False

    vx = row["vx"]
    vy = row["vy"]
    vz = row["vz"]
    x = row["x"]
    y = row["y"]
    roll = row["roll_deg"]
    pitch = row["pitch_deg"]
    gx = row["gyro_x_deg_s"]
    gy = row["gyro_y_deg_s"]
    gz = row["gyro_z_deg_s"]

    vertical_speed = abs(vz)
    horizontal_speed = math.sqrt(vx * vx + vy * vy)
    max_tilt = max(abs(roll), abs(pitch))
    angular_rate = math.radians(math.sqrt(gx * gx + gy * gy + gz * gz))
    drift = math.sqrt(x * x + y * y)

    checks = {
        "vertical_speed_ok": vertical_speed <= LIMIT_VERTICAL_SPEED,
        "horizontal_speed_ok": horizontal_speed <= LIMIT_HORIZONTAL_SPEED,
        "roll_pitch_ok": max_tilt <= LIMIT_TILT_DEG,
        "angular_rate_ok": angular_rate <= LIMIT_ANGULAR_RATE,
        "drift_ok": drift <= LIMIT_DRIFT,
    }

    safe = all(checks.values())

    return row, found, {
        "safe_touchdown": safe,
        "vertical_speed_mps": vertical_speed,
        "horizontal_speed_mps": horizontal_speed,
        "max_tilt_deg": max_tilt,
        "angular_rate_radps": angular_rate,
        "horizontal_drift_m": drift,
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default="udp://127.0.0.1:19850")
    parser.add_argument("--motor", type=int, required=True)
    parser.add_argument("--eta", type=float, required=True)
    parser.add_argument("--tag", default="stateaware_qp")
    parser.add_argument("--log-period-ms", type=int, default=20)
    parser.add_argument("--max-brake-duration", type=float, default=8.0)
    args = parser.parse_args()

    if args.motor not in [1, 2, 3, 4]:
        raise SystemExit("--motor must be 1, 2, 3, or 4")

    eta_tag = f"{args.eta:.3f}".replace(".", "p")
    out_path = Path("logs") / f"qp_event_allocator_m{args.motor}_eta{eta_tag}_{args.tag}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("[INFO] Starting state-aware QP-lite event allocator")
    print(f"[INFO] uri={args.uri}")
    print(f"[INFO] motor={args.motor}, eta={args.eta}")
    print(f"[INFO] log={out_path}")

    cflib.crtp.init_drivers()

    rows = []
    fault_t = None
    allocated = False

    selected_candidate = "none"
    selected_r = [0, 0, 0, 0]
    selected_score = 0.0
    selected_pred_vz = 0.0
    selected_pred_drift = 0.0
    selected_pred_tilt = 0.0

    fault_state_snapshot = {}

    required_keys = [
        "stateEstimate.x", "stateEstimate.y", "stateEstimate.z",
        "stateEstimate.vx", "stateEstimate.vy", "stateEstimate.vz",
        "stabilizer.roll", "stabilizer.pitch", "stabilizer.yaw",
        "gyro.x", "gyro.y", "gyro.z",
        "motor.m1", "motor.m2", "motor.m3", "motor.m4",
    ]

    with SyncCrazyflie(args.uri, cf=Crazyflie()) as scf:
        cf = scf.cf

        reset_sitl_fault_and_ftc(cf)

        try:
            cf.platform.send_arming_request(True)
            time.sleep(1.0)
        except Exception as e:
            print(f"[WARN] arming request failed/nonfatal: {e}")

        log_configs = make_log_configs(args.log_period_ms)
        latest = {}
        t0 = time.time()

        with SyncLogger(scf, log_configs) as logger:
            for _, data, _ in logger:
                latest.update(data)

                if not all(k in latest for k in required_keys):
                    continue

                data = latest
                t = time.time() - t0

                phase = "arming"
                z_cmd = 0.05

                if t < 1.0:
                    phase = "arming"
                    z_cmd = 0.05

                elif t < 4.0:
                    phase = "takeoff_stage_1"
                    z_cmd = 0.30

                elif t < 8.0:
                    phase = "takeoff_stage_2"
                    z_cmd = 0.70

                elif t < 10.0:
                    phase = "nominal_hover"
                    z_cmd = 0.70

                elif t < 10.0 + args.max_brake_duration:
                    z_cmd = 0.95

                    if not allocated:
                        phase = "fault_event"
                        fault_t = t

                        allocator_state = make_allocator_state(data)
                        allocation = allocate_residual_qp(args.motor, args.eta, allocator_state)

                        selected_candidate = allocation.candidate_name
                        selected_r = allocation.residual
                        selected_score = float(allocation.score)
                        selected_pred_vz = float(allocation.predicted_vz)
                        selected_pred_drift = float(allocation.predicted_drift)
                        selected_pred_tilt = float(allocation.predicted_tilt)

                        fault_state_snapshot = {
                            "fault_x": allocator_state.x,
                            "fault_y": allocator_state.y,
                            "fault_z": allocator_state.z,
                            "fault_vx": allocator_state.vx,
                            "fault_vy": allocator_state.vy,
                            "fault_vz": allocator_state.vz,
                            "fault_roll_deg": allocator_state.roll_deg,
                            "fault_pitch_deg": allocator_state.pitch_deg,
                            "fault_max_motor_pwm": allocator_state.max_motor_pwm,
                        }

                        print("[QP EVENT ALLOCATION]")
                        print(f"fault_t: {fault_t:.3f}")
                        print(f"fault_state: {fault_state_snapshot}")
                        print(f"candidate: {selected_candidate}")
                        print(f"residual: {selected_r}")
                        print(f"score: {selected_score:.6f}")
                        print(f"predicted_vz: {selected_pred_vz:.6f}")
                        print(f"predicted_drift: {selected_pred_drift:.6f}")
                        print(f"predicted_tilt: {selected_pred_tilt:.6f}")

                        inject_fault(cf, args.motor, args.eta)
                        apply_residual(cf, selected_r)
                        allocated = True

                    else:
                        phase = "max_brake_hold"

                elif t < 10.0 + args.max_brake_duration + 2.0:
                    phase = "touchdown_hold"
                    z_cmd = 0.02

                else:
                    break

                cf.commander.send_hover_setpoint(0.0, 0.0, 0.0, z_cmd)

                row = {
                    "t": t,
                    "phase": phase,
                    "x": fget(data, "stateEstimate.x"),
                    "y": fget(data, "stateEstimate.y"),
                    "z": fget(data, "stateEstimate.z"),
                    "vx": fget(data, "stateEstimate.vx"),
                    "vy": fget(data, "stateEstimate.vy"),
                    "vz": fget(data, "stateEstimate.vz"),
                    "roll_deg": fget(data, "stabilizer.roll"),
                    "pitch_deg": fget(data, "stabilizer.pitch"),
                    "yaw_deg": fget(data, "stabilizer.yaw"),
                    "gyro_x_deg_s": fget(data, "gyro.x"),
                    "gyro_y_deg_s": fget(data, "gyro.y"),
                    "gyro_z_deg_s": fget(data, "gyro.z"),
                    "motor_m1": int(fget(data, "motor.m1")),
                    "motor_m2": int(fget(data, "motor.m2")),
                    "motor_m3": int(fget(data, "motor.m3")),
                    "motor_m4": int(fget(data, "motor.m4")),
                    "z_cmd": z_cmd,
                    "selected_candidate": selected_candidate,
                    "r1": int(selected_r[0]),
                    "r2": int(selected_r[1]),
                    "r3": int(selected_r[2]),
                    "r4": int(selected_r[3]),
                    "qp_score": selected_score,
                    "qp_predicted_vz": selected_pred_vz,
                    "qp_predicted_drift": selected_pred_drift,
                    "qp_predicted_tilt": selected_pred_tilt,
                    **fault_state_snapshot,
                }
                rows.append(row)

        try:
            cf.commander.send_stop_setpoint()
            cf.commander.send_notify_setpoint_stop()
        except Exception:
            pass

        clear_residual(cf)
        set_param(cf, "sitlFault.enable", 0)

    if not rows:
        raise SystemExit("[ERROR] No rows logged.")

    preferred_fieldnames = [
        "t", "phase",
        "x", "y", "z", "vx", "vy", "vz",
        "roll_deg", "pitch_deg", "yaw_deg",
        "gyro_x_deg_s", "gyro_y_deg_s", "gyro_z_deg_s",
        "motor_m1", "motor_m2", "motor_m3", "motor_m4",
        "z_cmd",
        "selected_candidate", "r1", "r2", "r3", "r4",
        "qp_score", "qp_predicted_vz", "qp_predicted_drift", "qp_predicted_tilt",
        "fault_x", "fault_y", "fault_z",
        "fault_vx", "fault_vy", "fault_vz",
        "fault_roll_deg", "fault_pitch_deg", "fault_max_motor_pwm",
    ]

    all_keys = []
    for r in rows:
        for k in r.keys():
            if k not in all_keys:
                all_keys.append(k)

    fieldnames = [k for k in preferred_fieldnames if k in all_keys]
    fieldnames += [k for k in all_keys if k not in fieldnames]

    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerows(rows)

    z_values = [r["z"] for r in rows]
    print("\n[SUMMARY]")
    print(f"z_min: {min(z_values):.3f} m")
    print(f"z_max: {max(z_values):.3f} m")
    print(f"z_final: {z_values[-1]:.3f} m")

    if fault_t is None:
        fault_t = 10.0

    contact_row, found, eval_result = evaluate_first_contact(rows, fault_t)

    print("\n[FIRST CONTACT ROW USED]")
    print(f"found_contact: {found}")
    for k in [
        "t", "phase", "x", "y", "z", "vx", "vy", "vz",
        "roll_deg", "pitch_deg", "yaw_deg",
        "gyro_x_deg_s", "gyro_y_deg_s", "gyro_z_deg_s",
        "motor_m1", "motor_m2", "motor_m3", "motor_m4",
        "z_cmd", "selected_candidate", "r1", "r2", "r3", "r4",
        "qp_score", "qp_predicted_vz",
    ]:
        print(f"{k}: {contact_row.get(k, '')}")

    print("\n[FIRST CONTACT EVALUATION]")
    for k, v in eval_result.items():
        print(f"{k}: {v}")

    print(f"\n[SAVED] {out_path}")


if __name__ == "__main__":
    main()
