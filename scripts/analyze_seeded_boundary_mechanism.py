#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


INPUT = Path(
    "results/final/tables/seeded_boundary_fine_summary.csv"
)

OUT_DIR = Path("results/final/mechanism")
TABLE_DIR = OUT_DIR / "tables"
FIG_DIR = OUT_DIR / "figures"

TARGET_ETA = 0.496


def safe_rate(x):
    return float(np.mean(x.astype(bool)))


def main():
    if not INPUT.exists():
        raise SystemExit(f"[ERROR] Missing input: {INPUT}")

    df = pd.read_csv(INPUT)

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    required = {
        "motor",
        "controller",
        "eta",
        "trial_seed",
        "candidate",
        "r1",
        "r2",
        "r3",
        "r4",
        "vertical_speed_mps",
        "horizontal_speed_mps",
        "max_tilt_deg",
        "angular_rate_radps",
        "horizontal_drift_m",
        "safe_touchdown",
    }

    missing = required - set(df.columns)
    if missing:
        raise SystemExit(
            f"[ERROR] Missing required columns: {sorted(missing)}"
        )

    sub = df[np.isclose(df["eta"], TARGET_ETA)].copy()

    if sub.empty:
        raise SystemExit(
            f"[ERROR] No rows found for eta={TARGET_ETA}"
        )

    sub["safe_touchdown"] = (
        sub["safe_touchdown"]
        .astype(str)
        .str.lower()
        .map({"true": True, "false": False})
        .fillna(sub["safe_touchdown"])
        .astype(bool)
    )

    print(
        f"\n[MECHANISM ANALYSIS AT ETA={TARGET_ETA:.3f}]"
    )

    # ---------------------------------------------------------
    # 1. Controller-level outcome summary
    # ---------------------------------------------------------

    outcome = (
        sub.groupby(["motor", "controller"])
        .agg(
            n=("trial_seed", "count"),
            safe_count=("safe_touchdown", "sum"),
            safe_rate=("safe_touchdown", safe_rate),
            mean_vz=("vertical_speed_mps", "mean"),
            std_vz=("vertical_speed_mps", "std"),
            median_vz=("vertical_speed_mps", "median"),
            min_vz=("vertical_speed_mps", "min"),
            max_vz=("vertical_speed_mps", "max"),
            mean_hspeed=("horizontal_speed_mps", "mean"),
            max_hspeed=("horizontal_speed_mps", "max"),
            mean_tilt=("max_tilt_deg", "mean"),
            max_tilt=("max_tilt_deg", "max"),
            mean_angrate=("angular_rate_radps", "mean"),
            max_angrate=("angular_rate_radps", "max"),
            mean_drift=("horizontal_drift_m", "mean"),
            max_drift=("horizontal_drift_m", "max"),
        )
        .reset_index()
        .sort_values(["motor", "controller"])
    )

    outcome_path = (
        TABLE_DIR /
        "eta0p496_controller_outcomes.csv"
    )
    outcome.to_csv(outcome_path, index=False)

    print("\n[CONTROLLER OUTCOMES]")
    print(outcome.to_string(index=False))

    # ---------------------------------------------------------
    # 2. Candidate-selection breakdown
    # ---------------------------------------------------------

    candidates = (
        sub.groupby(
            [
                "motor",
                "controller",
                "candidate",
                "r1",
                "r2",
                "r3",
                "r4",
            ]
        )
        .agg(
            n=("trial_seed", "count"),
            safe_count=("safe_touchdown", "sum"),
            safe_rate=("safe_touchdown", safe_rate),
            mean_vz=("vertical_speed_mps", "mean"),
            std_vz=("vertical_speed_mps", "std"),
            mean_drift=("horizontal_drift_m", "mean"),
            max_drift=("horizontal_drift_m", "max"),
        )
        .reset_index()
        .sort_values(
            ["motor", "controller", "n", "candidate"],
            ascending=[True, True, False, True],
        )
    )

    candidate_path = (
        TABLE_DIR /
        "eta0p496_candidate_breakdown.csv"
    )
    candidates.to_csv(candidate_path, index=False)

    print("\n[CANDIDATE BREAKDOWN]")
    print(candidates.to_string(index=False))

    # ---------------------------------------------------------
    # 3. Compare QP-lite vs CEM aggregate deltas
    # ---------------------------------------------------------

    wide = outcome.pivot(
        index="motor",
        columns="controller",
        values=[
            "safe_rate",
            "mean_vz",
            "mean_drift",
            "mean_tilt",
            "mean_angrate",
        ],
    )

    delta_rows = []

    for motor in sorted(sub["motor"].unique()):
        try:
            q = outcome[
                (outcome["motor"] == motor)
                & (outcome["controller"] == "qplite")
            ].iloc[0]

            c = outcome[
                (outcome["motor"] == motor)
                & (outcome["controller"] == "cem")
            ].iloc[0]

        except IndexError:
            continue

        delta_rows.append({
            "motor": int(motor),
            "safe_rate_cem_minus_qplite":
                float(c["safe_rate"] - q["safe_rate"]),
            "mean_vz_qplite_minus_cem":
                float(q["mean_vz"] - c["mean_vz"]),
            "mean_drift_qplite_minus_cem":
                float(q["mean_drift"] - c["mean_drift"]),
            "mean_tilt_qplite_minus_cem":
                float(q["mean_tilt"] - c["mean_tilt"]),
            "mean_angrate_qplite_minus_cem":
                float(q["mean_angrate"] - c["mean_angrate"]),
        })

    deltas = pd.DataFrame(delta_rows)

    delta_path = (
        TABLE_DIR /
        "eta0p496_controller_deltas.csv"
    )
    deltas.to_csv(delta_path, index=False)

    print("\n[CONTROLLER DELTAS]")
    print(deltas.to_string(index=False))

    # ---------------------------------------------------------
    # 4. Plot touchdown vertical speed distributions
    # ---------------------------------------------------------

    for motor in sorted(sub["motor"].unique()):
        mdf = sub[sub["motor"] == motor].copy()

        q = (
            mdf[mdf["controller"] == "qplite"]
            ["vertical_speed_mps"]
            .to_numpy()
        )

        c = (
            mdf[mdf["controller"] == "cem"]
            ["vertical_speed_mps"]
            .to_numpy()
        )

        plt.figure(figsize=(8, 5.5))

        positions = [1, 2]
        data = [q, c]

        plt.boxplot(
            data,
            positions=positions,
            tick_labels=["QP-lite", "CEM"],
            showmeans=True,
        )

        plt.axhline(
            0.35,
            linestyle="--",
            label="Vertical-speed safety limit",
        )

        plt.ylabel(
            "First-contact vertical speed [m/s]"
        )

        plt.title(
            f"Near-boundary touchdown speed — "
            f"motor {motor}, eta={TARGET_ETA:.3f}"
        )

        plt.grid(True, axis="y")
        plt.legend()
        plt.tight_layout()

        out_fig = (
            FIG_DIR /
            f"eta0p496_vertical_speed_motor{motor}.png"
        )

        plt.savefig(out_fig, dpi=220)
        plt.close()

        print(f"Saved plot: {out_fig}")

    # ---------------------------------------------------------
    # 5. Plot residual vectors
    # ---------------------------------------------------------

    residual_summary = (
        sub.groupby(["motor", "controller"])
        [["r1", "r2", "r3", "r4"]]
        .mean()
        .reset_index()
    )

    residual_path = (
        TABLE_DIR /
        "eta0p496_mean_residual_vectors.csv"
    )

    residual_summary.to_csv(
        residual_path,
        index=False,
    )

    print("\n[MEAN RESIDUAL VECTORS]")
    print(residual_summary.to_string(index=False))

    for motor in sorted(sub["motor"].unique()):
        mdf = residual_summary[
            residual_summary["motor"] == motor
        ].copy()

        if mdf.empty:
            continue

        labels = ["r1", "r2", "r3", "r4"]
        x = np.arange(len(labels))
        width = 0.35

        qrow = mdf[
            mdf["controller"] == "qplite"
        ]

        crow = mdf[
            mdf["controller"] == "cem"
        ]

        if qrow.empty or crow.empty:
            continue

        qvals = qrow[labels].iloc[0].to_numpy()
        cvals = crow[labels].iloc[0].to_numpy()

        plt.figure(figsize=(8, 5.5))

        plt.bar(
            x - width / 2,
            qvals,
            width,
            label="QP-lite",
        )

        plt.bar(
            x + width / 2,
            cvals,
            width,
            label="CEM",
        )

        plt.xticks(x, labels)
        plt.ylabel("Mean residual command [PWM]")
        plt.title(
            f"Residual allocation at eta={TARGET_ETA:.3f} "
            f"— motor {motor}"
        )

        plt.grid(True, axis="y")
        plt.legend()
        plt.tight_layout()

        out_fig = (
            FIG_DIR /
            f"eta0p496_residual_vector_motor{motor}.png"
        )

        plt.savefig(out_fig, dpi=220)
        plt.close()

        print(f"Saved plot: {out_fig}")

    print("\n[SAVED TABLES]")
    print(outcome_path)
    print(candidate_path)
    print(delta_path)
    print(residual_path)

    print("\n[DONE] Mechanism analysis complete.")


if __name__ == "__main__":
    main()
