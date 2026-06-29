from pathlib import Path
import re
import math

import pandas as pd
import matplotlib.pyplot as plt

GROUND_Z = 0.03

def first_contact_row(df):
    fault_t = df.loc[df["phase"] == "fault_event", "t"].iloc[0]
    post = df[df["t"] >= fault_t].copy()
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

rows = []

for path in sorted(Path("logs").glob("motorloss_ftcboost_m2_eta0p497_b*_r0_0_0_0_rep*.csv")):
    m = re.search(r"m2_eta0p497_b(\d+)_r0_0_0_0_rep(\d+)", path.name)
    if not m:
        continue

    boost = int(m.group(1))
    rep = int(m.group(2))

    df = pd.read_csv(path)
    row, found = first_contact_row(df)
    vs, hs, tilt, ar, drift, safe = eval_row(row)

    rows.append({
        "motor": 2,
        "eta": 0.497,
        "boost": boost,
        "rep": rep,
        "vertical_speed_mps": vs,
        "horizontal_speed_mps": hs,
        "max_tilt_deg": tilt,
        "angular_rate_radps": ar,
        "horizontal_drift_m": drift,
        "safe_touchdown": safe,
        "file": path.name,
    })

out = pd.DataFrame(rows).sort_values(["boost", "rep"])
out_path = Path("results/tables/m2_eta0p497_boost_repeats_summary.csv")
out_path.parent.mkdir(parents=True, exist_ok=True)
out.to_csv(out_path, index=False)

print("\n[M2 ETA=0.497 BOOST REPEATS]")
print(out.to_string(index=False))

agg = out.groupby(["boost"]).agg(
    n=("rep", "count"),
    mean_vz=("vertical_speed_mps", "mean"),
    std_vz=("vertical_speed_mps", "std"),
    min_vz=("vertical_speed_mps", "min"),
    max_vz=("vertical_speed_mps", "max"),
    mean_drift=("horizontal_drift_m", "mean"),
    safe_count=("safe_touchdown", "sum"),
).reset_index()

agg_path = Path("results/tables/m2_eta0p497_boost_repeats_aggregate.csv")
agg.to_csv(agg_path, index=False)

print("\n[AGGREGATE]")
print(agg.to_string(index=False))

plt.figure()
plt.errorbar(
    agg["boost"],
    agg["mean_vz"],
    yerr=agg["std_vz"].fillna(0),
    marker="o",
    capsize=4,
)
plt.axhline(0.35, linestyle="--", label="safe limit 0.35 m/s")
plt.xlabel("Healthy-motor residual boost [PWM]")
plt.ylabel("Mean first-contact vertical speed [m/s]")
plt.title("Motor 2 limiting case: eta=0.497")
plt.grid(True)
plt.legend()

fig_path = Path("results/figures/m2_eta0p497_boost_repeats.png")
fig_path.parent.mkdir(parents=True, exist_ok=True)
plt.tight_layout()
plt.savefig(fig_path, dpi=200)

print(f"\nSaved table: {out_path}")
print(f"Saved aggregate: {agg_path}")
print(f"Saved plot: {fig_path}")
