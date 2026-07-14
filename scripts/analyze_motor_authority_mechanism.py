#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


SUMMARY = Path(
    "results/final/tables/seeded_boundary_fine_summary.csv"
)

OUT_DIR = Path("results/final/motor_authority")
TABLE_DIR = OUT_DIR / "tables"
FIG_DIR = OUT_DIR / "figures"

TARGET_ETA = 0.496
TARGET_MOTORS = [1, 4]

# Crazyflie motor command upper range in these SITL logs.
PWM_SAT_THRESHOLD = 65000


def first_fault_index(df: pd.DataFrame):
    rows = df.index[df["phase"] == "fault_event"].tolist()
    return rows[0] if rows else None


def first_contact_index(df: pd.DataFrame, fault_idx: int):
    post = df.loc[fault_idx:]
    rows = post.index[post["z"] <= 0.03].tolist()
    return rows[0] if rows else None


def choose_representative(summary_sub: pd.DataFrame):
    med = summary_sub["vertical_speed_mps"].median()
    idx = (
        summary_sub["vertical_speed_mps"] - med
    ).abs().idxmin()
    return summary_sub.loc[idx]


def main():
    if not SUMMARY.exists():
        raise SystemExit(f"[ERROR] Missing summary: {SUMMARY}")

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    summary = pd.read_csv(SUMMARY)

    selected = []

    for motor in TARGET_MOTORS:
        for controller in ["qplite", "cem"]:
            sub = summary[
                (summary["motor"] == motor)
                & (summary["controller"] == controller)
                & np.isclose(summary["eta"], TARGET_ETA)
            ].copy()

            if sub.empty:
                raise SystemExit(
                    f"[ERROR] No rows for motor={motor}, "
                    f"controller={controller}, eta={TARGET_ETA}"
                )

            selected.append(
                choose_representative(sub)
            )

    metrics_rows = []

    for row in selected:
        motor = int(row["motor"])
        controller = row["controller"]
        filename = row["file"]

        path = Path("logs") / filename

        if not path.exists():
            raise SystemExit(f"[ERROR] Missing raw log: {path}")

        df = pd.read_csv(path)

        fault_idx = first_fault_index(df)
        if fault_idx is None:
            raise RuntimeError(f"No fault_event in {filename}")

        contact_idx = first_contact_index(df, fault_idx)
        if contact_idx is None:
            raise RuntimeError(f"No first contact in {filename}")

        fault_t = float(df.loc[fault_idx, "t"])
        contact_t = float(df.loc[contact_idx, "t"])

        post = df.loc[fault_idx:contact_idx].copy()
        post["tau"] = post["t"] - fault_t

        motor_cols = [
            "motor_m1",
            "motor_m2",
            "motor_m3",
            "motor_m4",
        ]

        max_pwm_series = post[motor_cols].max(axis=1)

        metrics_rows.append({
            "motor": motor,
            "controller": controller,
            "trial_seed": int(row["trial_seed"]),
            "candidate": row["candidate"],
            "r1": int(row["r1"]),
            "r2": int(row["r2"]),
            "r3": int(row["r3"]),
            "r4": int(row["r4"]),
            "file": filename,
            "fault_t": fault_t,
            "contact_t": contact_t,
            "fault_to_contact_s": contact_t - fault_t,
            "touchdown_vertical_speed_mps":
                float(row["vertical_speed_mps"]),
            "max_motor_pwm_postfault":
                float(max_pwm_series.max()),
            "mean_max_motor_pwm_postfault":
                float(max_pwm_series.mean()),
            "fraction_samples_pwm_ge_65000":
                float(np.mean(max_pwm_series >= PWM_SAT_THRESHOLD)),
            "mean_motor_m1":
                float(post["motor_m1"].mean()),
            "mean_motor_m2":
                float(post["motor_m2"].mean()),
            "mean_motor_m3":
                float(post["motor_m3"].mean()),
            "mean_motor_m4":
                float(post["motor_m4"].mean()),
        })

        # Save normalized trajectory for later overlay/debugging.
        traj_out = (
            TABLE_DIR /
            f"m{motor}_{controller}_representative_trajectory.csv"
        )
        post.to_csv(traj_out, index=False)

    metrics = pd.DataFrame(metrics_rows)
    metrics_path = (
        TABLE_DIR /
        "representative_motor_authority_metrics.csv"
    )
    metrics.to_csv(metrics_path, index=False)

    print("\n[REPRESENTATIVE MOTOR-AUTHORITY METRICS]")
    print(metrics.to_string(index=False))

    # ---------------------------------------------------------
    # Per-motor comparison plots
    # ---------------------------------------------------------

    for motor in TARGET_MOTORS:
        traces = {}

        for controller in ["qplite", "cem"]:
            p = (
                TABLE_DIR /
                f"m{motor}_{controller}_representative_trajectory.csv"
            )
            traces[controller] = pd.read_csv(p)

        # Altitude
        plt.figure(figsize=(8, 5.5))
        for controller, df in traces.items():
            plt.plot(
                df["tau"],
                df["z"],
                label=controller,
            )

        plt.axhline(
            0.03,
            linestyle="--",
            label="contact threshold",
        )
        plt.xlabel("Time since fault [s]")
        plt.ylabel("Altitude z [m]")
        plt.title(
            f"Post-fault altitude — motor {motor}, eta={TARGET_ETA}"
        )
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.savefig(
            FIG_DIR / f"motor{motor}_altitude_comparison.png",
            dpi=220,
        )
        plt.close()

        # Vertical speed
        plt.figure(figsize=(8, 5.5))
        for controller, df in traces.items():
            plt.plot(
                df["tau"],
                df["vz"].abs(),
                label=controller,
            )

        plt.axhline(
            0.35,
            linestyle="--",
            label="vertical-speed safety limit",
        )
        plt.xlabel("Time since fault [s]")
        plt.ylabel("|vz| [m/s]")
        plt.title(
            f"Post-fault vertical speed — motor {motor}, eta={TARGET_ETA}"
        )
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.savefig(
            FIG_DIR / f"motor{motor}_vertical_speed_comparison.png",
            dpi=220,
        )
        plt.close()

        # Motor traces: one figure per controller to avoid clutter.
        for controller, df in traces.items():
            plt.figure(figsize=(9, 6))

            for mcol in [
                "motor_m1",
                "motor_m2",
                "motor_m3",
                "motor_m4",
            ]:
                plt.plot(
                    df["tau"],
                    df[mcol],
                    label=mcol,
                )

            plt.axhline(
                PWM_SAT_THRESHOLD,
                linestyle="--",
                label=f"PWM threshold {PWM_SAT_THRESHOLD}",
            )

            plt.xlabel("Time since fault [s]")
            plt.ylabel("Motor PWM")
            plt.title(
                f"Motor PWM after fault — motor {motor}, "
                f"{controller}, eta={TARGET_ETA}"
            )
            plt.grid(True)
            plt.legend()
            plt.tight_layout()

            plt.savefig(
                FIG_DIR /
                f"motor{motor}_{controller}_motor_pwm.png",
                dpi=220,
            )
            plt.close()

        # Max-PWM comparison
        plt.figure(figsize=(8, 5.5))

        for controller, df in traces.items():
            max_pwm = df[
                ["motor_m1", "motor_m2", "motor_m3", "motor_m4"]
            ].max(axis=1)

            plt.plot(
                df["tau"],
                max_pwm,
                label=controller,
            )

        plt.axhline(
            PWM_SAT_THRESHOLD,
            linestyle="--",
            label=f"PWM threshold {PWM_SAT_THRESHOLD}",
        )

        plt.xlabel("Time since fault [s]")
        plt.ylabel("Maximum motor PWM")
        plt.title(
            f"Maximum actuator demand — motor {motor}, eta={TARGET_ETA}"
        )
        plt.grid(True)
        plt.legend()
        plt.tight_layout()

        plt.savefig(
            FIG_DIR / f"motor{motor}_max_pwm_comparison.png",
            dpi=220,
        )
        plt.close()

    print("\n[SAVED]")
    print(metrics_path)
    print(FIG_DIR)
    print("\n[DONE] Motor-authority mechanism analysis complete.")


if __name__ == "__main__":
    main()
