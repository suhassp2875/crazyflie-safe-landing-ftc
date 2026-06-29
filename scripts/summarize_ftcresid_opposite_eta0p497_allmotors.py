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

pat = re.compile(
    r"motorloss_ftcboost_m(\d+)_eta0p497_b0_r(-?\d+)_(-?\d+)_(-?\d+)_(-?\d+)_opposite10000_rep(\d+)\.csv"
)

for path in sorted(Path("logs").glob("motorloss_ftcboost_m*_eta0p497_b0_r*_opposite10000_rep*.csv")):
    m = pat.match(path.name)
    if not m:
        continue

    motor = int(m.group(1))
    r1 = int(m.group(2))
    r2 = int(m.group(3))
    r3 = int(m.group(4))
    r4 = int(m.group(5))
    rep = int(m.group(6))

    df = pd.read_csv(path)
    row, found = first_contact_row(df)
    vs, hs, tilt, ar, drift, safe = eval_row(row)

    rows.append({
        "motor": motor,
        "eta": 0.497,
        "boost": 0,
        "opposite_residual": 10000,
        "r1": r1,
        "r2": r2,
        "r3": r3,
        "r4": r4,
        "rep": rep,
        "vertical_speed_mps": vs,
        "horizontal_speed_mps": hs,
        "max_tilt_deg": tilt,
        "angular_rate_radps": ar,
        "horizontal_drift_m": drift,
        "safe_touchdown": safe,
        "file": path.name,
    })

out = pd.DataFrame(rows)

if out.empty:
    raise SystemExit("[ERROR] No opposite residual logs found.")

out = out.sort_values(["motor", "rep"])

out_path = Path("results/tables/ftcresid_opposite_eta0p497_allmotors_summary.csv")
out_path.parent.mkdir(parents=True, exist_ok=True)
out.to_csv(out_path, index=False)

print("\n[OPPOSITE RESIDUAL ETA=0.497 ALL MOTORS]")
print(out.to_string(index=False))

agg = out.groupby(["motor", "eta", "boost", "opposite_residual", "r1", "r2", "r3", "r4"]).agg(
    n=("rep", "count"),
    mean_vz=("vertical_speed_mps", "mean"),
    std_vz=("vertical_speed_mps", "std"),
    min_vz=("vertical_speed_mps", "min"),
    max_vz=("vertical_speed_mps", "max"),
    mean_hspeed=("horizontal_speed_mps", "mean"),
    max_hspeed=("horizontal_speed_mps", "max"),
    mean_tilt=("max_tilt_deg", "mean"),
    max_tilt=("max_tilt_deg", "max"),
    mean_drift=("horizontal_drift_m", "mean"),
    max_drift=("horizontal_drift_m", "max"),
    safe_count=("safe_touchdown", "sum"),
).reset_index()

agg = agg.sort_values(["motor"])

agg_path = Path("results/tables/ftcresid_opposite_eta0p497_allmotors_aggregate.csv")
agg.to_csv(agg_path, index=False)

print("\n[AGGREGATE]")
print(agg.to_string(index=False))

plt.figure()
labels = [f"m{int(r['motor'])}\n[{int(r['r1'])},{int(r['r2'])},{int(r['r3'])},{int(r['r4'])}]" for _, r in agg.iterrows()]

plt.bar(range(len(agg)), agg["mean_vz"])
plt.errorbar(
    range(len(agg)),
    agg["mean_vz"],
    yerr=agg["std_vz"].fillna(0),
    fmt="none",
    capsize=4,
)
plt.axhline(0.35, linestyle="--", label="safe limit 0.35 m/s")
plt.xticks(range(len(agg)), labels)
plt.ylabel("Mean first-contact vertical speed [m/s]")
plt.title("Opposite-motor residual, eta=0.497, all motors")
plt.grid(True, axis="y")
plt.legend()

fig_path = Path("results/figures/ftcresid_opposite_eta0p497_allmotors.png")
fig_path.parent.mkdir(parents=True, exist_ok=True)
plt.tight_layout()
plt.savefig(fig_path, dpi=200)

print(f"\nSaved table: {out_path}")
print(f"Saved aggregate: {agg_path}")
print(f"Saved plot: {fig_path}")
