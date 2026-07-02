#!/usr/bin/env python3

from pathlib import Path
import re
import math

import pandas as pd
import matplotlib.pyplot as plt

GROUND_Z = 0.03

def wilson_ci(k, n, z=1.96):
    if n <= 0:
        return 0.0, 0.0
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt((p * (1 - p) / n) + (z * z / (4 * n * n))) / denom
    return max(0.0, center - half), min(1.0, center + half)

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

pat = re.compile(
    r"qp_event_allocator_m(\d+)_eta([0-9p]+)_seededcoarse_(qplite|cem)_m\d+_eta[0-9p]+_seed(\d+)\.csv"
)

for path in sorted(Path("logs").glob("qp_event_allocator_m*_eta*_seededcoarse_*_m*_eta*_seed*.csv")):
    m = pat.match(path.name)
    if not m:
        continue

    motor = int(m.group(1))
    eta = float(m.group(2).replace("p", "."))
    controller = m.group(3)
    seed = int(m.group(4))

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
        "controller": controller,
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
    raise SystemExit("[ERROR] No seeded coarse logs found.")

out = out.sort_values(["controller", "motor", "eta", "trial_seed"])

out_path = Path("results/tables/seeded_boundary_coarse_summary.csv")
out_path.parent.mkdir(parents=True, exist_ok=True)
out.to_csv(out_path, index=False)

agg = out.groupby(["protocol_id", "controller", "motor", "eta"]).agg(
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

agg["safe_rate"] = agg["safe_count"] / agg["n"]
ci = agg.apply(lambda r: wilson_ci(int(r["safe_count"]), int(r["n"])), axis=1)
agg["safe_rate_ci_low"] = [x[0] for x in ci]
agg["safe_rate_ci_high"] = [x[1] for x in ci]

agg = agg.sort_values(["controller", "motor", "eta"])

agg_path = Path("results/tables/seeded_boundary_coarse_aggregate.csv")
agg.to_csv(agg_path, index=False)

print("\n[SEEDED COARSE BOUNDARY AGGREGATE]")
print(agg.to_string(index=False))

print("\n[OVERALL]")
print(f"safe_count_total: {int(out['safe_touchdown'].sum())}/{len(out)}")
print(f"num_trials: {len(out)}")

# Save one figure per motor.
for motor in sorted(out["motor"].unique()):
    mdf = agg[agg["motor"] == motor].copy()
    if mdf.empty:
        continue

    plt.figure()
    for controller in sorted(mdf["controller"].unique()):
        cdf = mdf[mdf["controller"] == controller].sort_values("eta")

        y = cdf["safe_rate"].to_numpy()
        lo = cdf["safe_rate_ci_low"].to_numpy()
        hi = cdf["safe_rate_ci_high"].to_numpy()

        # Numerical clipping avoids tiny negative error bars when y or CI limits
        # are exactly 0 or 1.
        lower_err = (y - lo).clip(min=0.0)
        upper_err = (hi - y).clip(min=0.0)
        yerr = [lower_err, upper_err]

        plt.errorbar(
            cdf["eta"],
            y,
            yerr=yerr,
            marker="o",
            capsize=4,
            label=controller,
        )

    plt.xlabel("Fault effectiveness eta")
    plt.ylabel("Safe-touchdown probability")
    plt.title(f"Seeded coarse boundary, motor {motor}")
    plt.ylim(-0.05, 1.05)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    fig_path = Path(f"results/figures/seeded_boundary_coarse_motor{motor}.png")
    fig_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(fig_path, dpi=200)
    print(f"Saved plot: {fig_path}")

print(f"\nSaved summary:   {out_path}")
print(f"Saved aggregate: {agg_path}")
