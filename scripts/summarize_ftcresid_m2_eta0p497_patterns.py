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

pattern = re.compile(
    r"motorloss_ftcboost_m2_eta0p497_b0_r(-?\d+)_(-?\d+)_(-?\d+)_(-?\d+)_(.+)\.csv"
)

for path in sorted(Path("logs").glob("motorloss_ftcboost_m2_eta0p497_b0_r*_*.csv")):
    m = pattern.match(path.name)
    if not m:
        continue

    r1 = int(m.group(1))
    r2 = int(m.group(2))
    r3 = int(m.group(3))
    r4 = int(m.group(4))
    name = m.group(5)

    df = pd.read_csv(path)
    row, found = first_contact_row(df)
    vs, hs, tilt, ar, drift, safe = eval_row(row)

    rows.append({
        "pattern": name,
        "motor": 2,
        "eta": 0.497,
        "boost": 0,
        "r1": r1,
        "r2": r2,
        "r3": r3,
        "r4": r4,
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
    raise SystemExit("[ERROR] No asymmetric residual logs found.")

out = out.sort_values([
    "safe_touchdown",
    "vertical_speed_mps",
    "horizontal_drift_m",
], ascending=[False, True, True])

out_path = Path("results/tables/ftcresid_m2_eta0p497_patterns_summary.csv")
out_path.parent.mkdir(parents=True, exist_ok=True)
out.to_csv(out_path, index=False)

print("\n[M2 ETA=0.497 ASYMMETRIC RESIDUAL PATTERNS]")
print(out[[
    "pattern",
    "r1",
    "r2",
    "r3",
    "r4",
    "vertical_speed_mps",
    "horizontal_speed_mps",
    "max_tilt_deg",
    "horizontal_drift_m",
    "safe_touchdown",
]].to_string(index=False))

top = out.head(12).copy()

plt.figure()
labels = []
for _, r in top.iterrows():
    labels.append(f"{r['pattern']}\n[{int(r['r1'])},{int(r['r2'])},{int(r['r3'])},{int(r['r4'])}]")

plt.bar(range(len(top)), top["vertical_speed_mps"])
plt.axhline(0.35, linestyle="--", label="safe limit 0.35 m/s")
plt.xticks(range(len(top)), labels, rotation=70, ha="right")
plt.ylabel("First-contact vertical speed [m/s]")
plt.title("Motor 2 eta=0.497 asymmetric residual search")
plt.grid(True, axis="y")
plt.legend()

fig_path = Path("results/figures/ftcresid_m2_eta0p497_patterns.png")
fig_path.parent.mkdir(parents=True, exist_ok=True)
plt.tight_layout()
plt.savefig(fig_path, dpi=200)

print(f"\nSaved table: {out_path}")
print(f"Saved plot:  {fig_path}")
