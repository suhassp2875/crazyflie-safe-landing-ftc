#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

import numpy as np


DEFAULT_NOMINAL = Path(
    "results/final/model_sensitivity/"
    "nominal_m2_boundary/pinv_fine_boundary/"
    "pinv_fine_trial_summaries.csv"
)

DEFAULT_OFAT = Path(
    "results/final/model_sensitivity/ofat/"
    "pinv_boundary_fine_sweep/"
    "ofat_fine_trial_summaries.csv"
)

DEFAULT_OUTPUT = Path(
    "results/final/model_sensitivity/ofat/"
    "sensitivity_analysis"
)

ETA_SCALE = 1.0e4


def as_bool(value: str) -> bool:
    return value.strip().lower() in {
        "true",
        "1",
        "yes",
    }


def sigmoid(z: np.ndarray) -> np.ndarray:
    z = np.asarray(z, dtype=float)

    out = np.empty_like(z)

    positive = z >= 0.0
    negative = ~positive

    out[positive] = (
        1.0
        / (
            1.0
            + np.exp(-z[positive])
        )
    )

    exp_z = np.exp(z[negative])

    out[negative] = (
        exp_z
        / (
            1.0
            + exp_z
        )
    )

    return out


def penalized_loglik(
    beta: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
) -> float:
    linear = x @ beta
    p = sigmoid(linear)

    eps = 1.0e-15

    p = np.clip(
        p,
        eps,
        1.0 - eps,
    )

    loglik = float(
        np.sum(
            y * np.log(p)
            + (1.0 - y)
            * np.log(1.0 - p)
        )
    )

    w = p * (1.0 - p)

    info = (
        x.T
        @ (
            w[:, None]
            * x
        )
    )

    sign, logdet = np.linalg.slogdet(
        info
    )

    if sign <= 0:
        return -np.inf

    return (
        loglik
        + 0.5 * float(logdet)
    )


def fit_firth_logistic(
    eta: np.ndarray,
    y: np.ndarray,
    *,
    eta_center: float,
    max_iter: int = 200,
    tolerance: float = 1.0e-10,
) -> tuple[
    np.ndarray,
    np.ndarray,
    int,
]:
    eta = np.asarray(
        eta,
        dtype=float,
    )

    y = np.asarray(
        y,
        dtype=float,
    )

    scaled_eta = (
        eta - eta_center
    ) * ETA_SCALE

    x = np.column_stack(
        [
            np.ones_like(
                scaled_eta
            ),
            scaled_eta,
        ]
    )

    beta = np.zeros(
        2,
        dtype=float,
    )

    previous_pll = penalized_loglik(
        beta,
        x,
        y,
    )

    for iteration in range(
        1,
        max_iter + 1,
    ):
        linear = x @ beta
        p = sigmoid(linear)

        p = np.clip(
            p,
            1.0e-12,
            1.0 - 1.0e-12,
        )

        w = p * (1.0 - p)

        info = (
            x.T
            @ (
                w[:, None]
                * x
            )
        )

        try:
            info_inv = np.linalg.inv(
                info
            )
        except np.linalg.LinAlgError:
            info_inv = np.linalg.pinv(
                info
            )

        # Hat diagonal:
        #
        # h_i = w_i x_i' I^{-1} x_i
        hat_diag = (
            w
            * np.einsum(
                "ij,jk,ik->i",
                x,
                info_inv,
                x,
            )
        )

        adjusted_residual = (
            y
            - p
            + hat_diag
            * (
                0.5 - p
            )
        )

        adjusted_score = (
            x.T
            @ adjusted_residual
        )

        try:
            step = np.linalg.solve(
                info,
                adjusted_score,
            )
        except np.linalg.LinAlgError:
            step = (
                np.linalg.pinv(info)
                @ adjusted_score
            )

        candidate = beta + step

        candidate_pll = penalized_loglik(
            candidate,
            x,
            y,
        )

        # Step halving protects against
        # overshooting the penalized optimum.
        halving = 0

        while (
            candidate_pll
            < previous_pll
            and halving < 30
        ):
            step *= 0.5
            candidate = beta + step

            candidate_pll = (
                penalized_loglik(
                    candidate,
                    x,
                    y,
                )
            )

            halving += 1

        beta_change = float(
            np.max(
                np.abs(
                    candidate - beta
                )
            )
        )

        beta = candidate
        previous_pll = candidate_pll

        if beta_change < tolerance:
            break
    else:
        raise RuntimeError(
            "Firth logistic regression "
            "did not converge."
        )

    linear = x @ beta
    p = sigmoid(linear)

    p = np.clip(
        p,
        1.0e-12,
        1.0 - 1.0e-12,
    )

    w = p * (1.0 - p)

    info = (
        x.T
        @ (
            w[:, None]
            * x
        )
    )

    try:
        covariance = np.linalg.inv(
            info
        )
    except np.linalg.LinAlgError:
        covariance = np.linalg.pinv(
            info
        )

    return (
        beta,
        covariance,
        iteration,
    )


def eta_at_probability(
    beta: np.ndarray,
    probability: float,
    eta_center: float,
) -> float:
    if not (
        0.0 < probability < 1.0
    ):
        raise ValueError(
            "Probability must be "
            "strictly between 0 and 1."
        )

    intercept = float(beta[0])
    slope = float(beta[1])

    if slope <= 0.0:
        raise ValueError(
            "Logistic slope must be positive."
        )

    logit = math.log(
        probability
        / (
            1.0 - probability
        )
    )

    scaled_eta = (
        logit - intercept
    ) / slope

    return (
        eta_center
        + scaled_eta / ETA_SCALE
    )


def write_csv(
    path: Path,
    rows: list[dict],
) -> None:
    if not rows:
        raise RuntimeError(
            f"No rows for {path}"
        )

    with path.open(
        "w",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(
                rows[0].keys()
            ),
            lineterminator="\n",
        )

        writer.writeheader()
        writer.writerows(rows)


def read_rows(
    path: Path,
) -> list[dict]:
    if not path.is_file():
        raise SystemExit(
            f"[FAIL] Missing input: {path}"
        )

    with path.open(
        newline=""
    ) as file:
        return list(
            csv.DictReader(file)
        )


def validate_common_trial_fields(
    rows: list[dict],
    label: str,
) -> None:
    required = {
        "eta",
        "trial_seed",
        "safe_touchdown",
        "valid_prefault",
        "contact_found",
    }

    missing = (
        required
        - set(rows[0].keys())
    )

    if missing:
        raise SystemExit(
            f"[FAIL] {label} missing "
            f"columns: {sorted(missing)}"
        )

    for row in rows:
        if not as_bool(
            row["valid_prefault"]
        ):
            raise SystemExit(
                f"[FAIL] {label} contains "
                "invalid pre-fault trial."
            )

        if not as_bool(
            row["contact_found"]
        ):
            raise SystemExit(
                f"[FAIL] {label} contains "
                "trial without contact."
            )


def make_seed_matrix(
    rows: list[dict],
) -> tuple[
    list[int],
    np.ndarray,
    np.ndarray,
]:
    seeds = sorted(
        {
            int(row["trial_seed"])
            for row in rows
        }
    )

    etas = np.array(
        sorted(
            {
                float(row["eta"])
                for row in rows
            }
        ),
        dtype=float,
    )

    lookup = {}

    for row in rows:
        key = (
            int(row["trial_seed"]),
            float(row["eta"]),
        )

        if key in lookup:
            raise SystemExit(
                f"[FAIL] Duplicate trial "
                f"key: {key}"
            )

        lookup[key] = (
            1.0
            if as_bool(
                row["safe_touchdown"]
            )
            else 0.0
        )

    matrix = np.empty(
        (
            len(seeds),
            len(etas),
        ),
        dtype=float,
    )

    for seed_index, seed in enumerate(
        seeds
    ):
        for eta_index, eta in enumerate(
            etas
        ):
            key = (
                seed,
                float(eta),
            )

            if key not in lookup:
                raise SystemExit(
                    "[FAIL] Missing seed/eta "
                    f"trial: {key}"
                )

            matrix[
                seed_index,
                eta_index,
            ] = lookup[key]

    return (
        seeds,
        etas,
        matrix,
    )


def flatten_seed_matrix(
    etas: np.ndarray,
    matrix: np.ndarray,
) -> tuple[
    np.ndarray,
    np.ndarray,
]:
    n_seeds = matrix.shape[0]

    eta_vector = np.tile(
        etas,
        n_seeds,
    )

    safety_vector = (
        matrix.reshape(-1)
    )

    return (
        eta_vector,
        safety_vector,
    )


def bootstrap_matrix(
    matrix: np.ndarray,
    indices: np.ndarray,
) -> np.ndarray:
    return matrix[
        indices,
        :,
    ]


def percentile_ci(
    values: list[float],
) -> tuple[float, float]:
    array = np.asarray(
        values,
        dtype=float,
    )

    return (
        float(
            np.percentile(
                array,
                2.5,
            )
        ),
        float(
            np.percentile(
                array,
                97.5,
            )
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--nominal",
        type=Path,
        default=DEFAULT_NOMINAL,
    )

    parser.add_argument(
        "--ofat",
        type=Path,
        default=DEFAULT_OFAT,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    parser.add_argument(
        "--bootstrap",
        type=int,
        default=5000,
    )

    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=20260817,
    )

    args = parser.parse_args()

    if args.bootstrap <= 0:
        raise SystemExit(
            "[FAIL] bootstrap must be > 0."
        )

    args.output.mkdir(
        parents=True,
        exist_ok=True,
    )

    nominal_rows = read_rows(
        args.nominal
    )

    ofat_rows = read_rows(
        args.ofat
    )

    if len(nominal_rows) != 210:
        raise SystemExit(
            "[FAIL] Expected 210 nominal "
            f"trials; found {len(nominal_rows)}."
        )

    if len(ofat_rows) != 2100:
        raise SystemExit(
            "[FAIL] Expected 2100 OFAT "
            f"trials; found {len(ofat_rows)}."
        )

    validate_common_trial_fields(
        nominal_rows,
        "nominal",
    )

    validate_common_trial_fields(
        ofat_rows,
        "OFAT",
    )

    if "condition_id" not in ofat_rows[0]:
        raise SystemExit(
            "[FAIL] OFAT rows missing "
            "condition_id."
        )

    nominal_seeds, nominal_etas, nominal_matrix = (
        make_seed_matrix(
            nominal_rows
        )
    )

    if len(nominal_seeds) != 30:
        raise SystemExit(
            "[FAIL] Expected 30 nominal seeds."
        )

    if len(nominal_etas) != 7:
        raise SystemExit(
            "[FAIL] Expected 7 nominal etas."
        )

    condition_order = []

    grouped_ofat = defaultdict(list)

    for row in ofat_rows:
        condition_id = row[
            "condition_id"
        ]

        grouped_ofat[
            condition_id
        ].append(row)

        if condition_id not in condition_order:
            condition_order.append(
                condition_id
            )

    if len(condition_order) != 10:
        raise SystemExit(
            "[FAIL] Expected 10 OFAT "
            f"conditions; found "
            f"{len(condition_order)}."
        )

    metadata_path = (
        args.ofat.parent
        / "ofat_fine_condition_summary.csv"
    )

    metadata_rows = read_rows(
        metadata_path
    )

    if len(metadata_rows) != 10:
        raise SystemExit(
            "[FAIL] Expected 10 OFAT metadata "
            f"rows; found {len(metadata_rows)}."
        )

    required_metadata = {
        "condition_id",
        "parameter",
        "factor",
    }

    missing_metadata = (
        required_metadata
        - set(metadata_rows[0].keys())
    )

    if missing_metadata:
        raise SystemExit(
            "[FAIL] OFAT metadata table missing "
            f"columns: {sorted(missing_metadata)}"
        )

    condition_metadata = {}

    for row in metadata_rows:
        condition_id = row[
            "condition_id"
        ]

        if condition_id in condition_metadata:
            raise SystemExit(
                "[FAIL] Duplicate OFAT metadata "
                f"condition: {condition_id}"
            )

        condition_metadata[
            condition_id
        ] = {
            "parameter":
                row["parameter"],
            "factor":
                float(row["factor"]),
        }

    if set(condition_metadata) != set(
        condition_order
    ):
        raise SystemExit(
            "[FAIL] OFAT trial conditions and "
            "metadata conditions do not match."
        )

    condition_data = {}

    reference_ofat_seeds = None

    for condition_id in condition_order:
        rows = grouped_ofat[
            condition_id
        ]

        if len(rows) != 210:
            raise SystemExit(
                "[FAIL] Expected 210 rows for "
                f"{condition_id}; "
                f"found {len(rows)}."
            )

        seeds, etas, matrix = (
            make_seed_matrix(rows)
        )

        if len(seeds) != 30:
            raise SystemExit(
                "[FAIL] Expected 30 seeds for "
                f"{condition_id}."
            )

        if len(etas) != 7:
            raise SystemExit(
                "[FAIL] Expected 7 etas for "
                f"{condition_id}."
            )

        if reference_ofat_seeds is None:
            reference_ofat_seeds = seeds
        elif seeds != reference_ofat_seeds:
            raise SystemExit(
                "[FAIL] OFAT seed sets "
                "differ across conditions."
            )

        condition_data[
            condition_id
        ] = {
            "rows": rows,
            "seeds": seeds,
            "etas": etas,
            "matrix": matrix,
        }

    # ========================================================
    # Point estimates
    # ========================================================

    point_rows = []

    fits = {}

    all_datasets = [
        (
            "nominal",
            None,
            None,
            nominal_etas,
            nominal_matrix,
        )
    ]

    for condition_id in condition_order:
        metadata = condition_metadata[
            condition_id
        ]

        all_datasets.append(
            (
                condition_id,
                metadata["parameter"],
                metadata["factor"],
                condition_data[
                    condition_id
                ]["etas"],
                condition_data[
                    condition_id
                ]["matrix"],
            )
        )

    for (
        label,
        parameter,
        factor,
        etas,
        matrix,
    ) in all_datasets:
        eta_vector, safety_vector = (
            flatten_seed_matrix(
                etas,
                matrix,
            )
        )

        eta_center = float(
            np.mean(etas)
        )

        beta, covariance, iterations = (
            fit_firth_logistic(
                eta_vector,
                safety_vector,
                eta_center=eta_center,
            )
        )

        if beta[1] <= 0.0:
            raise SystemExit(
                "[FAIL] Non-positive fitted "
                f"slope for {label}: "
                f"{beta[1]}"
            )

        ed10 = eta_at_probability(
            beta,
            0.10,
            eta_center,
        )

        ed50 = eta_at_probability(
            beta,
            0.50,
            eta_center,
        )

        ed90 = eta_at_probability(
            beta,
            0.90,
            eta_center,
        )

        fits[label] = {
            "beta": beta,
            "covariance": covariance,
            "eta_center": eta_center,
            "ed10": ed10,
            "ed50": ed50,
            "ed90": ed90,
            "iterations": iterations,
        }

        point_rows.append(
            {
                "condition_id":
                    label,
                "parameter":
                    (
                        parameter
                        if parameter is not None
                        else "nominal"
                    ),
                "factor":
                    (
                        factor
                        if factor is not None
                        else 1.0
                    ),
                "n_trials":
                    int(
                        matrix.size
                    ),
                "n_seeds":
                    int(
                        matrix.shape[0]
                    ),
                "n_eta":
                    int(
                        matrix.shape[1]
                    ),
                "safe_count":
                    int(
                        matrix.sum()
                    ),
                "eta_min":
                    float(
                        np.min(etas)
                    ),
                "eta_max":
                    float(
                        np.max(etas)
                    ),
                "eta_center":
                    eta_center,
                "intercept":
                    float(beta[0]),
                "slope_per_eta_0p0001":
                    float(beta[1]),
                "odds_ratio_per_eta_0p0001":
                    float(
                        np.exp(beta[1])
                    ),
                "ed10":
                    ed10,
                "ed50":
                    ed50,
                "ed90":
                    ed90,
                "firth_iterations":
                    iterations,
            }
        )

    nominal_ed50 = fits[
        "nominal"
    ]["ed50"]

    # ========================================================
    # Cluster bootstrap
    #
    # One common OFAT resample is used across all 10
    # conditions, preserving their paired-seed design.
    #
    # Nominal uses an independent resample because its seeds
    # are a distinct experimental realization.
    # ========================================================

    rng = np.random.default_rng(
        args.bootstrap_seed
    )

    bootstrap_values = {
        label: {
            "ed10": [],
            "ed50": [],
            "ed90": [],
            "slope": [],
        }
        for label, *_ in all_datasets
    }

    delta_bootstrap = {
        condition_id: []
        for condition_id
        in condition_order
    }

    accepted = 0
    attempted = 0

    max_attempts = (
        args.bootstrap * 4
    )

    while (
        accepted < args.bootstrap
        and attempted < max_attempts
    ):
        attempted += 1

        nominal_indices = rng.integers(
            low=0,
            high=30,
            size=30,
        )

        ofat_indices = rng.integers(
            low=0,
            high=30,
            size=30,
        )

        replicate = {}

        try:
            # Nominal
            matrix = bootstrap_matrix(
                nominal_matrix,
                nominal_indices,
            )

            eta_vector, safety_vector = (
                flatten_seed_matrix(
                    nominal_etas,
                    matrix,
                )
            )

            eta_center = fits[
                "nominal"
            ]["eta_center"]

            beta, _, _ = (
                fit_firth_logistic(
                    eta_vector,
                    safety_vector,
                    eta_center=eta_center,
                )
            )

            if beta[1] <= 0.0:
                continue

            replicate[
                "nominal"
            ] = {
                "ed10":
                    eta_at_probability(
                        beta,
                        0.10,
                        eta_center,
                    ),
                "ed50":
                    eta_at_probability(
                        beta,
                        0.50,
                        eta_center,
                    ),
                "ed90":
                    eta_at_probability(
                        beta,
                        0.90,
                        eta_center,
                    ),
                "slope":
                    float(beta[1]),
            }

            # All OFAT conditions use the same
            # cluster resample.
            for condition_id in condition_order:
                data = condition_data[
                    condition_id
                ]

                matrix = bootstrap_matrix(
                    data["matrix"],
                    ofat_indices,
                )

                eta_vector, safety_vector = (
                    flatten_seed_matrix(
                        data["etas"],
                        matrix,
                    )
                )

                eta_center = fits[
                    condition_id
                ]["eta_center"]

                beta, _, _ = (
                    fit_firth_logistic(
                        eta_vector,
                        safety_vector,
                        eta_center=eta_center,
                    )
                )

                if beta[1] <= 0.0:
                    raise ValueError(
                        "non-positive slope"
                    )

                replicate[
                    condition_id
                ] = {
                    "ed10":
                        eta_at_probability(
                            beta,
                            0.10,
                            eta_center,
                        ),
                    "ed50":
                        eta_at_probability(
                            beta,
                            0.50,
                            eta_center,
                        ),
                    "ed90":
                        eta_at_probability(
                            beta,
                            0.90,
                            eta_center,
                        ),
                    "slope":
                        float(beta[1]),
                }

        except (
            RuntimeError,
            ValueError,
            np.linalg.LinAlgError,
        ):
            continue

        accepted += 1

        nominal_boot_ed50 = (
            replicate[
                "nominal"
            ]["ed50"]
        )

        for label in bootstrap_values:
            for metric in (
                "ed10",
                "ed50",
                "ed90",
                "slope",
            ):
                bootstrap_values[
                    label
                ][metric].append(
                    replicate[
                        label
                    ][metric]
                )

        for condition_id in condition_order:
            delta_bootstrap[
                condition_id
            ].append(
                replicate[
                    condition_id
                ]["ed50"]
                - nominal_boot_ed50
            )

    if accepted != args.bootstrap:
        raise SystemExit(
            "[FAIL] Could not obtain requested "
            f"bootstrap replicates: "
            f"accepted={accepted}, "
            f"attempted={attempted}."
        )

    # ========================================================
    # Final fit table with bootstrap CIs
    # ========================================================

    final_fit_rows = []

    for row in point_rows:
        label = row[
            "condition_id"
        ]

        ed10_low, ed10_high = (
            percentile_ci(
                bootstrap_values[
                    label
                ]["ed10"]
            )
        )

        ed50_low, ed50_high = (
            percentile_ci(
                bootstrap_values[
                    label
                ]["ed50"]
            )
        )

        ed90_low, ed90_high = (
            percentile_ci(
                bootstrap_values[
                    label
                ]["ed90"]
            )
        )

        slope_low, slope_high = (
            percentile_ci(
                bootstrap_values[
                    label
                ]["slope"]
            )
        )

        final_fit_rows.append(
            {
                **row,
                "slope_ci95_low":
                    slope_low,
                "slope_ci95_high":
                    slope_high,
                "ed10_ci95_low":
                    ed10_low,
                "ed10_ci95_high":
                    ed10_high,
                "ed50_ci95_low":
                    ed50_low,
                "ed50_ci95_high":
                    ed50_high,
                "ed90_ci95_low":
                    ed90_low,
                "ed90_ci95_high":
                    ed90_high,
                "bootstrap_replicates":
                    accepted,
                "bootstrap_seed":
                    args.bootstrap_seed,
            }
        )

    # ========================================================
    # Delta ED50 relative to nominal
    #
    # Lower ED50 = greater tolerance to severe LoE.
    # Therefore:
    #   negative delta => robustness improvement
    #   positive delta => robustness degradation
    # ========================================================

    delta_rows = []

    for condition_id in condition_order:
        metadata = condition_metadata[
            condition_id
        ]

        delta = (
            fits[
                condition_id
            ]["ed50"]
            - nominal_ed50
        )

        low, high = percentile_ci(
            delta_bootstrap[
                condition_id
            ]
        )

        delta_rows.append(
            {
                "condition_id":
                    condition_id,
                "parameter":
                    metadata["parameter"],
                "factor":
                    metadata["factor"],
                "nominal_ed50":
                    nominal_ed50,
                "condition_ed50":
                    fits[
                        condition_id
                    ]["ed50"],
                "delta_ed50":
                    delta,
                "delta_ed50_ci95_low":
                    low,
                "delta_ed50_ci95_high":
                    high,
                "interpretation":
                    (
                        "improved_fault_tolerance"
                        if delta < 0.0
                        else
                        "reduced_fault_tolerance"
                    ),
            }
        )

    # ========================================================
    # Parameter-level paired -10 / +10 table
    # ========================================================

    by_parameter = defaultdict(dict)

    for row in delta_rows:
        by_parameter[
            row["parameter"]
        ][
            float(row["factor"])
        ] = row

    sensitivity_rows = []

    for parameter in sorted(
        by_parameter
    ):
        entries = by_parameter[
            parameter
        ]

        if set(entries) != {
            0.9,
            1.1,
        }:
            raise SystemExit(
                "[FAIL] Parameter missing "
                f"0.9/1.1 pair: {parameter}"
            )

        minus = entries[0.9]
        plus = entries[1.1]

        minus_delta = float(
            minus["delta_ed50"]
        )

        plus_delta = float(
            plus["delta_ed50"]
        )

        span = (
            plus_delta
            - minus_delta
        )

        max_abs = max(
            abs(minus_delta),
            abs(plus_delta),
        )

        asymmetry = (
            plus_delta
            + minus_delta
        )

        sensitivity_rows.append(
            {
                "parameter":
                    parameter,
                "nominal_ed50":
                    nominal_ed50,
                "minus10_ed50":
                    minus[
                        "condition_ed50"
                    ],
                "minus10_delta_ed50":
                    minus_delta,
                "minus10_delta_ci95_low":
                    minus[
                        "delta_ed50_ci95_low"
                    ],
                "minus10_delta_ci95_high":
                    minus[
                        "delta_ed50_ci95_high"
                    ],
                "plus10_ed50":
                    plus[
                        "condition_ed50"
                    ],
                "plus10_delta_ed50":
                    plus_delta,
                "plus10_delta_ci95_low":
                    plus[
                        "delta_ed50_ci95_low"
                    ],
                "plus10_delta_ci95_high":
                    plus[
                        "delta_ed50_ci95_high"
                    ],
                "plus_minus_span":
                    span,
                "max_abs_delta_ed50":
                    max_abs,
                "asymmetry_sum":
                    asymmetry,
            }
        )

    sensitivity_rows.sort(
        key=lambda row: (
            row[
                "max_abs_delta_ed50"
            ]
        ),
        reverse=True,
    )

    # ========================================================
    # Save outputs
    # ========================================================

    fit_path = (
        args.output
        / "firth_ed_thresholds.csv"
    )

    delta_path = (
        args.output
        / "delta_ed50_vs_nominal.csv"
    )

    sensitivity_path = (
        args.output
        / "ofat_sensitivity_table.csv"
    )

    report_path = (
        args.output
        / "ofat_sensitivity_report.md"
    )

    bootstrap_meta_path = (
        args.output
        / "bootstrap_metadata.csv"
    )

    write_csv(
        fit_path,
        final_fit_rows,
    )

    write_csv(
        delta_path,
        delta_rows,
    )

    write_csv(
        sensitivity_path,
        sensitivity_rows,
    )

    write_csv(
        bootstrap_meta_path,
        [
            {
                "estimator":
                    "firth_bias_reduced_logistic",
                "eta_scale":
                    ETA_SCALE,
                "bootstrap_type":
                    (
                        "seed_cluster_bootstrap;"
                        "paired_across_ofat_conditions;"
                        "independent_nominal_reference"
                    ),
                "bootstrap_requested":
                    args.bootstrap,
                "bootstrap_accepted":
                    accepted,
                "bootstrap_attempted":
                    attempted,
                "bootstrap_seed":
                    args.bootstrap_seed,
                "nominal_seed_count":
                    len(nominal_seeds),
                "ofat_seed_count":
                    len(
                        reference_ofat_seeds
                    ),
            }
        ],
    )

    report = [
        "# M2 PINV OFAT Model-Sensitivity Analysis",
        "",
        "## Estimator",
        "",
        (
            "- Bias-reduced Firth logistic regression "
            "was used for nominal and all OFAT conditions."
        ),
        (
            "- This estimator was chosen because several "
            "perturbed boundaries exhibit complete or "
            "near-complete separation."
        ),
        (
            "- Bootstrap resampling was clustered by "
            "trial seed."
        ),
        (
            "- The same OFAT cluster resample was used "
            "across all ten perturbation conditions to "
            "preserve their paired-seed structure."
        ),
        (
            "- Nominal seeds were resampled independently "
            "because the nominal experiment used a distinct "
            "seed set."
        ),
        "",
        "## Interpretation",
        "",
        (
            "- Lower ED50 means tolerance of a more severe "
            "motor-loss condition."
        ),
        (
            "- Therefore negative ΔED50 relative to nominal "
            "indicates improved fault tolerance."
        ),
        (
            "- Positive ΔED50 indicates reduced fault "
            "tolerance."
        ),
        "",
        "## ED50 estimates",
        "",
        (
            "| Condition | ED50 | 95% CI | "
            "ΔED50 vs nominal |"
        ),
        "|---|---:|---:|---:|",
    ]

    fit_lookup = {
        row["condition_id"]: row
        for row in final_fit_rows
    }

    report.append(
        "| nominal | "
        f"{fit_lookup['nominal']['ed50']:.9f} | "
        f"[{fit_lookup['nominal']['ed50_ci95_low']:.9f}, "
        f"{fit_lookup['nominal']['ed50_ci95_high']:.9f}] | "
        "0 |"
    )

    delta_lookup = {
        row["condition_id"]: row
        for row in delta_rows
    }

    for condition_id in condition_order:
        fit_row = fit_lookup[
            condition_id
        ]

        delta_row = delta_lookup[
            condition_id
        ]

        report.append(
            f"| {condition_id} | "
            f"{fit_row['ed50']:.9f} | "
            f"[{fit_row['ed50_ci95_low']:.9f}, "
            f"{fit_row['ed50_ci95_high']:.9f}] | "
            f"{delta_row['delta_ed50']:+.9f} |"
        )

    report.extend(
        [
            "",
            "## Sensitivity ranking",
            "",
            (
                "| Parameter | -10% ΔED50 | "
                "+10% ΔED50 | Max |ΔED50| |"
            ),
            "|---|---:|---:|---:|",
        ]
    )

    for row in sensitivity_rows:
        report.append(
            f"| {row['parameter']} | "
            f"{float(row['minus10_delta_ed50']):+.9f} | "
            f"{float(row['plus10_delta_ed50']):+.9f} | "
            f"{float(row['max_abs_delta_ed50']):.9f} |"
        )

    report_path.write_text(
        "\n".join(report)
        + "\n"
    )

    print()
    print("========== COMMON FIRTH FITS ==========")

    for row in final_fit_rows:
        print(
            f"{row['condition_id']}: "
            f"ED50={row['ed50']:.9f} "
            f"CI=["
            f"{row['ed50_ci95_low']:.9f}, "
            f"{row['ed50_ci95_high']:.9f}] "
            f"slope={row['slope_per_eta_0p0001']:.6f}"
        )

    print()
    print("========== DELTA ED50 ==========")

    for row in delta_rows:
        print(
            f"{row['condition_id']}: "
            f"delta={row['delta_ed50']:+.9f} "
            f"CI=["
            f"{row['delta_ed50_ci95_low']:+.9f}, "
            f"{row['delta_ed50_ci95_high']:+.9f}]"
        )

    print()
    print("========== SENSITIVITY RANKING ==========")

    for index, row in enumerate(
        sensitivity_rows,
        start=1,
    ):
        print(
            f"{index}. {row['parameter']}: "
            f"-10%={float(row['minus10_delta_ed50']):+.9f}, "
            f"+10%={float(row['plus10_delta_ed50']):+.9f}, "
            f"max_abs={float(row['max_abs_delta_ed50']):.9f}"
        )

    print()
    print(
        f"bootstrap_accepted={accepted}/"
        f"{args.bootstrap}"
    )

    print(f"[SAVED] {fit_path}")
    print(f"[SAVED] {delta_path}")
    print(f"[SAVED] {sensitivity_path}")
    print(f"[SAVED] {bootstrap_meta_path}")
    print(f"[SAVED] {report_path}")


if __name__ == "__main__":
    main()
