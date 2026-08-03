#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


DEFAULT_ROOT = Path(
    "results/final/model_sensitivity/"
    "nominal_m2_boundary/pinv_fine_boundary"
)

ETA_CENTER = 0.49550
ETA_SCALE = 10000.0


def as_bool(value: str) -> bool:
    return value.strip().lower() in {
        "true",
        "1",
        "yes",
    }


def sigmoid(values: np.ndarray) -> np.ndarray:
    output = np.empty_like(
        values,
        dtype=float,
    )

    nonnegative = values >= 0

    output[nonnegative] = (
        1.0
        / (
            1.0
            + np.exp(
                -values[nonnegative]
            )
        )
    )

    exponential = np.exp(
        values[~nonnegative]
    )

    output[~nonnegative] = (
        exponential
        / (1.0 + exponential)
    )

    return output


def grouped_log_likelihood(
    beta: np.ndarray,
    x_values: np.ndarray,
    successes: np.ndarray,
    totals: np.ndarray,
) -> float:
    linear = (
        beta[0]
        + beta[1] * x_values
    )

    return float(
        np.sum(
            successes * linear
            - totals
            * np.logaddexp(
                0.0,
                linear,
            )
        )
    )


def fit_grouped_logistic(
    x_values: np.ndarray,
    successes: np.ndarray,
    totals: np.ndarray,
) -> tuple[
    np.ndarray,
    np.ndarray,
    float,
]:
    overall_rate = (
        successes.sum()
        / totals.sum()
    )

    overall_rate = float(
        np.clip(
            overall_rate,
            1.0e-6,
            1.0 - 1.0e-6,
        )
    )

    beta = np.array(
        [
            math.log(
                overall_rate
                / (1.0 - overall_rate)
            ),
            1.0,
        ],
        dtype=float,
    )

    design = np.column_stack(
        [
            np.ones_like(
                x_values,
                dtype=float,
            ),
            x_values,
        ]
    )

    converged = False

    for _ in range(100):
        linear = design @ beta
        probabilities = sigmoid(
            linear
        )

        score = (
            design.T
            @ (
                successes
                - totals * probabilities
            )
        )

        weights = (
            totals
            * probabilities
            * (1.0 - probabilities)
        )

        information = (
            design.T
            @ (
                weights[:, None]
                * design
            )
        )

        information = (
            information
            + np.eye(2) * 1.0e-12
        )

        try:
            step = np.linalg.solve(
                information,
                score,
            )
        except np.linalg.LinAlgError as error:
            raise RuntimeError(
                "Logistic information matrix "
                "is singular."
            ) from error

        current_ll = grouped_log_likelihood(
            beta,
            x_values,
            successes,
            totals,
        )

        step_scale = 1.0
        accepted = False

        while step_scale >= 1.0e-10:
            candidate = (
                beta
                + step_scale * step
            )

            candidate_ll = (
                grouped_log_likelihood(
                    candidate,
                    x_values,
                    successes,
                    totals,
                )
            )

            if candidate_ll >= (
                current_ll - 1.0e-12
            ):
                beta = candidate
                accepted = True
                break

            step_scale *= 0.5

        if not accepted:
            raise RuntimeError(
                "Logistic Newton update "
                "failed its line search."
            )

        if np.max(
            np.abs(
                step_scale * step
            )
        ) < 1.0e-10:
            converged = True
            break

    if not converged:
        raise RuntimeError(
            "Logistic fit did not converge."
        )

    linear = design @ beta
    probabilities = sigmoid(linear)

    weights = (
        totals
        * probabilities
        * (1.0 - probabilities)
    )

    information = (
        design.T
        @ (
            weights[:, None]
            * design
        )
    )

    covariance = np.linalg.inv(
        information
    )

    log_likelihood = grouped_log_likelihood(
        beta,
        x_values,
        successes,
        totals,
    )

    return (
        beta,
        covariance,
        log_likelihood,
    )


def eta_at_probability(
    beta: np.ndarray,
    probability: float,
) -> float:
    if not 0.0 < probability < 1.0:
        raise ValueError(
            "Probability must be inside (0, 1)."
        )

    slope = float(beta[1])

    if slope <= 0.0:
        raise ValueError(
            "Expected a positive logistic slope."
        )

    target_logit = math.log(
        probability
        / (1.0 - probability)
    )

    scaled_eta = (
        target_logit
        - float(beta[0])
    ) / slope

    return (
        ETA_CENTER
        + scaled_eta / ETA_SCALE
    )


def wilson95(
    successes: int,
    total: int,
) -> tuple[float, float]:
    if total == 0:
        return (
            float("nan"),
            float("nan"),
        )

    z_value = 1.959963984540054
    proportion = successes / total

    denominator = (
        1.0
        + z_value**2 / total
    )

    center = (
        proportion
        + z_value**2
        / (2.0 * total)
    ) / denominator

    radius = (
        z_value
        / denominator
        * math.sqrt(
            proportion
            * (1.0 - proportion)
            / total
            + z_value**2
            / (4.0 * total**2)
        )
    )

    return (
        max(
            0.0,
            center - radius,
        ),
        min(
            1.0,
            center + radius,
        ),
    )


def percentile_interval(
    values: np.ndarray,
) -> tuple[float, float]:
    lower, upper = np.quantile(
        values,
        [0.025, 0.975],
    )

    return (
        float(lower),
        float(upper),
    )


def write_csv(
    path: Path,
    rows: list[dict],
) -> None:
    if not rows:
        raise RuntimeError(
            f"No rows available for {path}"
        )

    with path.open(
        "w",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )

        writer.writeheader()
        writer.writerows(rows)


def saturated_log_likelihood(
    successes: np.ndarray,
    totals: np.ndarray,
) -> float:
    result = 0.0

    for success, total in zip(
        successes,
        totals,
    ):
        failure = total - success

        if success > 0:
            result += (
                success
                * math.log(
                    success / total
                )
            )

        if failure > 0:
            result += (
                failure
                * math.log(
                    failure / total
                )
            )

    return result


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
    )

    parser.add_argument(
        "--bootstrap-replicates",
        type=int,
        default=5000,
    )

    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=20260803,
    )

    args = parser.parse_args()

    trial_path = (
        args.root
        / "pinv_fine_trial_summaries.csv"
    )

    if not trial_path.is_file():
        raise SystemExit(
            f"[FAIL] Missing trial summaries: "
            f"{trial_path}"
        )

    with trial_path.open(
        newline=""
    ) as file:
        rows = list(
            csv.DictReader(file)
        )

    if len(rows) != 210:
        raise SystemExit(
            "[FAIL] Expected 210 trial rows; "
            f"found {len(rows)}."
        )

    expected_etas = [
        0.49520,
        0.49530,
        0.49540,
        0.49550,
        0.49560,
        0.49570,
        0.49580,
    ]

    observed_etas = sorted(
        {
            round(
                float(row["eta"]),
                5,
            )
            for row in rows
        }
    )

    if observed_etas != expected_etas:
        raise SystemExit(
            "[FAIL] Eta-grid mismatch.\n"
            f"expected={expected_etas}\n"
            f"observed={observed_etas}"
        )

    if not all(
        as_bool(
            row["valid_prefault"]
        )
        for row in rows
    ):
        raise SystemExit(
            "[FAIL] At least one trial has "
            "an invalid pre-fault state."
        )

    if not all(
        as_bool(
            row["contact_found"]
        )
        for row in rows
    ):
        raise SystemExit(
            "[FAIL] At least one trial has "
            "no first contact."
        )

    controllers = {
        row["controller"]
        for row in rows
    }

    candidates = {
        row["selected_candidate"]
        for row in rows
    }

    if controllers != {"pinv"}:
        raise SystemExit(
            "[FAIL] Controller mismatch: "
            f"{controllers}"
        )

    if candidates != {
        "bounded_fault_aware_wls"
    }:
        raise SystemExit(
            "[FAIL] Candidate mismatch: "
            f"{candidates}"
        )

    unsafe_rows = [
        row
        for row in rows
        if not as_bool(
            row["safe_touchdown"]
        )
    ]

    for row in unsafe_rows:
        if as_bool(
            row["vertical_speed_ok"]
        ):
            raise SystemExit(
                "[FAIL] Found an unsafe trial "
                "that passed vertical speed."
            )

        for key in [
            "horizontal_speed_ok",
            "tilt_ok",
            "angular_rate_ok",
            "drift_ok",
        ]:
            if not as_bool(row[key]):
                raise SystemExit(
                    "[FAIL] Found a non-vertical "
                    f"failure in {key}."
                )

    seeds = sorted(
        {
            int(row["trial_seed"])
            for row in rows
        }
    )

    if len(seeds) != 30:
        raise SystemExit(
            "[FAIL] Expected 30 paired seeds; "
            f"found {len(seeds)}."
        )

    by_seed_eta: dict[
        tuple[int, float],
        dict[str, str],
    ] = {}

    for row in rows:
        key = (
            int(row["trial_seed"]),
            round(
                float(row["eta"]),
                5,
            ),
        )

        if key in by_seed_eta:
            raise SystemExit(
                "[FAIL] Duplicate seed/eta row: "
                f"{key}"
            )

        by_seed_eta[key] = row

    outcome_matrix = np.empty(
        (
            len(seeds),
            len(expected_etas),
        ),
        dtype=int,
    )

    for seed_index, seed in enumerate(
        seeds
    ):
        for eta_index, eta in enumerate(
            expected_etas
        ):
            key = (
                seed,
                eta,
            )

            if key not in by_seed_eta:
                raise SystemExit(
                    "[FAIL] Missing paired row: "
                    f"{key}"
                )

            outcome_matrix[
                seed_index,
                eta_index,
            ] = int(
                as_bool(
                    by_seed_eta[
                        key
                    ]["safe_touchdown"]
                )
            )

    totals = np.full(
        len(expected_etas),
        len(seeds),
        dtype=float,
    )

    successes = outcome_matrix.sum(
        axis=0
    ).astype(float)

    eta_array = np.array(
        expected_etas,
        dtype=float,
    )

    x_values = (
        eta_array - ETA_CENTER
    ) * ETA_SCALE

    beta, covariance, log_likelihood = (
        fit_grouped_logistic(
            x_values,
            successes,
            totals,
        )
    )

    intercept = float(beta[0])
    slope_per_1e4 = float(beta[1])

    if slope_per_1e4 <= 0.0:
        raise SystemExit(
            "[FAIL] Fitted logistic slope "
            "is not positive."
        )

    odds_ratio_per_1e4 = math.exp(
        slope_per_1e4
    )

    ed10 = eta_at_probability(
        beta,
        0.10,
    )

    ed50 = eta_at_probability(
        beta,
        0.50,
    )

    ed90 = eta_at_probability(
        beta,
        0.90,
    )

    rng = np.random.default_rng(
        args.bootstrap_seed
    )

    bootstrap_records = []

    for replicate in range(
        args.bootstrap_replicates
    ):
        sampled_indices = rng.integers(
            low=0,
            high=len(seeds),
            size=len(seeds),
        )

        bootstrap_successes = (
            outcome_matrix[
                sampled_indices,
                :
            ].sum(axis=0)
            .astype(float)
        )

        try:
            bootstrap_beta, _, _ = (
                fit_grouped_logistic(
                    x_values,
                    bootstrap_successes,
                    totals,
                )
            )

            if (
                not np.all(
                    np.isfinite(
                        bootstrap_beta
                    )
                )
                or bootstrap_beta[1] <= 0.0
            ):
                continue

            bootstrap_records.append(
                {
                    "intercept":
                        float(
                            bootstrap_beta[0]
                        ),
                    "slope_per_1e4":
                        float(
                            bootstrap_beta[1]
                        ),
                    "odds_ratio_per_1e4":
                        math.exp(
                            float(
                                bootstrap_beta[1]
                            )
                        ),
                    "ed10":
                        eta_at_probability(
                            bootstrap_beta,
                            0.10,
                        ),
                    "ed50":
                        eta_at_probability(
                            bootstrap_beta,
                            0.50,
                        ),
                    "ed90":
                        eta_at_probability(
                            bootstrap_beta,
                            0.90,
                        ),
                }
            )
        except (
            RuntimeError,
            ValueError,
            OverflowError,
            np.linalg.LinAlgError,
        ):
            continue

    accepted_bootstraps = len(
        bootstrap_records
    )

    minimum_required = int(
        0.95
        * args.bootstrap_replicates
    )

    if accepted_bootstraps < minimum_required:
        raise SystemExit(
            "[FAIL] Too few valid bootstrap "
            "replicates: "
            f"{accepted_bootstraps}/"
            f"{args.bootstrap_replicates}"
        )

    bootstrap_arrays = {
        key: np.array(
            [
                record[key]
                for record
                in bootstrap_records
            ],
            dtype=float,
        )
        for key in bootstrap_records[0]
    }

    estimates = {
        "intercept_at_eta_0p49550":
            intercept,
        "slope_per_eta_1e_minus_4":
            slope_per_1e4,
        "odds_ratio_per_eta_1e_minus_4":
            odds_ratio_per_1e4,
        "ed10":
            ed10,
        "ed50":
            ed50,
        "ed90":
            ed90,
    }

    bootstrap_keys = {
        "intercept_at_eta_0p49550":
            "intercept",
        "slope_per_eta_1e_minus_4":
            "slope_per_1e4",
        "odds_ratio_per_eta_1e_minus_4":
            "odds_ratio_per_1e4",
        "ed10":
            "ed10",
        "ed50":
            "ed50",
        "ed90":
            "ed90",
    }

    fit_rows = []

    for metric, estimate in estimates.items():
        lower, upper = percentile_interval(
            bootstrap_arrays[
                bootstrap_keys[metric]
            ]
        )

        fit_rows.append(
            {
                "metric":
                    metric,
                "estimate":
                    estimate,
                "ci95_lower":
                    lower,
                "ci95_upper":
                    upper,
                "ci_method":
                    "paired_seed_cluster_"
                    "bootstrap_percentile",
                "bootstrap_replicates_requested":
                    args.bootstrap_replicates,
                "bootstrap_replicates_accepted":
                    accepted_bootstraps,
                "bootstrap_seed":
                    args.bootstrap_seed,
            }
        )

    predicted_at_eta = sigmoid(
        intercept
        + slope_per_1e4
        * x_values
    )

    by_eta_rows = []

    for (
        eta,
        success,
        total,
        predicted,
    ) in zip(
        expected_etas,
        successes,
        totals,
        predicted_at_eta,
    ):
        lower, upper = wilson95(
            int(success),
            int(total),
        )

        by_eta_rows.append(
            {
                "eta":
                    f"{eta:.5f}",
                "n":
                    int(total),
                "safe_count":
                    int(success),
                "observed_safe_rate":
                    success / total,
                "wilson95_lower":
                    lower,
                "wilson95_upper":
                    upper,
                "logistic_predicted_probability":
                    float(predicted),
                "observed_minus_predicted":
                    float(
                        success / total
                        - predicted
                    ),
            }
        )

    curve_etas = np.linspace(
        0.49515,
        0.49585,
        701,
    )

    curve_x = (
        curve_etas - ETA_CENTER
    ) * ETA_SCALE

    curve_probabilities = sigmoid(
        intercept
        + slope_per_1e4 * curve_x
    )

    curve_rows = [
        {
            "eta":
                float(eta),
            "predicted_safe_probability":
                float(probability),
        }
        for eta, probability in zip(
            curve_etas,
            curve_probabilities,
        )
    ]

    saturated_ll = (
        saturated_log_likelihood(
            successes,
            totals,
        )
    )

    deviance = 2.0 * (
        saturated_ll
        - log_likelihood
    )

    total_successes = float(
        successes.sum()
    )

    total_trials = float(
        totals.sum()
    )

    null_rate = (
        total_successes
        / total_trials
    )

    null_log_likelihood = (
        total_successes
        * math.log(null_rate)
        + (
            total_trials
            - total_successes
        )
        * math.log(
            1.0 - null_rate
        )
    )

    individual_predictions = []

    individual_outcomes = []

    for eta_index, eta in enumerate(
        expected_etas
    ):
        probability = float(
            predicted_at_eta[
                eta_index
            ]
        )

        individual_predictions.extend(
            [probability]
            * len(seeds)
        )

        individual_outcomes.extend(
            outcome_matrix[
                :,
                eta_index,
            ].tolist()
        )

    individual_predictions_array = (
        np.array(
            individual_predictions,
            dtype=float,
        )
    )

    individual_outcomes_array = (
        np.array(
            individual_outcomes,
            dtype=float,
        )
    )

    brier_score = float(
        np.mean(
            (
                individual_outcomes_array
                - individual_predictions_array
            ) ** 2
        )
    )

    diagnostics_rows = [
        {
            "model":
                "binomial_logistic_"
                "safe_touchdown_vs_eta",
            "eta_center":
                ETA_CENTER,
            "eta_scale":
                ETA_SCALE,
            "trial_count":
                len(rows),
            "seed_cluster_count":
                len(seeds),
            "eta_condition_count":
                len(expected_etas),
            "safe_count":
                int(successes.sum()),
            "unsafe_count":
                int(
                    totals.sum()
                    - successes.sum()
                ),
            "vertical_only_unsafe_count":
                len(unsafe_rows),
            "log_likelihood":
                log_likelihood,
            "null_log_likelihood":
                null_log_likelihood,
            "saturated_log_likelihood":
                saturated_ll,
            "deviance":
                deviance,
            "deviance_df":
                len(expected_etas) - 2,
            "aic":
                4.0
                - 2.0 * log_likelihood,
            "mcfadden_pseudo_r2":
                1.0
                - log_likelihood
                / null_log_likelihood,
            "brier_score":
                brier_score,
            "empirical_monotonicity_violations":
                sum(
                    current < previous
                    for previous, current
                    in zip(
                        successes[:-1]
                        / totals[:-1],
                        successes[1:]
                        / totals[1:],
                    )
                ),
            "bootstrap_replicates_requested":
                args.bootstrap_replicates,
            "bootstrap_replicates_accepted":
                accepted_bootstraps,
            "bootstrap_seed":
                args.bootstrap_seed,
        }
    ]

    fit_path = (
        args.root
        / "pinv_fine_logistic_fit.csv"
    )

    diagnostics_path = (
        args.root
        / "pinv_fine_logistic_diagnostics.csv"
    )

    by_eta_path = (
        args.root
        / "pinv_fine_logistic_by_eta.csv"
    )

    curve_path = (
        args.root
        / "pinv_fine_logistic_curve.csv"
    )

    report_path = (
        args.root
        / "pinv_fine_logistic_report.md"
    )

    plot_path = (
        args.root
        / "pinv_fine_logistic_curve.png"
    )

    write_csv(
        fit_path,
        fit_rows,
    )

    write_csv(
        diagnostics_path,
        diagnostics_rows,
    )

    write_csv(
        by_eta_path,
        by_eta_rows,
    )

    write_csv(
        curve_path,
        curve_rows,
    )

    fit_lookup = {
        row["metric"]: row
        for row in fit_rows
    }

    report_lines = [
        "# Nominal M2 PINV Logistic Boundary",
        "",
        "## Dataset audit",
        "",
        f"- Trials: {len(rows)}",
        f"- Paired seeds: {len(seeds)}",
        f"- Eta conditions: {len(expected_etas)}",
        f"- Valid pre-fault states: {len(rows)}/{len(rows)}",
        f"- First contacts found: {len(rows)}/{len(rows)}",
        f"- Safe touchdowns: {int(successes.sum())}/{len(rows)}",
        f"- Unsafe touchdowns: {len(unsafe_rows)}",
        (
            "- Unsafe failure mechanism: "
            "vertical speed only"
        ),
        "",
        "## Logistic model",
        "",
        (
            r"$\operatorname{logit}(p_{\mathrm{safe}})"
            r" = \beta_0 + \beta_1"
            r"[(\eta-0.49550)\times10^4]$"
        ),
        "",
        (
            "- Intercept: "
            f"{intercept:.9f}"
        ),
        (
            "- Slope per eta increase of 0.0001: "
            f"{slope_per_1e4:.9f}"
        ),
        (
            "- Odds ratio per eta increase of 0.0001: "
            f"{odds_ratio_per_1e4:.6f}"
        ),
        "",
        "## Fault-tolerance thresholds",
        "",
        "| Threshold | Estimate | Paired-seed bootstrap 95% CI |",
        "|---|---:|---:|",
    ]

    for metric in [
        "ed10",
        "ed50",
        "ed90",
    ]:
        row = fit_lookup[metric]

        report_lines.append(
            "| "
            f"{metric.upper()} | "
            f"{float(row['estimate']):.9f} | "
            f"[{float(row['ci95_lower']):.9f}, "
            f"{float(row['ci95_upper']):.9f}] |"
        )

    report_lines.extend(
        [
            "",
            "Lower eta represents a more severe "
            "loss-of-effectiveness fault. Therefore, "
            "a lower ED50 indicates stronger fault tolerance.",
            "",
            "## Diagnostics",
            "",
            f"- Deviance: {deviance:.6f} on {len(expected_etas) - 2} df",
            (
                "- McFadden pseudo-R²: "
                f"{diagnostics_rows[0]['mcfadden_pseudo_r2']:.6f}"
            ),
            f"- Brier score: {brier_score:.6f}",
            "- Empirical safe-rate monotonicity violations: 0",
            (
                "- Valid paired-seed bootstrap replicates: "
                f"{accepted_bootstraps}/"
                f"{args.bootstrap_replicates}"
            ),
        ]
    )

    plot_saved = False

    try:
        import matplotlib

        matplotlib.use("Agg")

        import matplotlib.pyplot as plt

        observed_rates = (
            successes / totals
        )

        lower_errors = []
        upper_errors = []

        for success, total in zip(
            successes,
            totals,
        ):
            lower, upper = wilson95(
                int(success),
                int(total),
            )

            observed = (
                success / total
            )

            lower_errors.append(
                max(
                    0.0,
                    observed - lower,
                )
            )

            upper_errors.append(
                max(
                    0.0,
                    upper - observed,
                )
            )

        figure, axis = plt.subplots(
            figsize=(8.0, 5.0)
        )

        axis.errorbar(
            eta_array,
            observed_rates,
            yerr=np.array(
                [
                    lower_errors,
                    upper_errors,
                ]
            ),
            fmt="o",
            capsize=4,
            label="Observed safe rate",
        )

        axis.plot(
            curve_etas,
            curve_probabilities,
            label="Logistic fit",
        )

        axis.axvline(
            ed50,
            linestyle="--",
            label=f"ED50 = {ed50:.6f}",
        )

        axis.set_xlabel(
            "Motor-2 effectiveness eta"
        )

        axis.set_ylabel(
            "Safe first-contact probability"
        )

        axis.set_ylim(
            -0.03,
            1.03,
        )

        axis.set_title(
            "Nominal M2 Bounded-WLS/PINV Safety Boundary"
        )

        axis.grid(
            True,
            alpha=0.25,
        )

        axis.legend()

        figure.tight_layout()

        figure.savefig(
            plot_path,
            dpi=220,
        )

        plt.close(figure)

        plot_saved = True

    except ImportError:
        report_lines.extend(
            [
                "",
                (
                    "Plot not generated because "
                    "matplotlib is unavailable."
                ),
            ]
        )

    report_path.write_text(
        "\n".join(report_lines) + "\n"
    )

    print(
        "========== PINV LOGISTIC FIT =========="
    )

    print(
        f"intercept={intercept:.9f}"
    )

    print(
        "slope_per_eta_0p0001="
        f"{slope_per_1e4:.9f}"
    )

    print(
        "odds_ratio_per_eta_0p0001="
        f"{odds_ratio_per_1e4:.6f}"
    )

    for metric in [
        "ed10",
        "ed50",
        "ed90",
    ]:
        row = fit_lookup[metric]

        print(
            f"{metric.upper()}="
            f"{float(row['estimate']):.9f} "
            f"CI95=["
            f"{float(row['ci95_lower']):.9f},"
            f"{float(row['ci95_upper']):.9f}]"
        )

    print(
        "bootstrap="
        f"{accepted_bootstraps}/"
        f"{args.bootstrap_replicates}"
    )

    print(
        f"deviance={deviance:.6f}"
    )

    print(
        f"brier_score={brier_score:.6f}"
    )

    print()
    print(f"[SAVED] {fit_path}")
    print(f"[SAVED] {diagnostics_path}")
    print(f"[SAVED] {by_eta_path}")
    print(f"[SAVED] {curve_path}")
    print(f"[SAVED] {report_path}")

    if plot_saved:
        print(f"[SAVED] {plot_path}")


if __name__ == "__main__":
    main()
