import csv
import os
import time
from pathlib import Path

import cflib.crtp
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie


URI = os.environ.get("CF_URI", "udp://127.0.0.1:19850")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = PROJECT_ROOT / "logs" / "hover_setpoint_test.csv"


class PosLogger:
    def __init__(self, cf):
        self.cf = cf
        self.rows = []
        self.start_time = time.time()
        self.logconf = None

    def _on_data(self, timestamp, data, logconf):
        self.rows.append({
            "t": time.time() - self.start_time,
            "x": data.get("stateEstimate.x", float("nan")),
            "y": data.get("stateEstimate.y", float("nan")),
            "z": data.get("stateEstimate.z", float("nan")),
            "vx": data.get("stateEstimate.vx", float("nan")),
            "vy": data.get("stateEstimate.vy", float("nan")),
            "vz": data.get("stateEstimate.vz", float("nan")),
        })

    def _on_error(self, logconf, msg):
        print(f"[LOG ERROR] {logconf.name}: {msg}")

    def start(self):
        self.logconf = LogConfig(name="posvel", period_in_ms=50)
        self.logconf.add_variable("stateEstimate.x", "float")
        self.logconf.add_variable("stateEstimate.y", "float")
        self.logconf.add_variable("stateEstimate.z", "float")
        self.logconf.add_variable("stateEstimate.vx", "float")
        self.logconf.add_variable("stateEstimate.vy", "float")
        self.logconf.add_variable("stateEstimate.vz", "float")

        self.cf.log.add_config(self.logconf)
        self.logconf.data_received_cb.add_callback(self._on_data)
        self.logconf.error_cb.add_callback(self._on_error)
        self.logconf.start()
        print("[LOG] Started posvel logger.")

    def stop(self):
        if self.logconf is not None:
            try:
                self.logconf.stop()
            except Exception as e:
                print(f"[WARN] Could not stop logger cleanly: {e}")

        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        if not self.rows:
            print("[WARN] No rows collected.")
            return

        with open(LOG_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.rows[0].keys()))
            writer.writeheader()
            writer.writerows(self.rows)

        print(f"[LOG] Saved {len(self.rows)} rows to {LOG_PATH}")


def send_hover_for(cf, duration_s, z_m, vx=0.0, vy=0.0, yawrate=0.0, rate_hz=20):
    dt = 1.0 / rate_hz
    steps = int(duration_s * rate_hz)

    for _ in range(steps):
        cf.commander.send_hover_setpoint(vx, vy, yawrate, z_m)
        time.sleep(dt)


def main():
    print(f"[INFO] Connecting to {URI}")
    cflib.crtp.init_drivers()

    with SyncCrazyflie(URI) as scf:
        cf = scf.cf
        print("[INFO] Connected.")

        print("[INFO] Disabling high-level commander.")
        cf.param.set_value("commander.enHighLevel", "0")
        time.sleep(0.5)

        logger = PosLogger(cf)

        try:
            logger.start()
            time.sleep(0.5)

            print("[INFO] Sending zero setpoints for arming/initialization.")
            for _ in range(20):
                cf.commander.send_setpoint(0, 0, 0, 0)
                time.sleep(0.02)

            print("[INFO] Low-level hover command: z = 0.3 m for 3 s.")
            send_hover_for(cf, duration_s=3.0, z_m=0.3)

            print("[INFO] Low-level hover command: z = 0.7 m for 5 s.")
            send_hover_for(cf, duration_s=5.0, z_m=0.7)

            print("[INFO] Scripted descent.")
            for z in [0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05]:
                print(f"[INFO] Commanding z = {z:.2f} m")
                send_hover_for(cf, duration_s=0.8, z_m=z)

            print("[INFO] Stop setpoint.")
            cf.commander.send_stop_setpoint()
            time.sleep(0.5)

        finally:
            logger.stop()

        if logger.rows:
            z_values = [r["z"] for r in logger.rows]
            print(f"[RESULT] z_min = {min(z_values):.3f} m")
            print(f"[RESULT] z_max = {max(z_values):.3f} m")
            print(f"[RESULT] z_final = {z_values[-1]:.3f} m")


if __name__ == "__main__":
    main()
