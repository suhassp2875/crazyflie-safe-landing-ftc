from pathlib import Path
import re

import pandas as pd
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def parse_motor_eta(path: Path):
    m = re.search(r"pwm_m(\d+)_eta(\d+)p(\d+)", path.stem)
    if not m:
        return None, None
    motor = int(m.group(1))
    eta = float(f"{m.group(2)}.{m.group(3)}")
    return motor, eta


def summarize_one(path: Path):
    df = pd.read_csv(path)
    motor, eta = parse_motor_eta(path)

    motor_cols = ["motor_m1", "motor_m2", "motor_m3", "motor_m4"]

    nominal = df[df["phase"] == "nominal_hover"]
    after_fault = df[df["phase"].isin(["fault_event", "emergency_landing", "touchdown_hold"])]

    row = {
        "file": path.name,
        "motor": motor,
        "eta": eta,
        "z_max": df["z"].max(),
        "z_min": df["z"].min(),
    }

    for col in motor_cols:
        row[f"{col}_nominal_mean"] = nominal[col].mean()
        row[f"{col}_after_fault_mean"] = after_fault[col].mean()
        row[f"{col}_after_fault_max"] = after_fault[col].max()
        row[f"{col}_sat_frac_60000"] = (after_fault[col] > 60000).mean()
        row[f"{col}_sat_frac_65000"] = (after_fault[col] > 65000).mean()

    return row


def plot_pwm_trace(path: Path):
    df = pd.read_csv(path)
    motor, eta = parse_motor_eta(path)

    plt.figure()
    for col in ["motor_m1", "motor_m2", "motor_m3", "motor_m4"]:
        plt.plot(df["t"], df[col], label=col)

    fault_rows = df[df["phase"] == "fault_event"]
    if len(fault_rows) > 0:
        fault_t = fault_rows["t"].iloc[0]
        plt.axvline(fault_t, linestyle="--", label="fault event")

    plt.xlabel("Time [s]")
    plt.ylabel("Motor PWM")
    plt.title(f"Motor PWM trace: fault motor {motor}, eta={eta}")
    plt.grid(True)
    plt.legend()
    out = RESULTS_DIR / f"pwm_trace_m{motor}_eta{str(eta).replace('.', 'p')}.png"
    plt.tight_layout()
    plt.savefig(out, dpi=200)
    plt.close()

    return out


def main():
    paths = sorted(LOG_DIR.glob("motorloss_pwm_m*_eta*.csv"))

    rows = []
    plot_paths = []

    for path in paths:
        rows.append(summarize_one(path))
        plot_paths.append(plot_pwm_trace(path))

    out = pd.DataFrame(rows).sort_values(["motor", "eta"], ascending=[True, False])
    out_path = RESULTS_DIR / "pwm_boundary_summary.csv"
    out.to_csv(out_path, index=False)

    print(out[[
        "file",
        "motor",
        "eta",
        "z_max",
        "z_min",
        "motor_m1_after_fault_max",
        "motor_m2_after_fault_max",
        "motor_m3_after_fault_max",
        "motor_m4_after_fault_max",
        "motor_m1_sat_frac_60000",
        "motor_m2_sat_frac_60000",
        "motor_m3_sat_frac_60000",
        "motor_m4_sat_frac_60000",
    ]].to_string(index=False))

    print(f"\nSaved summary: {out_path}")
    print("\nSaved PWM plots:")
    for p in plot_paths:
        print(p)


if __name__ == "__main__":
    main()
