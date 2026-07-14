#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


SUMMARY = Path(
    "results/final/tables/seeded_boundary_fine_summary.csv"
)

OUT_DIR = Path("results/final/transient_mechanism")
TABLE_DIR = OUT_DIR / "tables"
FIG_DIR = OUT_DIR / "figures"

TARGET_ETA = 0.496
TARGET_MOTORS = [1, 4]


def first_fault_index(df):
    rows = df.index[df["phase"] == "fault_event"].tolist()
    return rows[0] if rows else None


def first_contact_index(df, fault_idx):
    post = df.loc[fault_idx:]
    rows = post.index[post["z"] <= 0.03].tolist()
    return rows[0] if rows else None


def trapz_integral(y, t):
    y = np.asarray(y, dtype=float)
    t = np.asarray(t, dtype=float)

    if len(y) < 2:
        return np.nan

    return float(np.trapz(y, t))


def main():
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    summary = pd.read_csv(SUMMARY)

    summary = summary[
        summary["motor"].isin(TARGET_MOTORS)
        & np.isclose(summary["eta"], TARGET_ETA)
    ].copy()

    motor_cols = [
        "motor_m1",
        "motor_m2",
        "motor_m3",
        "motor_m4",
    ]

    rows = []

    for _, meta in summary.iterrows():
        path = Path("logs") / meta["file"]

        if not path.exists():
            print(f"[WARN] Missing raw log: {path}")
            continue

        df = pd.read_csv(path)

        fault_idx = first_fault_index(df)
        if fault_idx is None:
            print(f"[WARN] No fault_event: {path.name}")
            continue

        contact_idx = first_contact_index(df, fault_idx)
        if contact_idx is None:
            print(f"[WARN] No contact: {path.name}")
            continue

        post = df.loc[fault_idx:contact_idx].copy()

        fault_t = float(post.iloc[0]["t"])
        contact_t = float(post.iloc[-1]["t"])

        t = post["t"].to_numpy(dtype=float)
        abs_vz = post["vz"].abs().to_numpy(dtype=float)

        max_pwm_series = post[motor_cols].max(axis=1)

        rows.append({
            "motor": int(meta["motor"]),
            "controller": meta["controller"],
            "trial_seed": int(meta["trial_seed"]),
            "candidate": meta["candidate"],
            "file": meta["file"],

            "fault_to_contact_s":
                contact_t - fault_t,

            "touchdown_vertical_speed_mps":
                float(meta["vertical_speed_mps"]),

            "peak_abs_vz_postfault":
                float(np.max(abs_vz)),

            "mean_abs_vz_postfault":
                float(np.mean(abs_vz)),

            "integral_abs_vz_dt":
                trapz_integral(abs_vz, t),

            "max_motor_pwm_postfault":
                float(max_pwm_series.max()),

            "mean_max_motor_pwm_postfault":
                float(max_pwm_series.mean()),

            "mean_motor_m1":
                float(post["motor_m1"].mean()),

            "mean_motor_m2":
                float(post["motor_m2"].mean()),

            "mean_motor_m3":
                float(post["motor_m3"].mean()),

            "mean_motor_m4":
                float(post["motor_m4"].mean()),

            "safe_touchdown":
                bool(meta["safe_touchdown"]),
        })

    trials = pd.DataFrame(rows)

    trials_path = (
        TABLE_DIR /
        "eta0p496_all_trial_transient_metrics.csv"
    )
    trials.to_csv(trials_path, index=False)

    print("\n[ALL-TRIAL TRANSIENT METRICS]")
    print(trials.to_string(index=False))

    aggregate = (
        trials.groupby(["motor", "controller"])
        .agg(
            n=("trial_seed", "count"),
            safe_count=("safe_touchdown", "sum"),

            mean_fault_to_contact_s=
                ("fault_to_contact_s", "mean"),
            std_fault_to_contact_s=
                ("fault_to_contact_s", "std"),

            mean_touchdown_vz=
                ("touchdown_vertical_speed_mps", "mean"),
            std_touchdown_vz=
                ("touchdown_vertical_speed_mps", "std"),

            mean_peak_abs_vz=
                ("peak_abs_vz_postfault", "mean"),
            std_peak_abs_vz=
                ("peak_abs_vz_postfault", "std"),

            mean_abs_vz=
                ("mean_abs_vz_postfault", "mean"),

            mean_integral_abs_vz_dt=
                ("integral_abs_vz_dt", "mean"),

            mean_max_pwm=
                ("mean_max_motor_pwm_postfault", "mean"),
            max_pwm=
                ("max_motor_pwm_postfault", "max"),
        )
        .reset_index()
    )

    aggregate_path = (
        TABLE_DIR /
        "eta0p496_transient_aggregate.csv"
    )
    aggregate.to_csv(aggregate_path, index=False)

    print("\n[AGGREGATE TRANSIENT SUMMARY]")
    print(aggregate.to_string(index=False))

    delta_rows = []

    for motor in TARGET_MOTORS:
        q = aggregate[
            (aggregate["motor"] == motor)
            & (aggregate["controller"] == "qplite")
        ]

        c = aggregate[
            (aggregate["motor"] == motor)
            & (aggregate["controller"] == "cem")
        ]

        if q.empty or c.empty:
            continue

        q = q.iloc[0]
        c = c.iloc[0]

        delta_rows.append({
            "motor": motor,

            "cem_minus_qplite_fault_to_contact_s":
                c["mean_fault_to_contact_s"]
                - q["mean_fault_to_contact_s"],

            "qplite_minus_cem_touchdown_vz":
                q["mean_touchdown_vz"]
                - c["mean_touchdown_vz"],

            "qplite_minus_cem_peak_abs_vz":
                q["mean_peak_abs_vz"]
                - c["mean_peak_abs_vz"],

            "qplite_minus_cem_mean_abs_vz":
                q["mean_abs_vz"]
                - c["mean_abs_vz"],

            "qplite_minus_cem_integral_abs_vz_dt":
                q["mean_integral_abs_vz_dt"]
                - c["mean_integral_abs_vz_dt"],

            "cem_minus_qplite_mean_max_pwm":
                c["mean_max_pwm"]
                - q["mean_max_pwm"],
        })

    deltas = pd.DataFrame(delta_rows)

    delta_path = (
        TABLE_DIR /
        "eta0p496_transient_controller_deltas.csv"
    )
    deltas.to_csv(delta_path, index=False)

    print("\n[TRANSIENT CONTROLLER DELTAS]")
    print(deltas.to_string(index=False))

    # ---------------------------------------------------------
    # Plots
    # ---------------------------------------------------------

    for motor in TARGET_MOTORS:
        mdf = trials[trials["motor"] == motor]

        # Fault-to-contact time
        data = [
            mdf[
                mdf["controller"] == "qplite"
            ]["fault_to_contact_s"],
            mdf[
                mdf["controller"] == "cem"
            ]["fault_to_contact_s"],
        ]

        plt.figure(figsize=(8, 5.5))
        plt.boxplot(
            data,
            tick_labels=["QP-lite", "CEM"],
            showmeans=True,
        )
        plt.ylabel("Fault-to-contact time [s]")
        plt.title(
            f"Fault-to-contact time — motor {motor}, eta={TARGET_ETA}"
        )
        plt.grid(True, axis="y")
        plt.tight_layout()
        plt.savefig(
            FIG_DIR /
            f"motor{motor}_fault_to_contact_distribution.png",
            dpi=220,
        )
        plt.close()

        # Touchdown vertical speed
        data = [
            mdf[
                mdf["controller"] == "qplite"
            ]["touchdown_vertical_speed_mps"],
            mdf[
                mdf["controller"] == "cem"
            ]["touchdown_vertical_speed_mps"],
        ]

        plt.figure(figsize=(8, 5.5))
        plt.boxplot(
            data,
            tick_labels=["QP-lite", "CEM"],
            showmeans=True,
        )
        plt.axhline(
            0.35,
            linestyle="--",
            label="safety limit",
        )
        plt.ylabel(
            "First-contact vertical speed [m/s]"
        )
        plt.title(
            f"Touchdown speed — motor {motor}, eta={TARGET_ETA}"
        )
        plt.grid(True, axis="y")
        plt.legend()
        plt.tight_layout()
        plt.savefig(
            FIG_DIR /
            f"motor{motor}_touchdown_speed_distribution.png",
            dpi=220,
        )
        plt.close()

        # Fault-to-contact time vs touchdown speed
        plt.figure(figsize=(8, 5.5))

        for controller in ["qplite", "cem"]:
            cdf = mdf[
                mdf["controller"] == controller
            ]

            plt.scatter(
                cdf["fault_to_contact_s"],
                cdf["touchdown_vertical_speed_mps"],
                label=controller,
            )

        plt.axhline(
            0.35,
            linestyle="--",
            label="safety limit",
        )

        plt.xlabel("Fault-to-contact time [s]")
        plt.ylabel(
            "First-contact vertical speed [m/s]"
        )
        plt.title(
            f"Recovery time vs touchdown speed — "
            f"motor {motor}, eta={TARGET_ETA}"
        )
        plt.grid(True)
        plt.legend()
        plt.tight_layout()

        plt.savefig(
            FIG_DIR /
            f"motor{motor}_time_vs_touchdown_speed.png",
            dpi=220,
        )
        plt.close()

        # Mean max PWM
        data = [
            mdf[
                mdf["controller"] == "qplite"
            ]["mean_max_motor_pwm_postfault"],
            mdf[
                mdf["controller"] == "cem"
            ]["mean_max_motor_pwm_postfault"],
        ]

        plt.figure(figsize=(8, 5.5))
        plt.boxplot(
            data,
            tick_labels=["QP-lite", "CEM"],
            showmeans=True,
        )
        plt.ylabel("Mean maximum motor PWM")
        plt.title(
            f"Post-fault actuator demand — "
            f"motor {motor}, eta={TARGET_ETA}"
        )
        plt.grid(True, axis="y")
        plt.tight_layout()

        plt.savefig(
            FIG_DIR /
            f"motor{motor}_mean_max_pwm_distribution.png",
            dpi=220,
        )
        plt.close()

    print("\n[SAVED]")
    print(trials_path)
    print(aggregate_path)
    print(delta_path)
    print(FIG_DIR)

    print("\n[DONE] Aggregate transient mechanism analysis complete.")


if __name__ == "__main__":
    main()
