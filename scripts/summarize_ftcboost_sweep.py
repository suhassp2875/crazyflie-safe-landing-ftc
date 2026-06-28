from pathlib import Path
import re
import math

import pandas as pd
import matplotlib.pyplot as plt


GROUND_Z = 0.03
SAFE_VZ = 0.35


def parse_log(path):
    name = path.name
    m = re.search(r"ftcboost_m(\d+)_eta(\d+)p(\d+)_b(\d+)", name)
    if not m:
        return None

    return {
        "motor": int(m.group(1)),
        "eta": float(f"{m.group(2)}.{m.group(3)}"),
        "boost": int(m.group(4)),
    }


def first_contact_row(df):
    if "phase" in df.columns and (df["phase"] == "fault_event").any():
        fault_t = df.loc[df["phase"] == "fault_event", "t"].iloc[0]
        post = df[df["t"] >= fault_t].copy()
    else:
        post = df.copy()

    contact = post[post["z"] <= GROUND_Z]
    if len(contact) > 0:
        return contact.iloc[0], True

    return post.loc[post["z"].idxmin()], False


def eval_row(row):
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
    angular_rate = math.radians(math.sqrt(gx * gx + gy * gy + gz * gz))
    drift = math.sqrt(x * x + y * y)

    safe = (
        vertical_speed <= 0.35
        and horizontal_speed <= 0.25
        and max_tilt <= 12.0
        and angular_rate <= 1.5
        and drift <= 0.75
    )

    return vertical_speed, horizontal_speed, max_tilt, angular_rate, drift, safe


def main():
    rows = []

    for path in sorted(Path("logs").glob("motorloss_ftcboost_m*_eta*_b*.csv")):
        meta = parse_log(path)
        if meta is None:
            continue

        df = pd.read_csv(path)
        row, found_contact = first_contact_row(df)
        vertical_speed, horizontal_speed, max_tilt, angular_rate, drift, safe = eval_row(row)

        rows.append({
            **meta,
            "file": path.name,
            "found_contact": found_contact,
            "phase_contact": row.get("phase", ""),
            "t_contact": float(row["t"]),
            "z_contact": float(row["z"]),
            "vz_contact": float(row["vz"]),
            "vertical_speed_mps": vertical_speed,
            "horizontal_speed_mps": horizontal_speed,
            "max_tilt_deg": max_tilt,
            "angular_rate_radps": angular_rate,
            "horizontal_drift_m": drift,
            "safe_touchdown": safe,
            "motor_m1": float(row.get("motor_m1", float("nan"))),
            "motor_m2": float(row.get("motor_m2", float("nan"))),
            "motor_m3": float(row.get("motor_m3", float("nan"))),
            "motor_m4": float(row.get("motor_m4", float("nan"))),
            "z_cmd": float(row.get("z_cmd", float("nan"))),
        })

    if not rows:
        print("[ERROR] No ftcboost logs found.")
        return

    out = pd.DataFrame(rows).sort_values(["motor", "eta", "boost"])
    out_path = Path("results/tables/ftcboost_sweep_summary.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)

    print("\n[FTCBOOST SWEEP SUMMARY]")
    print(out[[
        "motor",
        "eta",
        "boost",
        "phase_contact",
        "z_contact",
        "vertical_speed_mps",
        "horizontal_speed_mps",
        "max_tilt_deg",
        "horizontal_drift_m",
        "safe_touchdown",
        "file",
    ]].to_string(index=False))

    # Plot vertical speed vs boost
    plt.figure()
    plt.plot(out["boost"], out["vertical_speed_mps"], marker="o")
    plt.axhline(SAFE_VZ, linestyle="--", label="safe limit 0.35 m/s")
    plt.xlabel("Healthy motor PWM boost")
    plt.ylabel("First-contact vertical speed [m/s]")
    plt.title("FTC healthy-motor boost sweep: m1 eta=0.50")
    plt.grid(True)
    plt.legend()
    fig_path = Path("results/figures/ftcboost_m1_eta0p50_vertical_speed_vs_boost.png")
    fig_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(fig_path, dpi=200)

    print(f"\nSaved table: {out_path}")
    print(f"Saved plot:  {fig_path}")


if __name__ == "__main__":
    main()
