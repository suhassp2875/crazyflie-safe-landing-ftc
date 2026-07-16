#!/usr/bin/env python3

from pathlib import Path
import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logit


INPUT = Path(
    "results/final/tables/"
    "seeded_residual_dose_response.csv"
)

OUT_FITS = Path(
    "results/final/tables/"
    "seeded_residual_dose_logistic_fits.csv"
)

OUT_THRESHOLDS = Path(
    "results/final/tables/"
    "seeded_residual_dose_thresholds.csv"
)

OUT_COMPARISON = Path(
    "results/final/tables/"
    "seeded_residual_dose_motor_comparison.csv"
)

OUT_BOOTSTRAP = Path(
    "results/final/tables/"
    "seeded_residual_dose_bootstrap_samples.csv.gz"
)

OUT_DIR = Path("results/final/figures")

BOOTSTRAP_REPS = 5000
RNG_SEED = 20260716

TARGET_PROBABILITIES = {
    "R10": 0.10,
    "R50": 0.50,
    "R90": 0.90,
}


def parse_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series

    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .map({
            "true": True,
            "false": False,
            "1": True,
            "0": False,
        })
    )


def fit_logistic(residual, safe):
    """
    Fit:

        P(safe) = sigmoid(a + b * residual)

    The residual is centered and scaled to improve numerical conditioning.
    Positive slope is enforced because greater residual authority should not
    reduce the fitted recoverability probability.
    """

    x = np.asarray(residual, dtype=float)
    y = np.asarray(safe, dtype=float)

    x_center = float(np.mean(x))
    x_scale = 1000.0
    xs = (x - x_center) / x_scale

    def nll(theta):
        intercept_scaled, slope_scaled = theta
        p = expit(intercept_scaled + slope_scaled * xs)

        eps = 1e-12

        return -float(np.sum(
            y * np.log(p + eps)
            + (1.0 - y) * np.log(1.0 - p + eps)
        ))

    result = minimize(
        nll,
        x0=np.array([0.0, 1.5]),
        method="L-BFGS-B",
        bounds=[
            (-100.0, 100.0),
            (1e-8, 1000.0),
        ],
    )

    if not result.success:
        raise RuntimeError(
            f"Logistic fit failed: {result.message}"
        )

    intercept_scaled, slope_scaled = result.x

    # Convert:
    # intercept_scaled + slope_scaled * ((R - center)/scale)
    # = intercept + slope * R
    slope = slope_scaled / x_scale
    intercept = (
        intercept_scaled
        - slope_scaled * x_center / x_scale
    )

    return {
        "intercept": float(intercept),
        "slope": float(slope),
        "intercept_scaled": float(intercept_scaled),
        "slope_scaled": float(slope_scaled),
        "residual_center": x_center,
        "residual_scale": x_scale,
        "nll": float(result.fun),
    }


def threshold_for_probability(
    intercept: float,
    slope: float,
    probability: float,
) -> float:
    return float(
        (logit(probability) - intercept) / slope
    )


def predict_probability(
    residual,
    intercept: float,
    slope: float,
):
    return expit(
        intercept + slope * np.asarray(residual, dtype=float)
    )


def bootstrap_motor(
    df: pd.DataFrame,
    motor: int,
    n_boot: int,
    seed: int,
):
    """
    Stratified nonparametric bootstrap.

    Trials are resampled independently within each residual level so that
    every bootstrap replicate retains the original dose grid and sample size.
    """

    rng = np.random.default_rng(seed)
    residual_levels = sorted(df["residual"].unique())

    rows = []

    for boot_id in range(1, n_boot + 1):
        pieces = []

        for residual in residual_levels:
            sub = df[df["residual"] == residual]

            sampled_indices = rng.integers(
                0,
                len(sub),
                size=len(sub),
            )

            pieces.append(
                sub.iloc[sampled_indices]
            )

        boot = pd.concat(
            pieces,
            ignore_index=True,
        )

        try:
            fit = fit_logistic(
                boot["residual"],
                boot["safe_touchdown"].astype(int),
            )

            thresholds = {
                name: threshold_for_probability(
                    fit["intercept"],
                    fit["slope"],
                    probability,
                )
                for name, probability
                in TARGET_PROBABILITIES.items()
            }

            # Reject pathological optimization results.
            if not all(
                5000.0 < value < 20000.0
                for value in thresholds.values()
            ):
                continue

            rows.append({
                "bootstrap_id": boot_id,
                "motor": int(motor),
                "intercept": fit["intercept"],
                "slope": fit["slope"],
                **thresholds,
            })

        except Exception:
            continue

    return pd.DataFrame(rows)


def percentile_interval(values):
    values = np.asarray(values, dtype=float)

    return (
        float(np.percentile(values, 2.5)),
        float(np.percentile(values, 97.5)),
    )


def main():
    if not INPUT.exists():
        raise SystemExit(
            f"[ERROR] Missing input: {INPUT}"
        )

    df = pd.read_csv(INPUT)

    required = {
        "motor",
        "residual",
        "trial_seed",
        "safe_touchdown",
    }

    missing = required - set(df.columns)

    if missing:
        raise SystemExit(
            f"[ERROR] Missing columns: {sorted(missing)}"
        )

    df["safe_touchdown"] = parse_bool(
        df["safe_touchdown"]
    )

    if df["safe_touchdown"].isna().any():
        raise SystemExit(
            "[ERROR] Could not parse safe_touchdown values."
        )

    OUT_FITS.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    OUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    fit_rows = []
    threshold_rows = []
    bootstrap_frames = []

    print("\n[RESIDUAL DOSE-RESPONSE LOGISTIC FITS]")

    for motor in sorted(df["motor"].unique()):
        sub = df[df["motor"] == motor].copy()

        fit = fit_logistic(
            sub["residual"],
            sub["safe_touchdown"].astype(int),
        )

        observed_thresholds = {
            name: threshold_for_probability(
                fit["intercept"],
                fit["slope"],
                probability,
            )
            for name, probability
            in TARGET_PROBABILITIES.items()
        }

        boot = bootstrap_motor(
            sub,
            motor=int(motor),
            n_boot=BOOTSTRAP_REPS,
            seed=RNG_SEED + int(motor) * 100,
        )

        if len(boot) < 1000:
            raise RuntimeError(
                f"Too few valid bootstrap fits for motor {motor}: "
                f"{len(boot)}/{BOOTSTRAP_REPS}"
            )

        bootstrap_frames.append(boot)

        fit_rows.append({
            "motor": int(motor),
            "n_trials": int(len(sub)),
            "residual_min": int(sub["residual"].min()),
            "residual_max": int(sub["residual"].max()),
            "safe_count": int(
                sub["safe_touchdown"].sum()
            ),
            "intercept": fit["intercept"],
            "slope_per_pwm": fit["slope"],
            "slope_per_1000_pwm":
                fit["slope"] * 1000.0,
            "nll": fit["nll"],
            "bootstrap_reps_valid": int(len(boot)),
        })

        for name, probability in TARGET_PROBABILITIES.items():
            ci_low, ci_high = percentile_interval(
                boot[name]
            )

            threshold_rows.append({
                "motor": int(motor),
                "threshold_name": name,
                "target_safe_probability": probability,
                "residual_threshold_pwm":
                    observed_thresholds[name],
                "bootstrap_median_pwm":
                    float(np.median(boot[name])),
                "ci95_low_pwm": ci_low,
                "ci95_high_pwm": ci_high,
                "bootstrap_reps_valid": int(len(boot)),
            })

        print(
            f"motor={motor}: "
            f"R10={observed_thresholds['R10']:.1f}, "
            f"R50={observed_thresholds['R50']:.1f}, "
            f"R90={observed_thresholds['R90']:.1f}, "
            f"slope/1000PWM={fit['slope'] * 1000.0:.4f}"
        )

    fits = pd.DataFrame(fit_rows)
    thresholds = pd.DataFrame(threshold_rows)
    bootstrap = pd.concat(
        bootstrap_frames,
        ignore_index=True,
    )

    fits.to_csv(
        OUT_FITS,
        index=False,
    )

    thresholds.to_csv(
        OUT_THRESHOLDS,
        index=False,
    )

    bootstrap.to_csv(
        OUT_BOOTSTRAP,
        index=False,
        compression="gzip",
    )

    # Independent motor comparison.
    comparison_rows = []

    motors = sorted(bootstrap["motor"].unique())

    if len(motors) == 2:
        motor_a, motor_b = motors

        a = (
            bootstrap[bootstrap["motor"] == motor_a]
            .reset_index(drop=True)
        )
        b = (
            bootstrap[bootstrap["motor"] == motor_b]
            .reset_index(drop=True)
        )

        n = min(len(a), len(b))
        a = a.iloc[:n]
        b = b.iloc[:n]

        for threshold_name in TARGET_PROBABILITIES:
            # Positive value means motor B requires more residual authority.
            difference = (
                b[threshold_name].to_numpy()
                - a[threshold_name].to_numpy()
            )

            observed_a = float(
                thresholds[
                    (thresholds["motor"] == motor_a)
                    & (
                        thresholds["threshold_name"]
                        == threshold_name
                    )
                ]["residual_threshold_pwm"].iloc[0]
            )

            observed_b = float(
                thresholds[
                    (thresholds["motor"] == motor_b)
                    & (
                        thresholds["threshold_name"]
                        == threshold_name
                    )
                ]["residual_threshold_pwm"].iloc[0]
            )

            ci_low, ci_high = percentile_interval(
                difference
            )

            comparison_rows.append({
                "threshold_name": threshold_name,
                "motor_a": int(motor_a),
                "motor_b": int(motor_b),
                "motor_a_threshold_pwm": observed_a,
                "motor_b_threshold_pwm": observed_b,
                "motor_b_minus_motor_a_pwm":
                    observed_b - observed_a,
                "difference_ci95_low_pwm": ci_low,
                "difference_ci95_high_pwm": ci_high,
                "bootstrap_probability_motor_b_requires_more":
                    float(np.mean(difference > 0.0)),
                "bootstrap_reps": int(n),
            })

    comparison = pd.DataFrame(comparison_rows)

    comparison.to_csv(
        OUT_COMPARISON,
        index=False,
    )

    print("\n[RESIDUAL THRESHOLDS]")
    print(
        thresholds.to_string(index=False)
    )

    print("\n[MOTOR COMPARISON]")
    print(
        comparison.to_string(index=False)
    )

    residual_grid = np.linspace(
        float(df["residual"].min()) - 500.0,
        float(df["residual"].max()) + 500.0,
        600,
    )

    for motor in sorted(df["motor"].unique()):
        sub = df[df["motor"] == motor]

        agg = (
            sub.groupby("residual")
            .agg(
                n=("trial_seed", "count"),
                safe_count=("safe_touchdown", "sum"),
            )
            .reset_index()
        )

        agg["safe_rate"] = (
            agg["safe_count"] / agg["n"]
        )

        fit = fits[fits["motor"] == motor].iloc[0]

        predicted = predict_probability(
            residual_grid,
            fit["intercept"],
            fit["slope_per_pwm"],
        )

        motor_thresholds = thresholds[
            thresholds["motor"] == motor
        ]

        plt.figure(figsize=(8.5, 5.8))

        plt.scatter(
            agg["residual"],
            agg["safe_rate"],
            label="Observed safe rate",
            zorder=3,
        )

        plt.plot(
            residual_grid,
            predicted,
            label="Logistic fit",
        )

        for threshold_name, probability in TARGET_PROBABILITIES.items():
            threshold_row = motor_thresholds[
                motor_thresholds["threshold_name"]
                == threshold_name
            ].iloc[0]

            threshold_value = float(
                threshold_row["residual_threshold_pwm"]
            )

            plt.axhline(
                probability,
                linestyle=":",
                alpha=0.45,
            )

            plt.axvline(
                threshold_value,
                linestyle="--",
                alpha=0.55,
                label=(
                    f"{threshold_name}="
                    f"{threshold_value:.0f} PWM"
                ),
            )

        plt.xlabel(
            "Opposite-motor residual [PWM]"
        )
        plt.ylabel(
            "Safe-touchdown probability"
        )
        plt.title(
            f"Residual recoverability curve — motor {motor}, "
            "eta=0.496"
        )
        plt.ylim(-0.05, 1.05)
        plt.grid(True)
        plt.legend()
        plt.tight_layout()

        figure_path = (
            OUT_DIR /
            f"seeded_residual_dose_logistic_motor{motor}.png"
        )

        plt.savefig(
            figure_path,
            dpi=220,
        )
        plt.close()

        print(f"Saved plot: {figure_path}")

    # Threshold comparison plot.
    plt.figure(figsize=(8.5, 5.8))

    x_positions = np.arange(
        len(TARGET_PROBABILITIES)
    )

    width = 0.34

    for index, motor in enumerate(
        sorted(thresholds["motor"].unique())
    ):
        sub = (
            thresholds[thresholds["motor"] == motor]
            .set_index("threshold_name")
            .loc[list(TARGET_PROBABILITIES.keys())]
            .reset_index()
        )

        values = sub[
            "residual_threshold_pwm"
        ].to_numpy()

        lower = (
            values
            - sub["ci95_low_pwm"].to_numpy()
        )

        upper = (
            sub["ci95_high_pwm"].to_numpy()
            - values
        )

        offset = (
            -width / 2
            if index == 0
            else width / 2
        )

        plt.errorbar(
            x_positions + offset,
            values,
            yerr=[lower, upper],
            marker="o",
            linestyle="none",
            capsize=5,
            label=f"Motor {motor}",
        )

    plt.xticks(
        x_positions,
        list(TARGET_PROBABILITIES.keys()),
    )
    plt.ylabel(
        "Required opposite-motor residual [PWM]"
    )
    plt.title(
        "Residual authority required for recoverability"
    )
    plt.grid(True, axis="y")
    plt.legend()
    plt.tight_layout()

    comparison_figure = (
        OUT_DIR /
        "seeded_residual_dose_threshold_comparison.png"
    )

    plt.savefig(
        comparison_figure,
        dpi=220,
    )
    plt.close()

    print(f"Saved plot: {comparison_figure}")

    print("\n[SAVED]")
    print(OUT_FITS)
    print(OUT_THRESHOLDS)
    print(OUT_COMPARISON)
    print(OUT_BOOTSTRAP)

    print(
        "\n[DONE] Residual dose-response logistic "
        "analysis complete."
    )


if __name__ == "__main__":
    main()
