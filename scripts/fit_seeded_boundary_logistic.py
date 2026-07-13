#!/usr/bin/env python3

from pathlib import Path
import math

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from scipy.optimize import minimize
from scipy.special import expit


INPUT = Path("results/final/tables/seeded_boundary_fine_summary.csv")
OUT_TABLE = Path("results/final/tables/seeded_boundary_logistic_fits.csv")
OUT_SHIFT = Path("results/final/tables/seeded_boundary_controller_shifts.csv")
OUT_DIR = Path("results/final/figures")

BOOTSTRAP_REPS = 2000
RNG_SEED = 20260713


def fit_logistic(x, y):
    """
    Fit:
        P(safe) = sigmoid(a + b * eta)

    eta50 = -a / b
    """

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    # Center eta to improve numerical conditioning.
    x0 = float(np.mean(x))
    xc = x - x0

    def nll(theta):
        a, b = theta
        p = expit(a + b * xc)
        eps = 1e-12
        return -np.sum(
            y * np.log(p + eps)
            + (1.0 - y) * np.log(1.0 - p + eps)
        )

    # Positive slope expected: higher eta = less severe fault = safer.
    result = minimize(
        nll,
        x0=np.array([0.0, 1000.0]),
        method="L-BFGS-B",
        bounds=[(-100.0, 100.0), (1e-6, 1e6)],
    )

    if not result.success:
        raise RuntimeError(f"Logistic fit failed: {result.message}")

    a_centered, b = result.x

    # Convert back to original eta coordinates:
    # a_centered + b*(eta-x0) = (a_centered-b*x0) + b*eta
    a = a_centered - b * x0
    eta50 = -a / b

    return {
        "intercept": float(a),
        "slope": float(b),
        "eta50": float(eta50),
        "x_center": x0,
        "opt_success": bool(result.success),
        "nll": float(result.fun),
    }


def predict_prob(eta, intercept, slope):
    eta = np.asarray(eta, dtype=float)
    return expit(intercept + slope * eta)


def bootstrap_eta50(df, n_boot=BOOTSTRAP_REPS, seed=RNG_SEED):
    """
    Stratified bootstrap within eta levels.

    Resamples trials with replacement independently within each eta,
    preserving the eta grid.
    """

    rng = np.random.default_rng(seed)
    eta_levels = sorted(df["eta"].unique())

    estimates = []

    for _ in range(n_boot):
        pieces = []

        for eta in eta_levels:
            sub = df[df["eta"] == eta]
            idx = rng.integers(0, len(sub), size=len(sub))
            pieces.append(sub.iloc[idx])

        boot = pd.concat(pieces, ignore_index=True)

        try:
            fit = fit_logistic(
                boot["eta"].to_numpy(),
                boot["safe_touchdown"].astype(int).to_numpy(),
            )

            eta50 = fit["eta50"]

            # Reject obviously pathological numerical fits.
            if 0.40 < eta50 < 0.60:
                estimates.append(eta50)

        except Exception:
            continue

    if len(estimates) < max(100, n_boot // 4):
        raise RuntimeError(
            f"Too few valid bootstrap fits: {len(estimates)}/{n_boot}"
        )

    estimates = np.asarray(estimates)

    return {
        "bootstrap_n_valid": int(len(estimates)),
        "eta50_ci_low": float(np.percentile(estimates, 2.5)),
        "eta50_ci_high": float(np.percentile(estimates, 97.5)),
        "eta50_boot_median": float(np.median(estimates)),
    }


def main():
    if not INPUT.exists():
        raise SystemExit(f"[ERROR] Missing input: {INPUT}")

    df = pd.read_csv(INPUT)

    required = {
        "controller",
        "motor",
        "eta",
        "trial_seed",
        "safe_touchdown",
    }

    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"[ERROR] Missing columns: {sorted(missing)}")

    df["safe_touchdown"] = df["safe_touchdown"].astype(bool)

    OUT_TABLE.parent.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    fit_rows = []

    print("\n[LOGISTIC BOUNDARY FITS]")

    for motor in sorted(df["motor"].unique()):
        for controller in sorted(df["controller"].unique()):
            sub = df[
                (df["motor"] == motor)
                & (df["controller"] == controller)
            ].copy()

            if sub.empty:
                continue

            fit = fit_logistic(
                sub["eta"].to_numpy(),
                sub["safe_touchdown"].astype(int).to_numpy(),
            )

            boot = bootstrap_eta50(
                sub,
                n_boot=BOOTSTRAP_REPS,
                seed=RNG_SEED + int(motor) * 100
                + (0 if controller == "qplite" else 1),
            )

            row = {
                "motor": int(motor),
                "controller": controller,
                "n_trials": int(len(sub)),
                "eta_min": float(sub["eta"].min()),
                "eta_max": float(sub["eta"].max()),
                "safe_count": int(sub["safe_touchdown"].sum()),
                "intercept": fit["intercept"],
                "slope": fit["slope"],
                "eta50": fit["eta50"],
                "eta50_ci_low": boot["eta50_ci_low"],
                "eta50_ci_high": boot["eta50_ci_high"],
                "eta50_boot_median": boot["eta50_boot_median"],
                "bootstrap_n_valid": boot["bootstrap_n_valid"],
                "nll": fit["nll"],
            }

            fit_rows.append(row)

            print(
                f"motor={motor}, controller={controller}, "
                f"eta50={row['eta50']:.6f}, "
                f"95% CI=[{row['eta50_ci_low']:.6f}, "
                f"{row['eta50_ci_high']:.6f}], "
                f"slope={row['slope']:.2f}"
            )

    fits = pd.DataFrame(fit_rows).sort_values(
        ["motor", "controller"]
    )

    fits.to_csv(OUT_TABLE, index=False)

    print(f"\nSaved fits: {OUT_TABLE}")

    # Controller shift table.
    shift_rows = []

    for motor in sorted(fits["motor"].unique()):
        mfit = fits[fits["motor"] == motor].set_index("controller")

        if "qplite" not in mfit.index or "cem" not in mfit.index:
            continue

        q = mfit.loc["qplite"]
        c = mfit.loc["cem"]

        # Lower eta50 is better because it means recovery at more severe LoE.
        delta = float(q["eta50"] - c["eta50"])

        shift_rows.append({
            "motor": int(motor),
            "qplite_eta50": float(q["eta50"]),
            "cem_eta50": float(c["eta50"]),
            "eta50_improvement_qplite_minus_cem": delta,
            "interpretation": (
                "CEM lower boundary"
                if delta > 0
                else "QP-lite lower boundary"
                if delta < 0
                else "No shift"
            ),
        })

    shifts = pd.DataFrame(shift_rows)

    shifts.to_csv(OUT_SHIFT, index=False)

    print("\n[CONTROLLER BOUNDARY SHIFTS]")
    print(shifts.to_string(index=False))
    print(f"\nSaved shifts: {OUT_SHIFT}")

    # Publication-style per-motor plots.
    eta_grid = np.linspace(
        float(df["eta"].min()) - 0.0003,
        float(df["eta"].max()) + 0.0003,
        500,
    )

    for motor in sorted(df["motor"].unique()):
        plt.figure(figsize=(8, 5.5))

        for controller in ["qplite", "cem"]:
            sub = df[
                (df["motor"] == motor)
                & (df["controller"] == controller)
            ].copy()

            if sub.empty:
                continue

            agg = (
                sub.groupby("eta")
                .agg(
                    n=("trial_seed", "count"),
                    safe_count=("safe_touchdown", "sum"),
                )
                .reset_index()
            )

            agg["safe_rate"] = agg["safe_count"] / agg["n"]

            fit_row = fits[
                (fits["motor"] == motor)
                & (fits["controller"] == controller)
            ].iloc[0]

            probs = predict_prob(
                eta_grid,
                fit_row["intercept"],
                fit_row["slope"],
            )

            plt.scatter(
                agg["eta"],
                agg["safe_rate"],
                label=f"{controller} observed",
            )

            plt.plot(
                eta_grid,
                probs,
                label=(
                    f"{controller} fit "
                    f"(eta50={fit_row['eta50']:.5f})"
                ),
            )

            plt.axvline(
                fit_row["eta50"],
                linestyle="--",
                alpha=0.5,
            )

        plt.axhline(
            0.5,
            linestyle=":",
            label="50% safe probability",
        )

        plt.xlabel("Fault effectiveness eta")
        plt.ylabel("Safe-touchdown probability")
        plt.title(
            f"Seeded recoverability boundary fit — motor {motor}"
        )
        plt.ylim(-0.05, 1.05)
        plt.grid(True)
        plt.legend()
        plt.tight_layout()

        out_fig = OUT_DIR / f"seeded_boundary_logistic_motor{motor}.png"
        plt.savefig(out_fig, dpi=220)
        plt.close()

        print(f"Saved plot: {out_fig}")

    print("\n[DONE] Logistic boundary estimation complete.")


if __name__ == "__main__":
    main()
