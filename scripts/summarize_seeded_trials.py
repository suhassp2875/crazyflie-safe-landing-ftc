#!/usr/bin/env python3

from pathlib import Path
import re
import math

import pandas as pd
import matplotlib.pyplot as plt

GROUND_Z = 0.03

def first_contact_row(df):
    fault_rows = df.loc[df["phase"] == "fault_event", "t"]
    if len(fault_rows) == 0:
        raise ValueError("No fault_event row found")

    fault_t = float(fault_rows.iloc[0])
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

pat = re.compile(r"qp_event_allocator_m(\d+)_eta([0-9p]+)_seeded_smoke_m\d+_eta[0-9p]+_seed(\d+)\.csv")

for path in sorted(Path("logs").glob("qp_event_allocator_m*_eta*_seeded_smoke_m*_eta*_seed*.csv")):
    m = pat.match(path.name)
    if not m:
        continue

    motor = int(m.group(1))
    eta = float(m.group(2).replace("p", "."))
    seed = int(m.group(3))

    df = pd.read_csv(path)

    try:
        row, found = first_contact_row(df)
    except Exception as e:
        print(f"[WARN] Skipping {path.name}: {e}")
        continue

    vs, hs, tilt, ar, drift, safe_raw = eval_row(row)
    safe = bool(found) and bool(safe_raw)

    rows.append({
        "contact_found": bool(found),
        "protocol_id": str(row.get("protocol_id", "")),
        "trial_seed": int(row.get("trial_seed", seed)),
        "motor": motor,
        "eta": eta,
        "controller": "state_aware_qp_lite",
        "allocator_config": str(row.get("allocator_config", "qplite_builtin")),
        "candidate": str(row.get("selected_candidate", "")),
        "r1": int(row.get("r1", 0)),
        "r2": int(row.get("r2", 0)),
        "r3": int(row.get("r3", 0)),
        "r4": int(row.get("r4", 0)),
        "spawn_x_cmd": float(row.get("spawn_x_cmd", 0.0)),
        "spawn_y_cmd": float(row.get("spawn_y_cmd", 0.0)),
        "spawn_yaw_deg_cmd": float(row.get("spawn_yaw_deg_cmd", 0.0)),
        "fault_time_cmd": float(row.get("fault_time_cmd", 10.0)),
        "hover_z_cmd": float(row.get("hover_z_cmd", 0.70)),
        "fault_z": float(row.get("fault_z", 0.0)),
        "fault_vz": float(row.get("fault_vz", 0.0)),
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
    raise SystemExit("[ERROR] No seeded smoke logs found.")

out = out.sort_values(["motor", "eta", "trial_seed"])

out_path = Path("results/tables/seeded_smoke_summary.csv")
out_path.parent.mkdir(parents=True, exist_ok=True)
out.to_csv(out_path, index=False)

agg = out.groupby(["protocol_id", "controller", "motor", "eta", "candidate", "r1", "r2", "r3", "r4"]).agg(
    n=("trial_seed", "count"),
    safe_count=("safe_touchdown", "sum"),
    contact_count=("contact_found", "sum"),
    mean_vz=("vertical_speed_mps", "mean"),
    std_vz=("vertical_speed_mps", "std"),
    min_vz=("vertical_speed_mps", "min"),
    max_vz=("vertical_speed_mps", "max"),
    mean_drift=("horizontal_drift_m", "mean"),
    max_drift=("horizontal_drift_m", "max"),
).reset_index()

agg_path = Path("results/tables/seeded_smoke_aggregate.csv")
agg.to_csv(agg_path, index=False)

print("\n[SEEDED SMOKE SUMMARY]")
print(out.to_string(index=False))

print("\n[AGGREGATE]")
print(agg.to_string(index=False))

print("\n[OVERALL]")
print(f"safe_count_total: {int(out['safe_touchdown'].sum())}/{len(out)}")

plt.figure()
plt.bar(out["trial_seed"].astype(str), out["vertical_speed_mps"])
plt.axhline(0.35, linestyle="--", label="safe limit 0.35 m/s")
plt.xlabel("Trial seed")
plt.ylabel("First-contact vertical speed [m/s]")
plt.title("Seeded smoke test")
plt.grid(True, axis="y")
plt.legend()
plt.tight_layout()

fig_path = Path("results/figures/seeded_smoke_vertical_speed.png")
fig_path.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(fig_path, dpi=200)

print(f"\nSaved summary:   {out_path}")
print(f"Saved aggregate: {agg_path}")
print(f"Saved plot:      {fig_path}")
