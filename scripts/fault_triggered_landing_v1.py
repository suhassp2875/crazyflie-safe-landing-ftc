import csv
import math
import os
import sys
import time
import warnings
from pathlib import Path

import cflib.crtp
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

# Hide CFLib legacy hover warning spam.
warnings.filterwarnings("ignore", category=DeprecationWarning)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

from eval.touchdown_metrics import evaluate_touchdown, TouchdownLimits


URI = os.environ.get("CF_URI", "udp://127.0.0.1:19850")
LOG_PATH = PROJECT_ROOT / "logs" / "fault_triggered_landing_v1.csv"

# Scenario parameters
TAKEOFF_Z_M = 0.7
TAKEOFF_STAGE_1_Z_M = 0.3
TAKEOFF_STAGE_1_S = 2.0
TAKEOFF_STAGE_2_S = 3.0

NOMINAL_HOVER_S = 3.0
EMERGENCY_LANDING_S = 6.0
TOUCHDOWN_HOLD_S = 2.0
FINAL_Z_M = 0.02

COMMAND_RATE_HZ = 20
GROUND_CONTACT_Z_M = 0.03


class StateLogger:
    def __init__(self, cf, log_path: Path):
        self.cf = cf
        self.log_path = log_path
        self.rows = []
        self.start_time = time.time()
        self.configs = []
        self.phase = "init"

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
        }

    def set_phase(self, phase: str):
        self.phase = phase
        print(f"[PHASE] {phase}")

    def _append_row(self):
        row = {
            "t": time.time() - self.start_time,
            "phase": self.phase,
        }
        row.update(self.latest)
        self.rows.append(row)

    def _on_posvel(self, timestamp, data, logconf):
        self.latest["x"] = data.get("stateEstimate.x", float("nan"))
        self.latest["y"] = data.get("stateEstimate.y", float("nan"))
        self.latest["z"] = data.get("stateEstimate.z", float("nan"))
        self.latest["vx"] = data.get("stateEstimate.vx", float("nan"))
        self.latest["vy"] = data.get("stateEstimate.vy", float("nan"))
        self.latest["vz"] = data.get("stateEstimate.vz", float("nan"))
        self._append_row()

    def _on_attitude(self, timestamp, data, logconf):
        self.latest["roll_deg"] = data.get("stabilizer.roll", float("nan"))
        self.latest["pitch_deg"] = data.get("stabilizer.pitch", float("nan"))
        self.latest["yaw_deg"] = data.get("stabilizer.yaw", float("nan"))

    def _on_gyro(self, timestamp, data, logconf):
        self.latest["gyro_x_deg_s"] = data.get("gyro.x", float("nan"))
        self.latest["gyro_y_deg_s"] = data.get("gyro.y", float("nan"))
        self.latest["gyro_z_deg_s"] = data.get("gyro.z", float("nan"))

    def _on_error(self, logconf, msg):
        print(f"[LOG ERROR] {logconf.name}: {msg}")

    def _make_logconf(self, name, period_ms, variables, callback):
        logconf = LogConfig(name=name, period_in_ms=period_ms)

        for var_name, var_type in variables:
            logconf.add_variable(var_name, var_type)

        self.cf.log.add_config(logconf)
        logconf.data_received_cb.add_callback(callback)
        logconf.error_cb.add_callback(self._on_error)
        logconf.start()

        self.configs.append(logconf)
        print(f"[LOG] Started log block: {name}")

    def start(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        self._make_logconf(
            name="posvel",
            period_ms=50,
            variables=[
                ("stateEstimate.x", "float"),
                ("stateEstimate.y", "float"),
                ("stateEstimate.z", "float"),
                ("stateEstimate.vx", "float"),
                ("stateEstimate.vy", "float"),
                ("stateEstimate.vz", "float"),
            ],
            callback=self._on_posvel,
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

    def stop(self):
        for logconf in self.configs:
            try:
                logconf.stop()
            except Exception as e:
                print(f"[WARN] Could not stop {logconf.name} cleanly: {e}")

        if not self.rows:
            print("[WARN] No log rows collected.")
            return

        with open(self.log_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.rows[0].keys()))
            writer.writeheader()
            writer.writerows(self.rows)

        print(f"[LOG] Saved {len(self.rows)} rows to {self.log_path}")


def deg_to_rad(x):
    return x * math.pi / 180.0


def finite_row(row):
    needed = [
        "x", "y", "z",
        "vx", "vy", "vz",
        "roll_deg", "pitch_deg",
        "gyro_x_deg_s", "gyro_y_deg_s", "gyro_z_deg_s",
    ]
    return all(math.isfinite(row.get(k, float("nan"))) for k in needed)


def send_hover_for(cf, logger, duration_s, z_m, vx=0.0, vy=0.0, yawrate=0.0):
    dt = 1.0 / COMMAND_RATE_HZ
    steps = int(duration_s * COMMAND_RATE_HZ)

    for _ in range(steps):
        cf.commander.send_hover_setpoint(vx, vy, yawrate, z_m)
        time.sleep(dt)


def send_ramped_landing(cf, logger, start_z, end_z, duration_s):
    dt = 1.0 / COMMAND_RATE_HZ
    steps = int(duration_s * COMMAND_RATE_HZ)

    for i in range(steps):
        alpha = i / max(steps - 1, 1)
        z_cmd = (1.0 - alpha) * start_z + alpha * end_z
        cf.commander.send_hover_setpoint(0.0, 0.0, 0.0, z_cmd)
        time.sleep(dt)


def find_touchdown_row(rows):
    # Use the first true near-ground row after the fault-triggered landing starts.
    # This avoids evaluating too early while the vehicle is still above the ground.
    touchdown_phases = {"emergency_landing", "touchdown_hold"}

    for row in rows:
        if row.get("phase") in touchdown_phases and finite_row(row):
            if row["z"] <= GROUND_CONTACT_Z_M:
                return row

    # If it still did not reach the ground before stop, report the last landing row.
    for row in reversed(rows):
        if row.get("phase") in touchdown_phases and finite_row(row):
            return row

    # Final fallback: last finite row overall.
    for row in reversed(rows):
        if finite_row(row):
            return row

    return None


def evaluate_row(row):
    return evaluate_touchdown(
        vx=row["vx"],
        vy=row["vy"],
        vz=row["vz"],
        roll=deg_to_rad(row["roll_deg"]),
        pitch=deg_to_rad(row["pitch_deg"]),
        wx=deg_to_rad(row["gyro_x_deg_s"]),
        wy=deg_to_rad(row["gyro_y_deg_s"]),
        wz=deg_to_rad(row["gyro_z_deg_s"]),
        x=row["x"],
        y=row["y"],
        limits=TouchdownLimits(),
    )


def main():
    print(f"[INFO] Connecting to {URI}")
    cflib.crtp.init_drivers()

    with SyncCrazyflie(URI) as scf:
        cf = scf.cf
        print("[INFO] Connected.")

        print("[INFO] Using low-level hover commander.")
        cf.param.set_value("commander.enHighLevel", "0")
        time.sleep(0.5)

        logger = StateLogger(cf, LOG_PATH)

        try:
            logger.start()
            time.sleep(0.5)

            logger.set_phase("arming")
            for _ in range(20):
                cf.commander.send_setpoint(0, 0, 0, 0)
                time.sleep(0.02)

            logger.set_phase("takeoff_stage_1")
            print(f"[CMD] z = {TAKEOFF_STAGE_1_Z_M:.2f} m")
            send_hover_for(cf, logger, TAKEOFF_STAGE_1_S, TAKEOFF_STAGE_1_Z_M)

            logger.set_phase("takeoff_stage_2")
            print(f"[CMD] z = {TAKEOFF_Z_M:.2f} m")
            send_hover_for(cf, logger, TAKEOFF_STAGE_2_S, TAKEOFF_Z_M)

            logger.set_phase("nominal_hover")
            print(f"[CMD] hover at z = {TAKEOFF_Z_M:.2f} m for {NOMINAL_HOVER_S:.1f} s")
            send_hover_for(cf, logger, NOMINAL_HOVER_S, TAKEOFF_Z_M)

            logger.set_phase("fault_event")
            print("[FAULT EVENT] Simulated fault trigger. Real motor loss not injected yet.")
            time.sleep(0.5)

            logger.set_phase("emergency_landing")
            print(f"[CMD] emergency ramp landing: {TAKEOFF_Z_M:.2f} m → {FINAL_Z_M:.2f} m over {EMERGENCY_LANDING_S:.1f} s")
            send_ramped_landing(cf, logger, TAKEOFF_Z_M, FINAL_Z_M, EMERGENCY_LANDING_S)

            logger.set_phase("touchdown_hold")
            print(f"[CMD] holding low altitude z = {FINAL_Z_M:.2f} m for {TOUCHDOWN_HOLD_S:.1f} s before stop")
            send_hover_for(cf, logger, TOUCHDOWN_HOLD_S, FINAL_Z_M)

            logger.set_phase("stop")
            print("[CMD] stop setpoint")
            cf.commander.send_stop_setpoint()
            time.sleep(0.5)

        finally:
            logger.stop()

        touchdown = find_touchdown_row(logger.rows)

        if touchdown is None:
            print("[RESULT] No touchdown row found.")
            return

        result = evaluate_row(touchdown)

        z_values = [r["z"] for r in logger.rows if math.isfinite(r.get("z", float("nan")))]

        print("\n[SUMMARY]")
        print(f"z_min: {min(z_values):.3f} m")
        print(f"z_max: {max(z_values):.3f} m")
        print(f"z_final: {z_values[-1]:.3f} m")

        print("\n[TOUCHDOWN ROW USED]")
        for k, v in touchdown.items():
            print(f"{k}: {v}")

        print("\n[TOUCHDOWN EVALUATION]")
        for k, v in result.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
