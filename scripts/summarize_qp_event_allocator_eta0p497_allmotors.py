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

pat = re.compile(r"qp_event_allocator_m(\d+)_eta0p497_m\d+_eta0p497_rep(\d+)\.csv")

for path in sorted(Path("logs").glob("qp_event_allocator_m*_eta0p497_m*_eta0p497_rep*.csv")):
    m = pat.match(path.name)
    if not m:
        continue

    motor = int(m.group(1))
    rep = int(m.group(2))

    df = pd.read_csv(path)
    row, found = first_contact_row(df)
    vs, hs, tilt, ar, drift, safe = eval_row(row)

    rows.append({
        "controller": "state_aware_qp_event_allocator",
        "motor": motor,
        "eta": 0.497,
        "candidate": str(row.get("selected_candidate", "")),
        "r1": int(row.get("r1", 0)),
        "r2": int(row.get("r2", 0)),
        "r3": int(row.get("r3", 0)),
        "r4": int(row.get("r4", 0)),
        "rep": rep,
        "fault_z": float(row.get("fault_z", 0.0)),
        "fault_vz": float(row.get("fault_vz", 0.0)),
        "qp_score": float(row.get("qp_score", 0.0)),
        "qp_predicted_vz": float(row.get("qp_predicted_vz", 0.0)),
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
    raise SystemExit("[ERROR] No state-aware QP event allocator logs found.")

out = out.sort_values(["motor", "rep"])
out_path = Path("results/tables/qp_event_allocator_eta0p497_allmotors_summary.csv")
out_path.parent.mkdir(parents=True, exist_ok=True)
out.to_csv(out_path, index=False)

print("\n[STATE-AWARE QP EVENT ALLOCATOR ETA=0.497 ALL MOTORS]")
print(out.to_string(index=False))

agg = out.groupby(["controller", "motor", "eta", "candidate", "r1", "r2", "r3", "r4"]).agg(
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
).reset_index().sort_values(["motor", "candidate"])

agg_path = Path("results/tables/qp_event_allocator_eta0p497_allmotors_aggregate.csv")
agg.to_csv(agg_path, index=False)

print("\n[AGGREGATE]")
print(agg.to_string(index=False))

print("\n[OVERALL]")
print(f"safe_count_total: {int(out['safe_touchdown'].sum())}/{len(out)}")

plot_agg = out.groupby(["motor"]).agg(
    mean_vz=("vertical_speed_mps", "mean"),
    std_vz=("vertical_speed_mps", "std"),
    safe_count=("safe_touchdown", "sum"),
).reset_index()

plt.figure()
labels = [f"m{int(r['motor'])}\n{int(r['safe_count'])}/5 safe" for _, r in plot_agg.iterrows()]
plt.bar(range(len(plot_agg)), plot_agg["mean_vz"])
plt.errorbar(range(len(plot_agg)), plot_agg["mean_vz"], yerr=plot_agg["std_vz"].fillna(0), fmt="none", capsize=4)
plt.axhline(0.35, linestyle="--", label="safe limit 0.35 m/s")
plt.xticks(range(len(plot_agg)), labels)
plt.ylabel("Mean first-contact vertical speed [m/s]")
plt.title("State-aware QP event allocator, eta=0.497")
plt.grid(True, axis="y")
plt.legend()

fig_path = Path("results/figures/qp_event_allocator_eta0p497_allmotors.png")
fig_path.parent.mkdir(parents=True, exist_ok=True)
plt.tight_layout()
plt.savefig(fig_path, dpi=200)

print(f"\nSaved table: {out_path}")
print(f"Saved aggregate: {agg_path}")
print(f"Saved plot: {fig_path}")
