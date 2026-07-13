#!/usr/bin/env python3

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

INPUT = Path("results/final/tables/seeded_boundary_fine_summary.csv")
OUT = Path("results/final/tables/seeded_boundary_shift_bootstrap.csv")
BOOTSTRAP_REPS = 5000
RNG_SEED = 20260713


def fit_logistic_eta50(df: pd.DataFrame) -> float:
    x = df["eta"].to_numpy(dtype=float)
    y = df["safe_touchdown"].astype(int).to_numpy(dtype=float)

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

    result = minimize(
        nll,
        x0=np.array([0.0, 1000.0]),
        method="L-BFGS-B",
        bounds=[(-100.0, 100.0), (1e-6, 1e6)],
    )

    if not result.success:
        raise RuntimeError(result.message)

    a_centered, b = result.x
    a = a_centered - b * x0
    eta50 = -a / b

    if not (0.40 < eta50 < 0.60):
        raise RuntimeError(f"Pathological eta50: {eta50}")

    return float(eta50)


def stratified_bootstrap(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    pieces = []

    for eta in sorted(df["eta"].unique()):
        sub = df[df["eta"] == eta]

        idx = rng.integers(
            low=0,
            high=len(sub),
            size=len(sub),
        )

        pieces.append(sub.iloc[idx])

    return pd.concat(pieces, ignore_index=True)


def main():
    if not INPUT.exists():
        raise SystemExit(f"[ERROR] Missing input: {INPUT}")

    df = pd.read_csv(INPUT)
    df["safe_touchdown"] = df["safe_touchdown"].astype(bool)

    rows = []

    print("\n[INDEPENDENT STRATIFIED BOOTSTRAP OF ETA50 SHIFTS]")

    for motor in sorted(df["motor"].unique()):
        q = df[
            (df["motor"] == motor)
            & (df["controller"] == "qplite")
        ].copy()

        c = df[
            (df["motor"] == motor)
            & (df["controller"] == "cem")
        ].copy()

        if q.empty or c.empty:
            continue

        q_eta50 = fit_logistic_eta50(q)
        c_eta50 = fit_logistic_eta50(c)
        observed_delta = q_eta50 - c_eta50

        rng_q = np.random.default_rng(RNG_SEED + motor * 1000 + 1)
        rng_c = np.random.default_rng(RNG_SEED + motor * 1000 + 2)

        deltas = []
        q_boot = []
        c_boot = []

        for _ in range(BOOTSTRAP_REPS):
            try:
                qb = stratified_bootstrap(q, rng_q)
                cb = stratified_bootstrap(c, rng_c)

                q50 = fit_logistic_eta50(qb)
                c50 = fit_logistic_eta50(cb)

                q_boot.append(q50)
                c_boot.append(c50)
                deltas.append(q50 - c50)

            except Exception:
                continue

        if len(deltas) < 1000:
            raise RuntimeError(
                f"Too few valid bootstrap samples for motor {motor}: "
                f"{len(deltas)}/{BOOTSTRAP_REPS}"
            )

        deltas = np.asarray(deltas)
        q_boot = np.asarray(q_boot)
        c_boot = np.asarray(c_boot)

        ci_low = float(np.percentile(deltas, 2.5))
        ci_high = float(np.percentile(deltas, 97.5))

        # Bootstrap probability that CEM has the lower boundary.
        p_cem_better = float(np.mean(deltas > 0.0))

        rows.append({
            "motor": int(motor),
            "bootstrap_method": "independent_stratified_within_eta",
            "bootstrap_reps_requested": BOOTSTRAP_REPS,
            "bootstrap_reps_valid": int(len(deltas)),
            "qplite_eta50": q_eta50,
            "cem_eta50": c_eta50,
            "observed_delta_eta50_qplite_minus_cem": observed_delta,
            "delta_ci_low": ci_low,
            "delta_ci_high": ci_high,
            "bootstrap_probability_cem_lower_boundary": p_cem_better,
            "qplite_eta50_boot_median": float(np.median(q_boot)),
            "cem_eta50_boot_median": float(np.median(c_boot)),
        })

        print(
            f"motor={motor}: "
            f"delta_eta50={observed_delta:.6f}, "
            f"95% CI=[{ci_low:.6f}, {ci_high:.6f}], "
            f"P(CEM lower boundary)={p_cem_better:.4f}"
        )

    out = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)

    print(f"\nSaved: {OUT}")


if __name__ == "__main__":
    main()
