import argparse
import csv
import math
import time
import warnings
from pathlib import Path

import cflib.crtp
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie


warnings.filterwarnings("ignore", category=DeprecationWarning)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

DEFAULT_URI = "udp://127.0.0.1:19850"

COMMAND_RATE_HZ = 50
GROUND_CONTACT_Z_M = 0.03

TAKEOFF_STAGE_1_Z_M = 0.30
TAKEOFF_Z_M = 0.70
FINAL_Z_M = 0.02

ARMING_S = 1.0
TAKEOFF_STAGE_1_S = 2.0
TAKEOFF_STAGE_2_S = 3.0
NOMINAL_HOVER_S = 3.0
FAULT_EVENT_S = 0.5
MAX_BRAKE_S = 8.0
TOUCHDOWN_HOLD_S = 2.0


class FlightLogger:
    def __init__(self, cf):
        self.cf = cf
        self.phase = "init"
        self.t0 = time.time()
        self.rows = []
        self.logconfs = []

        self.latest = {
            "x": float("nan"),
            "y": float("nan"),
            "z": float("nan"),
            "vx": float("nan"),
            "vy": float("nan"),
            "vz": float("nan"),
            "roll_deg": float("nan"),
            "pitch_deg": float("nan"),
            "yaw_deg": float("nan"),
            "gyro_x_deg_s": float("nan"),
            "gyro_y_deg_s": float("nan"),
            "gyro_z_deg_s": float("nan"),
            "motor_m1": float("nan"),
            "motor_m2": float("nan"),
            "motor_m3": float("nan"),
            "motor_m4": float("nan"),
            "z_cmd": float("nan"),
        }

    def set_phase(self, phase):
        self.phase = phase
        print(f"[PHASE] {phase}")

    def _make_logconf(self, name, period_ms, variables, callback):
        lg = LogConfig(name=name, period_in_ms=period_ms)
        for var, vtype in variables:
            lg.add_variable(var, vtype)

        self.cf.log.add_config(lg)
        lg.data_received_cb.add_callback(callback)
        lg.error_cb.add_callback(lambda logconf, msg: print(f"[LOG ERROR] {name}: {msg}"))
        self.logconfs.append(lg)

    def start(self):
        self._make_logconf(
            name="state",
            period_ms=50,
            variables=[
                ("stateEstimate.x", "float"),
                ("stateEstimate.y", "float"),
                ("stateEstimate.z", "float"),
                ("stateEstimate.vx", "float"),
                ("stateEstimate.vy", "float"),
                ("stateEstimate.vz", "float"),
            ],
            callback=self._on_state,
        )

        self._make_logconf(
            name="attitude",
            period_ms=50,
            variables=[
                ("stabilizer.roll", "float"),
                ("stabilizer.pitch", "float"),
                ("stabilizer.yaw", "float"),
            ],
            callback=self._on_attitude,
        )

        self._make_logconf(
            name="gyro",
            period_ms=50,
            variables=[
                ("gyro.x", "float"),
                ("gyro.y", "float"),
                ("gyro.z", "float"),
            ],
            callback=self._on_gyro,
        )

        self._make_logconf(
            name="motor_pwm",
            period_ms=50,
            variables=[
                ("motor.m1", "uint16_t"),
                ("motor.m2", "uint16_t"),
                ("motor.m3", "uint16_t"),
                ("motor.m4", "uint16_t"),
            ],
            callback=self._on_motor,
        )

        for lg in self.logconfs:
            lg.start()

        time.sleep(0.5)

    def stop(self):
        for lg in self.logconfs:
            try:
                lg.stop()
            except Exception:
                pass

    def _on_state(self, timestamp, data, logconf):
        self.latest["x"] = data.get("stateEstimate.x", float("nan"))
        self.latest["y"] = data.get("stateEstimate.y", float("nan"))
        self.latest["z"] = data.get("stateEstimate.z", float("nan"))
        self.latest["vx"] = data.get("stateEstimate.vx", float("nan"))
        self.latest["vy"] = data.get("stateEstimate.vy", float("nan"))
        self.latest["vz"] = data.get("stateEstimate.vz", float("nan"))

        row = {
            "t": time.time() - self.t0,
            "phase": self.phase,
            **self.latest,
        }
        self.rows.append(row)

    def _on_attitude(self, timestamp, data, logconf):
        self.latest["roll_deg"] = data.get("stabilizer.roll", float("nan"))
        self.latest["pitch_deg"] = data.get("stabilizer.pitch", float("nan"))
        self.latest["yaw_deg"] = data.get("stabilizer.yaw", float("nan"))

    def _on_gyro(self, timestamp, data, logconf):
        self.latest["gyro_x_deg_s"] = data.get("gyro.x", float("nan"))
        self.latest["gyro_y_deg_s"] = data.get("gyro.y", float("nan"))
        self.latest["gyro_z_deg_s"] = data.get("gyro.z", float("nan"))

    def _on_motor(self, timestamp, data, logconf):
        self.latest["motor_m1"] = data.get("motor.m1", float("nan"))
        self.latest["motor_m2"] = data.get("motor.m2", float("nan"))
        self.latest["motor_m3"] = data.get("motor.m3", float("nan"))
        self.latest["motor_m4"] = data.get("motor.m4", float("nan"))

    def save(self, path):
        if not self.rows:
            print("[WARN] No rows logged.")
            return

        keys = list(self.rows[0].keys())
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(self.rows)

        print(f"[LOG] Saved {len(self.rows)} rows to {path}")


def send_hover_for(cf, logger, z_cmd, duration_s):
    dt = 1.0 / COMMAND_RATE_HZ
    steps = int(duration_s * COMMAND_RATE_HZ)

    for _ in range(steps):
        logger.latest["z_cmd"] = z_cmd
        cf.commander.send_hover_setpoint(0.0, 0.0, 0.0, z_cmd)
        time.sleep(dt)


def send_max_brake_hold(cf, logger, start_z, duration_s):
    dt = 1.0 / COMMAND_RATE_HZ
    steps = int(duration_s * COMMAND_RATE_HZ)

    z_cmd = min(start_z + 0.25, 0.95)

    for _ in range(steps):
        z = logger.latest.get("z", float("nan"))

        logger.latest["z_cmd"] = z_cmd
        cf.commander.send_hover_setpoint(0.0, 0.0, 0.0, z_cmd)

        if z == z and z <= GROUND_CONTACT_Z_M:
            break

        time.sleep(dt)

    print(f"[FTCBOOST_MAXBRAKE] commanded z_cmd={z_cmd:.3f}")


def find_first_contact_row(rows):
    fault_t = None
    for r in rows:
        if r["phase"] == "fault_event":
            fault_t = r["t"]
            break

    if fault_t is None:
        post = rows
    else:
        post = [r for r in rows if r["t"] >= fault_t]

    contact = [r for r in post if float(r["z"]) <= GROUND_CONTACT_Z_M]

    if contact:
        return contact[0], True

    return min(post, key=lambda r: float(r["z"])), False


def evaluate_row(row):
    vx = float(row["vx"])
    vy = float(row["vy"])
    vz = float(row["vz"])
    x = float(row["x"])
    y = float(row["y"])
    roll = float(row["roll_deg"])
    pitch = float(row["pitch_deg"])

    gx = float(row.get("gyro_x_deg_s", 0.0))
    gy = float(row.get("gyro_y_deg_s", 0.0))
    gz = float(row.get("gyro_z_deg_s", 0.0))

    vertical_speed = abs(vz)
    horizontal_speed = math.sqrt(vx * vx + vy * vy)
    max_tilt = max(abs(roll), abs(pitch))
    angular_rate_radps = math.radians(math.sqrt(gx * gx + gy * gy + gz * gz))
    drift = math.sqrt(x * x + y * y)

    checks = {
        "vertical_speed_ok": vertical_speed <= 0.35,
        "horizontal_speed_ok": horizontal_speed <= 0.25,
        "roll_pitch_ok": max_tilt <= 12.0,
        "angular_rate_ok": angular_rate_radps <= 1.5,
        "drift_ok": drift <= 0.75,
    }

    return {
        "safe_touchdown": all(checks.values()),
        "vertical_speed_mps": vertical_speed,
        "horizontal_speed_mps": horizontal_speed,
        "max_tilt_deg": max_tilt,
        "angular_rate_radps": angular_rate_radps,
        "horizontal_drift_m": drift,
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", type=str, default=DEFAULT_URI)
    parser.add_argument("--motor", type=int, default=1)
    parser.add_argument("--eta", type=float, default=0.50)
    parser.add_argument("--boost", type=float, default=0.0, help="Extra PWM added to healthy motors after fault")
    parser.add_argument("--r1", type=float, default=0.0, help="Explicit residual PWM for motor 1")
    parser.add_argument("--r2", type=float, default=0.0, help="Explicit residual PWM for motor 2")
    parser.add_argument("--r3", type=float, default=0.0, help="Explicit residual PWM for motor 3")
    parser.add_argument("--r4", type=float, default=0.0, help="Explicit residual PWM for motor 4")
    args = parser.parse_args()

    fault_motor = int(args.motor)
    fault_eta = float(args.eta)
    healthy_boost = float(args.boost)
    residuals = [float(args.r1), float(args.r2), float(args.r3), float(args.r4)]

    boost_tag = f"b{int(healthy_boost)}"
    r_tag = f"r{int(residuals[0])}_{int(residuals[1])}_{int(residuals[2])}_{int(residuals[3])}"
    log_tag = f"ftcboost_m{fault_motor}_eta{fault_eta:.3f}_{boost_tag}_{r_tag}".replace(".", "p")
    log_path = LOG_DIR / f"motorloss_{log_tag}.csv"

    print("[CONFIG]")
    print(f"uri: {args.uri}")
    print(f"fault motor: {fault_motor}")
    print(f"fault eta: {fault_eta}")
    print(f"healthy boost PWM: {healthy_boost}")
    print(f"residuals PWM: {residuals}")
    print(f"log path: {log_path}")

    cflib.crtp.init_drivers()

    logger = None

    with SyncCrazyflie(args.uri) as scf:
        cf = scf.cf
        print("[INFO] Connected.")

        try:
            cf.param.set_value("commander.enHighLevel", "0")
            time.sleep(0.2)
        except Exception as e:
            print(f"[WARN] Could not disable high-level commander: {e}")

        # Reset fault/FTC params at the start.
        try:
            cf.param.set_value("sitlFtc.enable", "0")
            cf.param.set_value("sitlFtc.healthyBoost", "0")
            cf.param.set_value("sitlFtc.r1", "0")
            cf.param.set_value("sitlFtc.r2", "0")
            cf.param.set_value("sitlFtc.r3", "0")
            cf.param.set_value("sitlFtc.r4", "0")
            cf.param.set_value("sitlFault.enable", "0")
            cf.param.set_value("sitlFault.eta", "1.0")
            time.sleep(0.2)
        except Exception as e:
            print(f"[WARN] Could not reset SITL params at start: {e}")

        logger = FlightLogger(cf)
        logger.start()

        try:
            logger.set_phase("arming")
            send_hover_for(cf, logger, 0.0, ARMING_S)

            logger.set_phase("takeoff_stage_1")
            print(f"[CMD] takeoff stage 1 z={TAKEOFF_STAGE_1_Z_M:.2f}")
            send_hover_for(cf, logger, TAKEOFF_STAGE_1_Z_M, TAKEOFF_STAGE_1_S)

            logger.set_phase("takeoff_stage_2")
            print(f"[CMD] takeoff stage 2 z={TAKEOFF_Z_M:.2f}")
            send_hover_for(cf, logger, TAKEOFF_Z_M, TAKEOFF_STAGE_2_S)

            logger.set_phase("nominal_hover")
            print(f"[CMD] nominal hover z={TAKEOFF_Z_M:.2f}")
            send_hover_for(cf, logger, TAKEOFF_Z_M, NOMINAL_HOVER_S)

            logger.set_phase("fault_event")
            print(f"[FAULT] motor={fault_motor}, eta={fault_eta}")
            cf.param.set_value("sitlFault.motor", str(fault_motor))
            cf.param.set_value("sitlFault.eta", str(fault_eta))
            cf.param.set_value("sitlFault.enable", "1")

            cf.param.set_value("sitlFtc.healthyBoost", str(healthy_boost))
            cf.param.set_value("sitlFtc.r1", str(residuals[0]))
            cf.param.set_value("sitlFtc.r2", str(residuals[1]))
            cf.param.set_value("sitlFtc.r3", str(residuals[2]))
            cf.param.set_value("sitlFtc.r4", str(residuals[3]))

            ftc_enabled = healthy_boost > 0 or any(abs(r) > 0 for r in residuals)
            cf.param.set_value("sitlFtc.enable", "1" if ftc_enabled else "0")
            print(f"[FTC] healthy motor boost enabled: {healthy_boost:.1f} PWM")
            print(f"[FTC] explicit residuals enabled: r1={residuals[0]:.1f}, r2={residuals[1]:.1f}, r3={residuals[2]:.1f}, r4={residuals[3]:.1f}")

            send_hover_for(cf, logger, TAKEOFF_Z_M, FAULT_EVENT_S)

            logger.set_phase("max_brake_hold")
            print(f"[CMD] max-brake hold with healthy boost for {MAX_BRAKE_S:.1f}s")
            send_max_brake_hold(cf, logger, TAKEOFF_Z_M, MAX_BRAKE_S)

            logger.set_phase("touchdown_hold")
            print(f"[CMD] touchdown hold z={FINAL_Z_M:.2f}")
            send_hover_for(cf, logger, FINAL_Z_M, TOUCHDOWN_HOLD_S)

            logger.set_phase("stop")
            print("[CMD] stop setpoint")
            logger.latest["z_cmd"] = float("nan")
            cf.commander.send_stop_setpoint()
            time.sleep(0.5)

        finally:
            print("[INFO] Disabling SITL FTC/fault params.")
            try:
                cf.param.set_value("sitlFtc.enable", "0")
                cf.param.set_value("sitlFtc.healthyBoost", "0")
                cf.param.set_value("sitlFault.enable", "0")
                cf.param.set_value("sitlFault.eta", "1.0")
            except Exception as e:
                print(f"[WARN] Cleanup param reset failed: {e}")

            logger.stop()

    logger.save(log_path)

    if logger.rows:
        z_values = [float(r["z"]) for r in logger.rows]
        print("\n[SUMMARY]")
        print(f"z_min: {min(z_values):.3f} m")
        print(f"z_max: {max(z_values):.3f} m")
        print(f"z_final: {z_values[-1]:.3f} m")

        row, found_contact = find_first_contact_row(logger.rows)
        metrics = evaluate_row(row)

        print("\n[FIRST CONTACT ROW USED]")
        print(f"found_contact: {found_contact}")
        for k in [
            "t", "phase", "x", "y", "z", "vx", "vy", "vz",
            "roll_deg", "pitch_deg", "yaw_deg",
            "gyro_x_deg_s", "gyro_y_deg_s", "gyro_z_deg_s",
            "motor_m1", "motor_m2", "motor_m3", "motor_m4",
            "z_cmd",
        ]:
            print(f"{k}: {row.get(k)}")

        print("\n[FIRST CONTACT EVALUATION]")
        for k, v in metrics.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
