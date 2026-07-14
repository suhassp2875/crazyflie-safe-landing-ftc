#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

INPUT = Path(
    "results/final/transient_mechanism/tables/"
    "eta0p496_all_trial_transient_metrics.csv"
)

OUT = Path(
    "results/final/transient_mechanism/tables/"
    "eta0p496_transient_statistical_tests.csv"
)

METRICS = [
    "fault_to_contact_s",
    "touchdown_vertical_speed_mps",
    "mean_abs_vz_postfault",
    "integral_abs_vz_dt",
    "mean_max_motor_pwm_postfault",
]


def cohens_d(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    nx, ny = len(x), len(y)
    pooled = np.sqrt(
        ((nx - 1) * np.var(x, ddof=1)
         + (ny - 1) * np.var(y, ddof=1))
        / (nx + ny - 2)
    )

    return (np.mean(x) - np.mean(y)) / pooled


def bootstrap_mean_diff(x, y, n_boot=20000, seed=42):
    rng = np.random.default_rng(seed)
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    diffs = np.empty(n_boot)

    for i in range(n_boot):
        xb = rng.choice(x, size=len(x), replace=True)
        yb = rng.choice(y, size=len(y), replace=True)
        diffs[i] = np.mean(xb) - np.mean(yb)

    return (
        float(np.mean(x) - np.mean(y)),
        float(np.percentile(diffs, 2.5)),
        float(np.percentile(diffs, 97.5)),
    )


def main():
    df = pd.read_csv(INPUT)
    rows = []

    for motor in sorted(df["motor"].unique()):
        mdf = df[df["motor"] == motor]

        for metric in METRICS:
            cem = mdf[
                mdf["controller"] == "cem"
            ][metric].dropna().to_numpy()

            qp = mdf[
                mdf["controller"] == "qplite"
            ][metric].dropna().to_numpy()

            welch = stats.ttest_ind(
                cem, qp, equal_var=False
            )

            mann = stats.mannwhitneyu(
                cem, qp, alternative="two-sided"
            )

            diff, ci_low, ci_high = \
                bootstrap_mean_diff(cem, qp)

            rows.append({
                "motor": motor,
                "metric": metric,
                "cem_mean": np.mean(cem),
                "qplite_mean": np.mean(qp),
                "cem_minus_qplite": diff,
                "bootstrap_ci95_low": ci_low,
                "bootstrap_ci95_high": ci_high,
                "welch_t_p": welch.pvalue,
                "mann_whitney_p": mann.pvalue,
                "cohens_d_cem_minus_qplite":
                    cohens_d(cem, qp),
            })

        # Within-controller correlation:
        # longer recovery time vs touchdown speed
        for controller in ["qplite", "cem"]:
            cdf = mdf[
                mdf["controller"] == controller
            ]

            pearson = stats.pearsonr(
                cdf["fault_to_contact_s"],
                cdf["touchdown_vertical_speed_mps"],
            )

            spearman = stats.spearmanr(
                cdf["fault_to_contact_s"],
                cdf["touchdown_vertical_speed_mps"],
            )

            rows.append({
                "motor": motor,
                "metric":
                    f"time_vs_touchdown_correlation_{controller}",
                "cem_mean": np.nan,
                "qplite_mean": np.nan,
                "cem_minus_qplite": np.nan,
                "bootstrap_ci95_low": np.nan,
                "bootstrap_ci95_high": np.nan,
                "welch_t_p": np.nan,
                "mann_whitney_p": np.nan,
                "cohens_d_cem_minus_qplite": np.nan,
                "pearson_r": pearson.statistic,
                "pearson_p": pearson.pvalue,
                "spearman_rho": spearman.statistic,
                "spearman_p": spearman.pvalue,
            })

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)

    print(out.to_string(index=False))
    print(f"\n[SAVED] {OUT}")


if __name__ == "__main__":
    main()
