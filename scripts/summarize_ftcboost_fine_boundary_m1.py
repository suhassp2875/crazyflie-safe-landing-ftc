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

rows = []

for path in sorted(Path("logs").glob("motorloss_ftcboost_m1_eta*_b*_r0_0_0_0.csv")):
    m = re.search(r"m1_eta(\d+)p(\d+)_b(\d+)_r0_0_0_0", path.name)
    if not m:
        continue

    eta = float(f"{m.group(1)}.{m.group(2)}")
    boost = int(m.group(3))

    if eta < 0.489 or eta > 0.501:
        continue
    if boost not in [7000, 10000]:
        continue

    df = pd.read_csv(path)
    row, found = first_contact_row(df)
    vertical_speed, horizontal_speed, max_tilt, angular_rate, drift, safe = eval_row(row)

    rows.append({
        "eta": eta,
        "boost": boost,
        "file": path.name,
        "phase_contact": row.get("phase", ""),
        "z_contact": float(row["z"]),
        "vertical_speed_mps": vertical_speed,
        "horizontal_speed_mps": horizontal_speed,
        "max_tilt_deg": max_tilt,
        "angular_rate_radps": angular_rate,
        "horizontal_drift_m": drift,
        "safe_touchdown": safe,
    })

out = pd.DataFrame(rows).drop_duplicates(
    subset=["eta", "boost"],
    keep="last"
).sort_values(["boost", "eta"])

out_path = Path("results/tables/ftcboost_fine_boundary_m1_summary.csv")
out_path.parent.mkdir(parents=True, exist_ok=True)
out.to_csv(out_path, index=False)

print("\n[FINE FTC BOUNDARY: MOTOR 1]")
print(out[[
    "eta",
    "boost",
    "vertical_speed_mps",
    "horizontal_speed_mps",
    "max_tilt_deg",
    "horizontal_drift_m",
    "safe_touchdown",
    "file",
]].to_string(index=False))

plt.figure()
for boost in sorted(out["boost"].unique()):
    sub = out[out["boost"] == boost].sort_values("eta")
    plt.plot(sub["eta"], sub["vertical_speed_mps"], marker="o", label=f"boost {boost}")

plt.axhline(0.35, linestyle="--", label="safe limit 0.35 m/s")
plt.xlabel("Fault effectiveness eta")
plt.ylabel("First-contact vertical speed [m/s]")
plt.title("Fine recoverability boundary: motor 1 FTC boost")
plt.grid(True)
plt.legend()

fig_path = Path("results/figures/ftcboost_fine_boundary_m1.png")
fig_path.parent.mkdir(parents=True, exist_ok=True)
plt.tight_layout()
plt.savefig(fig_path, dpi=200)

print(f"\nSaved table: {out_path}")
print(f"Saved plot:  {fig_path}")
