import math
import re
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

from eval.touchdown_metrics import evaluate_touchdown, TouchdownLimits


GROUND_CONTACT_Z_M = 0.03


def deg_to_rad(x):
    return x * math.pi / 180.0


def finite_row(row):
    needed = [
        "x", "y", "z",
        "vx", "vy", "vz",
        "roll_deg", "pitch_deg",
        "gyro_x_deg_s", "gyro_y_deg_s", "gyro_z_deg_s",
    ]
    return all(math.isfinite(float(row[k])) for k in needed)


def find_touchdown_row(df):
    touchdown_phases = {"emergency_landing", "touchdown_hold", "stop"}

    for _, row in df.iterrows():
        if row.get("phase") in touchdown_phases and finite_row(row):
            if row["z"] <= GROUND_CONTACT_Z_M:
                return row

    for _, row in df.iloc[::-1].iterrows():
        if row.get("phase") in touchdown_phases and finite_row(row):
            return row

    for _, row in df.iloc[::-1].iterrows():
        if finite_row(row):
            return row

    return None


def parse_eta_motor(path):
    name = path.stem
    m = re.search(r"m(\d+)_eta(\d+)p(\d+)", name)
    if not m:
        return None, None

    motor = int(m.group(1))
    eta = float(f"{m.group(2)}.{m.group(3)}")
    return motor, eta


def main():
    rows = []

    for path in sorted((PROJECT_ROOT / "logs").glob("motorloss_m*_eta*.csv")):
        df = pd.read_csv(path)
        motor, eta = parse_eta_motor(path)

        z_max_run = df["z"].max()

        if z_max_run < 0.5:
            rows.append({
                "file": path.name,
                "motor": motor,
                "eta": eta,
                "safe_touchdown": False,
                "vertical_speed_mps": float("nan"),
                "horizontal_speed_mps": float("nan"),
                "touchdown_tilt_deg": float("nan"),
                "touchdown_angular_rate_radps": float("nan"),
                "horizontal_drift_m": float("nan"),
                "max_tilt_after_fault_deg": float("nan"),
                "z_min": df["z"].min(),
                "z_max": z_max_run,
                "status": "INVALID_NO_TAKEOFF",
            })
            continue

        touchdown = find_touchdown_row(df)

        if touchdown is None:
            rows.append({
                "file": path.name,
                "motor": motor,
                "eta": eta,
                "safe_touchdown": False,
                "vertical_speed_mps": float("nan"),
                "horizontal_speed_mps": float("nan"),
                "touchdown_tilt_deg": float("nan"),
                "touchdown_angular_rate_radps": float("nan"),
                "horizontal_drift_m": float("nan"),
                "max_tilt_after_fault_deg": float("nan"),
                "z_min": df["z"].min(),
                "z_max": z_max_run,
                "status": "NO_TOUCHDOWN_ROW",
            })
            continue

        result = evaluate_touchdown(
            vx=float(touchdown["vx"]),
            vy=float(touchdown["vy"]),
            vz=float(touchdown["vz"]),
            roll=deg_to_rad(float(touchdown["roll_deg"])),
            pitch=deg_to_rad(float(touchdown["pitch_deg"])),
            wx=deg_to_rad(float(touchdown["gyro_x_deg_s"])),
            wy=deg_to_rad(float(touchdown["gyro_y_deg_s"])),
            wz=deg_to_rad(float(touchdown["gyro_z_deg_s"])),
            x=float(touchdown["x"]),
            y=float(touchdown["y"]),
            limits=TouchdownLimits(),
        )

        fault_landing = df[df["phase"].isin(["fault_event", "emergency_landing", "touchdown_hold"])]
        max_abs_roll = fault_landing["roll_deg"].abs().max() if "roll_deg" in fault_landing else float("nan")
        max_abs_pitch = fault_landing["pitch_deg"].abs().max() if "pitch_deg" in fault_landing else float("nan")
        max_tilt_episode = max(max_abs_roll, max_abs_pitch)

        rows.append({
            "file": path.name,
            "motor": motor,
            "eta": eta,
            "safe_touchdown": result["safe_touchdown"],
            "vertical_speed_mps": result["vertical_speed_mps"],
            "horizontal_speed_mps": result["horizontal_speed_mps"],
            "touchdown_tilt_deg": result["max_tilt_deg"],
            "touchdown_angular_rate_radps": result["angular_rate_radps"],
            "horizontal_drift_m": result["horizontal_drift_m"],
            "max_tilt_after_fault_deg": max_tilt_episode,
            "z_min": df["z"].min(),
            "z_max": df["z"].max(),
            "status": "OK",
        })

    out = pd.DataFrame(rows).sort_values(["motor", "eta"], ascending=[True, False])
    out_path = PROJECT_ROOT / "results" / "motorloss_sweep_summary.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)

    print(out.to_string(index=False))
    print(f"\\nSaved {out_path}")


if __name__ == "__main__":
    main()
