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

from src.controllers.residual_allocator_qp import AllocatorState, allocate_residual_qp, predict_metrics
from src.controllers.residual_allocator_tunable import load_weight_config, allocate_residual_tunable


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

    set_param(cf, "sitlPinv.enable", 0)
    set_param(cf, "sitlPinv.wThrust", 1.0)
    set_param(cf, "sitlPinv.wRoll", 1.0)
    set_param(cf, "sitlPinv.wPitch", 1.0)
    set_param(cf, "sitlPinv.wYaw", 0.2)
    set_param(cf, "sitlPinv.lambda", 1.0e-6)

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



def configure_pinv(
    cf,
    w_thrust,
    w_roll,
    w_pitch,
    w_yaw,
    regularization,
):
    # PINV and residual allocation are mutually exclusive.
    clear_residual(cf)

    set_param(cf, "sitlPinv.wThrust", float(w_thrust))
    set_param(cf, "sitlPinv.wRoll", float(w_roll))
    set_param(cf, "sitlPinv.wPitch", float(w_pitch))
    set_param(cf, "sitlPinv.wYaw", float(w_yaw))
    set_param(cf, "sitlPinv.lambda", float(regularization))
    set_param(cf, "sitlPinv.enable", 1)


def clear_pinv(cf):
    set_param(cf, "sitlPinv.enable", 0)

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

    pinv_motor_lg = LogConfig(
        name="pinv_motor_allocation",
        period_in_ms=period_ms,
    )

    for name, typ in [
        ("pinvAlloc.nom1", "uint16_t"),
        ("pinvAlloc.nom2", "uint16_t"),
        ("pinvAlloc.nom3", "uint16_t"),
        ("pinvAlloc.nom4", "uint16_t"),
        ("pinvAlloc.alloc1", "uint16_t"),
        ("pinvAlloc.alloc2", "uint16_t"),
        ("pinvAlloc.alloc3", "uint16_t"),
        ("pinvAlloc.alloc4", "uint16_t"),
        ("pinvAlloc.active", "uint8_t"),
    ]:
        pinv_motor_lg.add_variable(name, typ)

    pinv_error_lg = LogConfig(
        name="pinv_allocation_error",
        period_in_ms=period_ms,
    )

    for name, typ in [
        ("pinvAlloc.errT", "float"),
        ("pinvAlloc.errR", "float"),
        ("pinvAlloc.errP", "float"),
        ("pinvAlloc.errY", "float"),
        ("pinvAlloc.objective", "float"),
    ]:
        pinv_error_lg.add_variable(name, typ)

    return [
        state_lg,
        attitude_lg,
        motor_lg,
        pinv_motor_lg,
        pinv_error_lg,
    ]


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
        # No touchdown within the evaluation window.
        # This is not a safe touchdown. We still return the minimum-z row for diagnostics,
        # but the final safe_touchdown flag is forced to False below.
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

    safe = found and all(checks.values())

    return row, found, {
        "contact_found": found,
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

    # Controlled randomized trial metadata.
    # These are generated by scripts/seeded_trial_params.py and logged into every CSV.
    parser.add_argument("--protocol-id", default="fixed_nominal_protocol")
    parser.add_argument("--trial-seed", type=int, default=-1)
    parser.add_argument("--spawn-x", type=float, default=0.0)
    parser.add_argument("--spawn-y", type=float, default=0.0)
    parser.add_argument("--spawn-yaw-deg", type=float, default=0.0)
    parser.add_argument("--fault-time", type=float, default=10.0)
    parser.add_argument("--hover-z", type=float, default=0.70)

    # Post-fault landing protocol.
    # legacy_maxbrake_touchdown reproduces the old pilot protocol:
    #   fixed high z_cmd brake, then abrupt z_cmd=0.02.
    # adaptive_ramp_v1 is the publication protocol:
    #   brake only when descending too fast, otherwise follow a slow descent ramp.
    parser.add_argument("--post-fault-mode",
                        choices=["legacy_maxbrake_touchdown", "adaptive_ramp_v1"],
                        default="legacy_maxbrake_touchdown")
    parser.add_argument("--eval-duration", type=float, default=-1.0)
    parser.add_argument("--brake-z-cmd", type=float, default=0.95)
    parser.add_argument("--brake-vz-threshold", type=float, default=-0.15)
    parser.add_argument("--landing-descent-rate", type=float, default=0.08)
    parser.add_argument("--landing-final-z", type=float, default=0.02)

    # Trial-validity gate evaluated immediately before fault injection.
    parser.add_argument("--min-valid-fault-z", type=float, default=0.50)
    parser.add_argument("--max-valid-fault-abs-vz", type=float, default=0.25)
    parser.add_argument("--weight-config", default=None,
                        help="Optional JSON config for tunable allocator weights.")
    parser.add_argument("--manual-residual", action="store_true",
                        help="Bypass allocator and apply --r1..--r4 once at fault event.")
    parser.add_argument("--manual-name", default="manual_residual")
    parser.add_argument("--r1", type=int, default=0)
    parser.add_argument("--r2", type=int, default=0)
    parser.add_argument("--r3", type=int, default=0)
    parser.add_argument("--r4", type=int, default=0)
    parser.add_argument(
        "--controller",
        choices=["qplite", "pinv"],
        default="qplite",
        help=(
            "qplite uses the empirical residual allocator; "
            "pinv uses firmware bounded weighted least-squares "
            "allocation."
        ),
    )
    parser.add_argument(
        "--pinv-w-thrust",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--pinv-w-roll",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--pinv-w-pitch",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--pinv-w-yaw",
        type=float,
        default=0.2,
    )
    parser.add_argument(
        "--pinv-lambda",
        type=float,
        default=1.0e-6,
    )

    args = parser.parse_args()

    if args.motor not in [1, 2, 3, 4]:
        raise SystemExit("--motor must be 1, 2, 3, or 4")

    if args.controller == "pinv":
        if getattr(args, "manual_residual", False):
            raise SystemExit(
                "--manual-residual cannot be combined with "
                "--controller pinv"
            )

        if getattr(args, "weight_config", None):
            raise SystemExit(
                "--weight-config applies only to "
                "--controller qplite"
            )

    if args.pinv_lambda < 0.0:
        raise SystemExit(
            "--pinv-lambda must be non-negative"
        )

    for option_name, option_value in [
        ("--pinv-w-thrust", args.pinv_w_thrust),
        ("--pinv-w-roll", args.pinv_w_roll),
        ("--pinv-w-pitch", args.pinv_w_pitch),
        ("--pinv-w-yaw", args.pinv_w_yaw),
    ]:
        if option_value <= 0.0:
            raise SystemExit(
                f"{option_name} must be positive"
            )

    fault_trigger_time = float(args.fault_time)
    hover_z = float(args.hover_z)
    stage1_z = max(0.20, min(0.35, 0.43 * hover_z))

    eval_duration = float(args.eval_duration)
    if eval_duration <= 0.0:
        if args.post_fault_mode == "adaptive_ramp_v1":
            eval_duration = 18.0
        else:
            eval_duration = float(args.max_brake_duration) + 2.0

    eta_tag = f"{args.eta:.3f}".replace(".", "p")
    out_path = Path("logs") / f"qp_event_allocator_m{args.motor}_eta{eta_tag}_{args.tag}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(
        f"[INFO] Starting fault-triggered landing "
        f"controller={args.controller}"
    )
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
    allocator_config_name = (
        "pinv_bounded_wls_"
        f"w{args.pinv_w_thrust:g}_"
        f"{args.pinv_w_roll:g}_"
        f"{args.pinv_w_pitch:g}_"
        f"{args.pinv_w_yaw:g}_"
        f"lambda{args.pinv_lambda:g}"
        if args.controller == "pinv"
        else "qplite_builtin"
    )

    weight_cfg = None

    if args.controller == "qplite" and args.weight_config:
        weight_cfg = load_weight_config(args.weight_config)
        allocator_config_name = weight_cfg.name
        print(
            "[INFO] Using tunable allocator config: "
            f"{args.weight_config} "
            f"({allocator_config_name})"
        )

    fault_state_snapshot = {}

    required_keys = [
        "stateEstimate.x",
        "stateEstimate.y",
        "stateEstimate.z",
        "stateEstimate.vx",
        "stateEstimate.vy",
        "stateEstimate.vz",
        "stabilizer.roll",
        "stabilizer.pitch",
        "stabilizer.yaw",
        "gyro.x",
        "gyro.y",
        "gyro.z",
        "motor.m1",
        "motor.m2",
        "motor.m3",
        "motor.m4",
        "pinvAlloc.nom1",
        "pinvAlloc.nom2",
        "pinvAlloc.nom3",
        "pinvAlloc.nom4",
        "pinvAlloc.alloc1",
        "pinvAlloc.alloc2",
        "pinvAlloc.alloc3",
        "pinvAlloc.alloc4",
        "pinvAlloc.active",
        "pinvAlloc.errT",
        "pinvAlloc.errR",
        "pinvAlloc.errP",
        "pinvAlloc.errY",
        "pinvAlloc.objective",
    ]

    with SyncCrazyflie(args.uri, cf=Crazyflie()) as scf:
        cf = scf.cf

        reset_sitl_fault_and_ftc(cf)

        if args.controller == "pinv":
            configure_pinv(
                cf,
                w_thrust=args.pinv_w_thrust,
                w_roll=args.pinv_w_roll,
                w_pitch=args.pinv_w_pitch,
                w_yaw=args.pinv_w_yaw,
                regularization=args.pinv_lambda,
            )
        else:
            clear_pinv(cf)

        try:
            cf.platform.send_arming_request(True)
            time.sleep(1.0)
        except Exception as e:
            print(f"[WARN] arming request failed/nonfatal: {e}")

        log_configs = make_log_configs(args.log_period_ms)
        latest = {}
        t0 = time.time()

        with SyncLogger(scf, log_configs) as logger:
            for _, data, log_config in logger:
                latest.update(data)

                # PINV diagnostics are observational only. Do not allow the
                # two additional telemetry streams to increase the command,
                # fault-trigger or trajectory-update cadence relative to the
                # original three-log landing protocol.
                log_name = getattr(log_config, "name", "")

                if log_name in {
                    "pinv_motor_allocation",
                    "pinv_allocation_error",
                }:
                    continue

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
                    z_cmd = stage1_z

                elif t < 8.0:
                    phase = "takeoff_stage_2"
                    z_cmd = hover_z

                elif t < fault_trigger_time:
                    phase = "nominal_hover"
                    z_cmd = hover_z

                elif t < fault_trigger_time + eval_duration:
                    tau_fault = t - fault_trigger_time

                    if not allocated:
                        phase = "fault_event"
                        fault_t = t

                        allocator_state = make_allocator_state(data)

                        # Hard pre-fault trial-validity gate.
                        # A trial is invalid if the vehicle never became properly airborne
                        # or if the fault would be injected from an excessive vertical-speed state.
                        if allocator_state.z < float(args.min_valid_fault_z):
                            raise RuntimeError(
                                "INVALID_PREFAULT_STATE: "
                                f"fault_z={allocator_state.z:.6f} "
                                f"< min_valid_fault_z={args.min_valid_fault_z:.6f}"
                            )

                        if abs(allocator_state.vz) > float(args.max_valid_fault_abs_vz):
                            raise RuntimeError(
                                "INVALID_PREFAULT_STATE: "
                                f"|fault_vz|={abs(allocator_state.vz):.6f} "
                                f"> max_valid_fault_abs_vz={args.max_valid_fault_abs_vz:.6f}"
                            )

                        if args.controller == "pinv":
                            selected_candidate = (
                                "bounded_fault_aware_wls"
                            )
                            selected_r = [0, 0, 0, 0]
                            selected_score = 0.0
                            selected_pred_vz = 0.0
                            selected_pred_drift = 0.0
                            selected_pred_tilt = 0.0

                        elif args.manual_residual:
                            selected_r = [
                                int(args.r1),
                                int(args.r2),
                                int(args.r3),
                                int(args.r4),
                            ]

                            if selected_r[args.motor - 1] != 0:
                                raise RuntimeError(
                                    "Manual residual must be zero "
                                    "on the faulted motor."
                                )

                            selected_candidate = args.manual_name

                            (
                                selected_pred_vz,
                                selected_pred_drift,
                                selected_pred_tilt,
                            ) = predict_metrics(
                                fault_motor=args.motor,
                                eta=args.eta,
                                state=allocator_state,
                                residual=selected_r,
                            )

                            selected_score = 0.0
                            allocator_config_name = (
                                "manual_residual_sweep"
                            )

                        else:
                            if weight_cfg is not None:
                                allocation = (
                                    allocate_residual_tunable(
                                        args.motor,
                                        args.eta,
                                        allocator_state,
                                        weight_cfg,
                                    )
                                )
                            else:
                                allocation = allocate_residual_qp(
                                    args.motor,
                                    args.eta,
                                    allocator_state,
                                )

                            selected_candidate = (
                                allocation.candidate_name
                            )
                            selected_r = allocation.residual
                            selected_score = float(
                                allocation.score
                            )
                            selected_pred_vz = float(
                                allocation.predicted_vz
                            )
                            selected_pred_drift = float(
                                allocation.predicted_drift
                            )
                            selected_pred_tilt = float(
                                allocation.predicted_tilt
                            )

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

                        print(
                            f"[{args.controller.upper()} "
                            "EVENT ALLOCATION]"
                        )
                        print(f"fault_t: {fault_t:.3f}")
                        print(f"fault_state: {fault_state_snapshot}")
                        print(f"candidate: {selected_candidate}")
                        print(f"residual: {selected_r}")
                        print(f"score: {selected_score:.6f}")
                        print(f"predicted_vz: {selected_pred_vz:.6f}")
                        print(f"predicted_drift: {selected_pred_drift:.6f}")
                        print(f"predicted_tilt: {selected_pred_tilt:.6f}")

                        if args.controller == "pinv":
                            # PINV has already been configured and enabled.
                            # The healthy fast path kept it transparent until
                            # this fault becomes active.
                            inject_fault(
                                cf,
                                args.motor,
                                args.eta,
                            )
                        else:
                            inject_fault(
                                cf,
                                args.motor,
                                args.eta,
                            )
                            apply_residual(cf, selected_r)

                        allocated = True

                    if phase != "fault_event":
                        if args.post_fault_mode == "adaptive_ramp_v1":
                            current_vz = fget(data, "stateEstimate.vz")
                            ramp_z = max(
                                float(args.landing_final_z),
                                hover_z - float(args.landing_descent_rate) * tau_fault,
                            )

                            # Brake only when the vehicle is actually descending too fast.
                            # Otherwise, command a slow ramp to ground. This avoids the old
                            # artifact where less-severe faults survived the brake phase and
                            # were then slammed down by an abrupt z_cmd=0.02.
                            if (
                                tau_fault <= float(args.max_brake_duration)
                                and current_vz < float(args.brake_vz_threshold)
                            ):
                                phase = "adaptive_brake"
                                z_cmd = float(args.brake_z_cmd)
                            else:
                                phase = "landing_ramp"
                                z_cmd = ramp_z
                        else:
                            if tau_fault < float(args.max_brake_duration):
                                phase = "max_brake_hold"
                                z_cmd = float(args.brake_z_cmd)
                            else:
                                phase = "touchdown_hold"
                                z_cmd = float(args.landing_final_z)

                else:
                    break

                cf.commander.send_hover_setpoint(0.0, 0.0, 0.0, z_cmd)

                row = {
                    "protocol_id": args.protocol_id,
                    "trial_seed": int(args.trial_seed),
                    "spawn_x_cmd": float(args.spawn_x),
                    "spawn_y_cmd": float(args.spawn_y),
                    "spawn_yaw_deg_cmd": float(args.spawn_yaw_deg),
                    "fault_time_cmd": float(fault_trigger_time),
                    "hover_z_cmd": float(hover_z),
                    "post_fault_mode": args.post_fault_mode,
                    "eval_duration_cmd": float(eval_duration),
                    "landing_descent_rate_cmd": float(args.landing_descent_rate),
                    "stage1_z_cmd": float(stage1_z),
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
                    "controller": args.controller,
                    "allocator_config": allocator_config_name,

                    "pinv_w_thrust": float(
                        args.pinv_w_thrust
                    ),
                    "pinv_w_roll": float(
                        args.pinv_w_roll
                    ),
                    "pinv_w_pitch": float(
                        args.pinv_w_pitch
                    ),
                    "pinv_w_yaw": float(
                        args.pinv_w_yaw
                    ),
                    "pinv_lambda": float(
                        args.pinv_lambda
                    ),

                    "pinv_nom_m1": int(
                        fget(data, "pinvAlloc.nom1")
                    ),
                    "pinv_nom_m2": int(
                        fget(data, "pinvAlloc.nom2")
                    ),
                    "pinv_nom_m3": int(
                        fget(data, "pinvAlloc.nom3")
                    ),
                    "pinv_nom_m4": int(
                        fget(data, "pinvAlloc.nom4")
                    ),

                    "pinv_alloc_m1": int(
                        fget(data, "pinvAlloc.alloc1")
                    ),
                    "pinv_alloc_m2": int(
                        fget(data, "pinvAlloc.alloc2")
                    ),
                    "pinv_alloc_m3": int(
                        fget(data, "pinvAlloc.alloc3")
                    ),
                    "pinv_alloc_m4": int(
                        fget(data, "pinvAlloc.alloc4")
                    ),

                    "pinv_active_mask": int(
                        fget(data, "pinvAlloc.active")
                    ),
                    "pinv_err_thrust": fget(
                        data,
                        "pinvAlloc.errT",
                    ),
                    "pinv_err_roll": fget(
                        data,
                        "pinvAlloc.errR",
                    ),
                    "pinv_err_pitch": fget(
                        data,
                        "pinvAlloc.errP",
                    ),
                    "pinv_err_yaw": fget(
                        data,
                        "pinvAlloc.errY",
                    ),
                    "pinv_objective": fget(
                        data,
                        "pinvAlloc.objective",
                    ),

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
        clear_pinv(cf)
        set_param(cf, "sitlFault.enable", 0)

    if not rows:
        raise SystemExit("[ERROR] No rows logged.")

    preferred_fieldnames = [
        "protocol_id", "trial_seed",
        "spawn_x_cmd", "spawn_y_cmd", "spawn_yaw_deg_cmd",
        "fault_time_cmd", "hover_z_cmd", "stage1_z_cmd",
        "post_fault_mode", "eval_duration_cmd", "landing_descent_rate_cmd",
        "t", "phase",
        "x", "y", "z", "vx", "vy", "vz",
        "roll_deg", "pitch_deg", "yaw_deg",
        "gyro_x_deg_s", "gyro_y_deg_s", "gyro_z_deg_s",
        "motor_m1", "motor_m2", "motor_m3", "motor_m4",
        "z_cmd",
        "controller",
        "allocator_config",
        "selected_candidate",
        "pinv_w_thrust",
        "pinv_w_roll",
        "pinv_w_pitch",
        "pinv_w_yaw",
        "pinv_lambda",
        "pinv_nom_m1",
        "pinv_nom_m2",
        "pinv_nom_m3",
        "pinv_nom_m4",
        "pinv_alloc_m1",
        "pinv_alloc_m2",
        "pinv_alloc_m3",
        "pinv_alloc_m4",
        "pinv_active_mask",
        "pinv_err_thrust",
        "pinv_err_roll",
        "pinv_err_pitch",
        "pinv_err_yaw",
        "pinv_objective",
        "r1", "r2", "r3", "r4",
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
        fault_t = fault_trigger_time

    contact_row, found, eval_result = evaluate_first_contact(rows, fault_t)

    print("\n[FIRST CONTACT ROW USED]")
    print(f"found_contact: {found}")
    for k in [
        "t", "phase", "x", "y", "z", "vx", "vy", "vz",
        "roll_deg", "pitch_deg", "yaw_deg",
        "gyro_x_deg_s", "gyro_y_deg_s", "gyro_z_deg_s",
        "motor_m1", "motor_m2", "motor_m3", "motor_m4",
        "z_cmd", "controller", "selected_candidate",
        "r1", "r2", "r3", "r4",
        "pinv_active_mask",
        "pinv_alloc_m1", "pinv_alloc_m2",
        "pinv_alloc_m3", "pinv_alloc_m4",
        "pinv_err_thrust", "pinv_err_yaw",
        "pinv_objective",
        "qp_score", "qp_predicted_vz",
    ]:
        print(f"{k}: {contact_row.get(k, '')}")

    print("\n[FIRST CONTACT EVALUATION]")
    for k, v in eval_result.items():
        print(f"{k}: {v}")

    print(f"\n[SAVED] {out_path}")


if __name__ == "__main__":
    main()
