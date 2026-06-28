from pathlib import Path
import re
import math

import pandas as pd


GROUND_Z = 0.03

# Same limits we used earlier
MAX_VERTICAL_SPEED = 0.35       # m/s
MAX_HORIZONTAL_SPEED = 0.25     # m/s
MAX_TILT_DEG = 12.0             # deg
MAX_ANGULAR_RATE_RADPS = 1.5    # rad/s
MAX_DRIFT = 0.75                # m


def parse_name(path):
    name = path.name

    motor = None
    eta = None

    m = re.search(r"m(\d+)_eta(\d+)p(\d+)", name)
    if m:
        motor = int(m.group(1))
        eta = float(f"{m.group(2)}.{m.group(3)}")

    if "maxbrake" in name:
        controller = "maxbrake"
    elif "cbf_v6" in name:
        controller = "cbf_v6"
    elif "cbf_v5" in name:
        controller = "cbf_v5"
    elif "cbf_v4" in name:
        controller = "cbf_v4"
    elif "adaptive_v3" in name:
        controller = "adaptive_v3"
    elif "adaptive_v2" in name:
        controller = "adaptive_v2"
    elif "adaptive" in name:
        controller = "adaptive_v1"
    elif "motorloss_m" in name:
        controller = "scripted"
    else:
        controller = "unknown"

    return controller, motor, eta


def first_contact_row(df):
    # Prefer rows after the fault event starts.
    if "phase" in df.columns and (df["phase"] == "fault_event").any():
        fault_t = df.loc[df["phase"] == "fault_event", "t"].iloc[0]
        post = df[df["t"] >= fault_t].copy()
    else:
        post = df.copy()

    contact = post[post["z"] <= GROUND_Z]

    if len(contact) == 0:
        # Fallback: closest-to-ground row after fault
        idx = post["z"].idxmin()
        return post.loc[idx], False

    return contact.iloc[0], True


def compute_touchdown_metrics(row):
    x = float(row["x"])
    y = float(row["y"])
    vx = float(row["vx"])
    vy = float(row["vy"])
    vz = float(row["vz"])
    roll = float(row["roll_deg"])
    pitch = float(row["pitch_deg"])

    gx = float(row.get("gyro_x_deg_s", 0.0))
    gy = float(row.get("gyro_y_deg_s", 0.0))
    gz = float(row.get("gyro_z_deg_s", 0.0))

    vertical_speed = abs(vz)
    horizontal_speed = math.sqrt(vx**2 + vy**2)
    max_tilt = max(abs(roll), abs(pitch))
    horizontal_drift = math.sqrt(x**2 + y**2)

    # Convert deg/s to rad/s
    angular_rate_radps = math.radians(math.sqrt(gx**2 + gy**2 + gz**2))

    checks = {
        "vertical_speed_ok": vertical_speed <= MAX_VERTICAL_SPEED,
        "horizontal_speed_ok": horizontal_speed <= MAX_HORIZONTAL_SPEED,
        "roll_pitch_ok": max_tilt <= MAX_TILT_DEG,
        "angular_rate_ok": angular_rate_radps <= MAX_ANGULAR_RATE_RADPS,
        "drift_ok": horizontal_drift <= MAX_DRIFT,
    }

    safe = all(checks.values())

    return {
        "safe_touchdown": safe,
        "vertical_speed_mps": vertical_speed,
        "horizontal_speed_mps": horizontal_speed,
        "max_tilt_deg": max_tilt,
        "angular_rate_radps": angular_rate_radps,
        "horizontal_drift_m": horizontal_drift,
        **checks,
    }


def main():
    paths = []

    # Current active logs
    paths.extend(Path("logs").glob("*.csv"))

    # Archived logs
    paths.extend(Path("archive").glob("pre_v4_cleanup_*/logs/*.csv"))

    rows = []

    for path in sorted(paths):
        name = path.name

        if not (
            "motorloss" in name
            or "maxbrake" in name
            or "cbf_v" in name
            or "adaptive" in name
        ):
            continue

        try:
            df = pd.read_csv(path)
        except Exception as e:
            print(f"[SKIP] {path}: {e}")
            continue

        required = {"x", "y", "z", "vx", "vy", "vz", "roll_deg", "pitch_deg"}
        if not required.issubset(df.columns):
            continue

        row, found_contact = first_contact_row(df)
        metrics = compute_touchdown_metrics(row)
        controller, motor, eta = parse_name(path)

        rows.append({
            "file": name,
            "controller": controller,
            "motor": motor,
            "eta": eta,
            "phase_at_first_contact": row.get("phase", ""),
            "t_contact": float(row["t"]),
            "z_contact": float(row["z"]),
            "vz_contact": float(row["vz"]),
            "z_cmd": float(row.get("z_cmd", float("nan"))),
            "safe_touchdown": metrics["safe_touchdown"],
            "vertical_speed_mps": metrics["vertical_speed_mps"],
            "horizontal_speed_mps": metrics["horizontal_speed_mps"],
            "max_tilt_deg": metrics["max_tilt_deg"],
            "angular_rate_radps": metrics["angular_rate_radps"],
            "horizontal_drift_m": metrics["horizontal_drift_m"],
            "vertical_speed_ok": metrics["vertical_speed_ok"],
            "horizontal_speed_ok": metrics["horizontal_speed_ok"],
            "roll_pitch_ok": metrics["roll_pitch_ok"],
            "angular_rate_ok": metrics["angular_rate_ok"],
            "drift_ok": metrics["drift_ok"],
            "found_contact": found_contact,
            "path": str(path),
        })

    out = pd.DataFrame(rows)

    if len(out) == 0:
        print("[ERROR] No usable logs found.")
        return

    out = out.sort_values(
        by=["motor", "eta", "controller", "file"],
        ascending=[True, False, True, True],
        na_position="last",
    )

    out_path = Path("results/tables/first_contact_recheck_summary.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)

    focus = out[
        (out["motor"] == 1)
        & (out["eta"].round(2) == 0.50)
    ]

    print("\n[FOCUS: motor 1 eta=0.50]")
    if len(focus):
        print(focus[[
            "controller",
            "file",
            "phase_at_first_contact",
            "t_contact",
            "z_contact",
            "vz_contact",
            "vertical_speed_mps",
            "safe_touchdown",
            "z_cmd",
            "path",
        ]].to_string(index=False))
    else:
        print("No motor 1 eta=0.50 logs found.")

    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
