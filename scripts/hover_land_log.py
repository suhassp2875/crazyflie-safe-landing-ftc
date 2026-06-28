import csv
import math
import os
import sys
import time
from pathlib import Path

import cflib.crtp
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

from eval.touchdown_metrics import evaluate_touchdown, TouchdownLimits


URI = os.environ.get("CF_URI", "udp://127.0.0.1:19850")
LOG_PATH = PROJECT_ROOT / "logs" / "hover_land_log.csv"

TAKEOFF_HEIGHT_M = 1.0
TAKEOFF_DURATION_S = 2.0
HOVER_TIME_S = 3.0
LAND_HEIGHT_M = 0.05
LANDING_DURATION_S = 4.0


class StateLogger:
    def __init__(self, cf, log_path: Path):
        self.cf = cf
        self.log_path = log_path
        self.rows = []
        self.start_time = time.time()
        self.configs = []
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

    def _append_row(self):
        row = {"t": time.time() - self.start_time}
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

    def last_valid_row(self):
        if not self.rows:
            return None

        needed = [
            "x", "y", "z",
            "vx", "vy", "vz",
            "roll_deg", "pitch_deg",
            "gyro_x_deg_s", "gyro_y_deg_s", "gyro_z_deg_s",
        ]

        for row in reversed(self.rows):
            if all(math.isfinite(row.get(k, float("nan"))) for k in needed):
                return row

        return None


def deg_to_rad(x):
    return x * math.pi / 180.0


def main():
    print(f"[INFO] Connecting to {URI}")
    cflib.crtp.init_drivers()

    with SyncCrazyflie(URI) as scf:
        cf = scf.cf
        print("[INFO] Connected.")

        logger = StateLogger(cf, LOG_PATH)

        try:
            print("[INFO] Enabling high-level commander.")
            cf.param.set_value("commander.enHighLevel", "1")
            time.sleep(1.0)

            logger.start()
            time.sleep(1.0)

            hl = cf.high_level_commander

            print(f"[INFO] Takeoff to {TAKEOFF_HEIGHT_M} m.")
            hl.takeoff(TAKEOFF_HEIGHT_M, TAKEOFF_DURATION_S)
            time.sleep(TAKEOFF_DURATION_S + 0.5)

            print(f"[INFO] Hover for {HOVER_TIME_S} s.")
            time.sleep(HOVER_TIME_S)

            print("[INFO] Emergency landing mode: scripted slow landing.")
            hl.land(LAND_HEIGHT_M, LANDING_DURATION_S)
            time.sleep(LANDING_DURATION_S + 1.0)

            print("[INFO] Stop high-level commander.")
            hl.stop()
            time.sleep(0.5)

        finally:
            logger.stop()

        last = logger.last_valid_row()

        if last is None:
            print("[RESULT] No valid touchdown row found.")
            return

        result = evaluate_touchdown(
            vx=last["vx"],
            vy=last["vy"],
            vz=last["vz"],
            roll=deg_to_rad(last["roll_deg"]),
            pitch=deg_to_rad(last["pitch_deg"]),
            wx=deg_to_rad(last["gyro_x_deg_s"]),
            wy=deg_to_rad(last["gyro_y_deg_s"]),
            wz=deg_to_rad(last["gyro_z_deg_s"]),
            x=last["x"],
            y=last["y"],
            limits=TouchdownLimits(),
        )

        print("\n[FINAL LOG ROW]")
        for k, v in last.items():
            print(f"{k}: {v}")

        print("\n[TOUCHDOWN EVALUATION]")
        for k, v in result.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
