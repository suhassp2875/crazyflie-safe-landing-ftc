from pathlib import Path
import re
import math

import pandas as pd
import matplotlib.pyplot as plt


GROUND_Z = 0.03


def first_contact_row(df):
    if "phase" in df.columns and (df["phase"] == "fault_event").any():
        fault_t = df.loc[df["phase"] == "fault_event", "t"].iloc[0]
        post = df[df["t"] >= fault_t].copy()
    else:
        post = df.copy()

    contact = post[post["z"] <= GROUND_Z]
    if len(contact):
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

    for path in sorted(Path("logs").glob("motorloss_ftcboost_m1_eta0p45_b0_r*.csv")):
        m = re.search(r"_r(-?\d+)_(-?\d+)_(-?\d+)_(-?\d+)", path.name)
        if not m:
            continue

        r1, r2, r3, r4 = [int(m.group(i)) for i in range(1, 5)]

        df = pd.read_csv(path)
        row, found = first_contact_row(df)
        vertical_speed, horizontal_speed, max_tilt, angular_rate, drift, safe = eval_row(row)

        rows.append({
            "file": path.name,
            "r1": r1,
            "r2": r2,
            "r3": r3,
            "r4": r4,
            "found_contact": found,
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
        })

    if not rows:
        print("[ERROR] No residual pattern logs found.")
        return

    out = pd.DataFrame(rows).sort_values("vertical_speed_mps")
    out_path = Path("results/tables/ftcresid_m1_eta0p45_patterns_summary.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)

    print("\n[FTC RESIDUAL PATTERNS: M1 ETA=0.45]")
    print(out[[
        "r1", "r2", "r3", "r4",
        "vertical_speed_mps",
        "horizontal_speed_mps",
        "max_tilt_deg",
        "horizontal_drift_m",
        "safe_touchdown",
        "file",
    ]].to_string(index=False))

    labels = [f"[{r.r1},{r.r2},{r.r3},{r.r4}]" for r in out.itertuples()]
    plt.figure()
    plt.bar(range(len(out)), out["vertical_speed_mps"])
    plt.axhline(0.35, linestyle="--", label="safe limit 0.35 m/s")
    plt.xticks(range(len(out)), labels, rotation=75, ha="right")
    plt.ylabel("First-contact vertical speed [m/s]")
    plt.title("Asymmetric residual patterns: m1 eta=0.45")
    plt.grid(True, axis="y")
    plt.legend()
    fig_path = Path("results/figures/ftcresid_m1_eta0p45_patterns.png")
    fig_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(fig_path, dpi=200)

    print(f"\nSaved table: {out_path}")
    print(f"Saved plot:  {fig_path}")


if __name__ == "__main__":
    main()
