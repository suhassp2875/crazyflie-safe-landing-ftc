#!/usr/bin/env python3

from __future__ import annotations

import csv
import shutil
from pathlib import Path


ROOT = Path(
    "results/final/model_sensitivity/ofat"
)

SENSITIVITY_ROOT = (
    ROOT / "sensitivity_analysis"
)

FINE_ROOT = (
    ROOT / "pinv_boundary_fine_sweep"
)

ROUTING_ROOT = (
    ROOT / "m2_routing_stability_eta0p496"
)

OUTPUT_ROOT = (
    ROOT / "synthesis"
)


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise SystemExit(
            f"[FAIL] Missing required input: {path}"
        )

    with path.open(newline="") as file:
        rows = list(csv.DictReader(file))

    if not rows:
        raise SystemExit(
            f"[FAIL] Empty CSV: {path}"
        )

    return rows


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
            fieldnames=list(rows[0].keys()),
            lineterminator="\n",
        )

        writer.writeheader()
        writer.writerows(rows)


def fmt(value: float) -> str:
    return f"{value:.9f}"


def fmt_signed(value: float) -> str:
    return f"{value:+.9f}"


def primary_failure_mechanism(
    row: dict,
) -> str:
    counts = {
        "vertical_speed":
            int(row["vertical_fail_total"]),
        "horizontal_speed":
            int(row["horizontal_fail_total"]),
        "tilt":
            int(row["tilt_fail_total"]),
        "angular_rate":
            int(row["angular_fail_total"]),
        "drift":
            int(row["drift_fail_total"]),
    }

    maximum = max(counts.values())

    if maximum == 0:
        return "none"

    winners = [
        name
        for name, count in counts.items()
        if count == maximum
    ]

    return "+".join(winners)


def main() -> None:
    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    fit_rows = read_csv(
        SENSITIVITY_ROOT
        / "firth_ed_thresholds.csv"
    )

    delta_rows = read_csv(
        SENSITIVITY_ROOT
        / "delta_ed50_vs_nominal.csv"
    )

    sensitivity_rows = read_csv(
        SENSITIVITY_ROOT
        / "ofat_sensitivity_table.csv"
    )

    fine_rows = read_csv(
        FINE_ROOT
        / "ofat_fine_condition_summary.csv"
    )

    routing_rows = read_csv(
        ROUTING_ROOT
        / "routing_stability_pairwise.csv"
    )

    routing_controller_rows = read_csv(
        ROUTING_ROOT
        / "routing_stability_controller_summary.csv"
    )


    # ========================================================
    # Structural audits
    # ========================================================

    if len(fit_rows) != 11:
        raise SystemExit(
            "[FAIL] Expected 11 Firth fits."
        )

    if len(delta_rows) != 10:
        raise SystemExit(
            "[FAIL] Expected 10 delta-ED50 rows."
        )

    if len(sensitivity_rows) != 5:
        raise SystemExit(
            "[FAIL] Expected 5 parameter pairs."
        )

    if len(fine_rows) != 10:
        raise SystemExit(
            "[FAIL] Expected 10 OFAT fine-sweep rows."
        )

    if len(routing_rows) != 11:
        raise SystemExit(
            "[FAIL] Expected 11 routing rows."
        )

    if len(routing_controller_rows) != 22:
        raise SystemExit(
            "[FAIL] Expected 22 routing-controller rows."
        )


    fit_lookup = {
        row["condition_id"]: row
        for row in fit_rows
    }

    delta_lookup = {
        row["condition_id"]: row
        for row in delta_rows
    }

    fine_lookup = {
        row["condition_id"]: row
        for row in fine_rows
    }

    routing_lookup = {
        row["condition_id"]: row
        for row in routing_rows
    }

    controller_lookup = {
        (
            row["condition_id"],
            row["controller"],
        ): row
        for row in routing_controller_rows
    }


    nominal_fit = fit_lookup[
        "nominal"
    ]

    nominal_ed50 = float(
        nominal_fit["ed50"]
    )


    # ========================================================
    # Condition-level master table
    # ========================================================

    condition_order = [
        row["condition_id"]
        for row in delta_rows
    ]

    master_rows = []

    for condition_id in condition_order:
        fit = fit_lookup[
            condition_id
        ]

        delta = delta_lookup[
            condition_id
        ]

        fine = fine_lookup[
            condition_id
        ]

        routing = routing_lookup[
            condition_id
        ]

        pinv = controller_lookup[
            (
                condition_id,
                "pinv",
            )
        ]

        cem = controller_lookup[
            (
                condition_id,
                "cem",
            )
        ]

        delta_value = float(
            delta["delta_ed50"]
        )

        delta_low = float(
            delta["delta_ed50_ci95_low"]
        )

        delta_high = float(
            delta["delta_ed50_ci95_high"]
        )

        if delta_high < 0.0:
            delta_direction = (
                "improved_fault_tolerance"
            )
        elif delta_low > 0.0:
            delta_direction = (
                "reduced_fault_tolerance"
            )
        else:
            delta_direction = (
                "uncertain_relative_to_nominal"
            )

        master_rows.append(
            {
                "condition_id":
                    condition_id,
                "parameter":
                    delta["parameter"],
                "factor":
                    delta["factor"],
                "ed50":
                    fit["ed50"],
                "ed50_ci95_low":
                    fit["ed50_ci95_low"],
                "ed50_ci95_high":
                    fit["ed50_ci95_high"],
                "delta_ed50":
                    delta["delta_ed50"],
                "delta_ed50_ci95_low":
                    delta[
                        "delta_ed50_ci95_low"
                    ],
                "delta_ed50_ci95_high":
                    delta[
                        "delta_ed50_ci95_high"
                    ],
                "delta_interpretation":
                    delta_direction,
                "fine_safe_count":
                    fine["safe_count"],
                "fine_trial_count":
                    fine["n_present"],
                "primary_failure_mechanism":
                    primary_failure_mechanism(
                        fine
                    ),
                "vertical_fail_total":
                    fine[
                        "vertical_fail_total"
                    ],
                "horizontal_fail_total":
                    fine[
                        "horizontal_fail_total"
                    ],
                "tilt_fail_total":
                    fine[
                        "tilt_fail_total"
                    ],
                "angular_fail_total":
                    fine[
                        "angular_fail_total"
                    ],
                "drift_fail_total":
                    fine[
                        "drift_fail_total"
                    ],
                "pinv_safe_eta0p496":
                    routing[
                        "pinv_safe_count"
                    ],
                "cem_safe_eta0p496":
                    routing[
                        "cem_safe_count"
                    ],
                "pinv_only_safe":
                    routing[
                        "pinv_only_safe"
                    ],
                "cem_only_safe":
                    routing[
                        "cem_only_safe"
                    ],
                "routing_state":
                    routing[
                        "routing_state"
                    ],
                "mcnemar_exact_p":
                    routing[
                        "mcnemar_exact_p"
                    ],
                "pinv_vertical_fail_eta0p496":
                    pinv[
                        "vertical_fail"
                    ],
                "pinv_angular_fail_eta0p496":
                    pinv[
                        "angular_fail"
                    ],
                "cem_vertical_fail_eta0p496":
                    cem[
                        "vertical_fail"
                    ],
                "cem_angular_fail_eta0p496":
                    cem[
                        "angular_fail"
                    ],
            }
        )


    master_path = (
        OUTPUT_ROOT
        / "model_sensitivity_master_table.csv"
    )

    write_csv(
        master_path,
        master_rows,
    )


    # ========================================================
    # Compact failure-mechanism table
    # ========================================================

    failure_rows = []

    for condition_id in condition_order:
        row = fine_lookup[
            condition_id
        ]

        failure_rows.append(
            {
                "condition_id":
                    condition_id,
                "parameter":
                    row["parameter"],
                "factor":
                    row["factor"],
                "safe_count":
                    row["safe_count"],
                "trial_count":
                    row["n_present"],
                "vertical_fail":
                    row[
                        "vertical_fail_total"
                    ],
                "horizontal_fail":
                    row[
                        "horizontal_fail_total"
                    ],
                "tilt_fail":
                    row[
                        "tilt_fail_total"
                    ],
                "angular_fail":
                    row[
                        "angular_fail_total"
                    ],
                "drift_fail":
                    row[
                        "drift_fail_total"
                    ],
                "primary_failure_mechanism":
                    primary_failure_mechanism(
                        row
                    ),
            }
        )


    failure_path = (
        OUTPUT_ROOT
        / "failure_mechanism_summary.csv"
    )

    write_csv(
        failure_path,
        failure_rows,
    )


    # ========================================================
    # Compact routing table
    # ========================================================

    routing_compact_rows = []

    for row in routing_rows:
        routing_compact_rows.append(
            {
                "condition_id":
                    row["condition_id"],
                "parameter":
                    row["parameter"],
                "factor":
                    row["factor"],
                "pinv_safe":
                    row["pinv_safe_count"],
                "cem_safe":
                    row["cem_safe_count"],
                "pinv_only_safe":
                    row["pinv_only_safe"],
                "cem_only_safe":
                    row["cem_only_safe"],
                "neither_safe":
                    row["neither_safe"],
                "routing_state":
                    row["routing_state"],
                "mcnemar_exact_p":
                    row["mcnemar_exact_p"],
            }
        )


    routing_path = (
        OUTPUT_ROOT
        / "routing_stability_compact.csv"
    )

    write_csv(
        routing_path,
        routing_compact_rows,
    )


    # ========================================================
    # Parameter-level sensitivity table
    # ========================================================

    parameter_rows = []

    for rank, row in enumerate(
        sensitivity_rows,
        start=1,
    ):
        parameter_rows.append(
            {
                "rank":
                    rank,
                "parameter":
                    row["parameter"],
                "nominal_ed50":
                    row["nominal_ed50"],
                "minus10_ed50":
                    row["minus10_ed50"],
                "minus10_delta_ed50":
                    row[
                        "minus10_delta_ed50"
                    ],
                "plus10_ed50":
                    row["plus10_ed50"],
                "plus10_delta_ed50":
                    row[
                        "plus10_delta_ed50"
                    ],
                "max_abs_delta_ed50":
                    row[
                        "max_abs_delta_ed50"
                    ],
                "plus_minus_span":
                    row[
                        "plus_minus_span"
                    ],
                "asymmetry_sum":
                    row[
                        "asymmetry_sum"
                    ],
            }
        )


    parameter_path = (
        OUTPUT_ROOT
        / "parameter_sensitivity_ranking.csv"
    )

    write_csv(
        parameter_path,
        parameter_rows,
    )


    # ========================================================
    # Derive high-level routing facts
    # ========================================================

    pinv_preferred = [
        row
        for row in routing_rows
        if row["routing_state"]
        == "pinv_preferred"
    ]

    cem_preferred = [
        row
        for row in routing_rows
        if row["routing_state"]
        == "cem_preferred"
    ]

    tied = [
        row
        for row in routing_rows
        if row["routing_state"]
        == "tie"
    ]

    pinv_significant = [
        row
        for row in routing_rows
        if (
            row["routing_state"]
            == "pinv_preferred"
            and float(
                row["mcnemar_exact_p"]
            ) < 0.05
        )
    ]

    perturbed_rows = [
        row
        for row in routing_rows
        if row["condition_id"]
        != "nominal"
    ]

    perturbed_pinv_higher = [
        row
        for row in perturbed_rows
        if row["routing_state"]
        == "pinv_preferred"
    ]

    perturbed_pinv_significant = [
        row
        for row in perturbed_pinv_higher
        if float(
            row["mcnemar_exact_p"]
        ) < 0.05
    ]


    if cem_preferred:
        routing_claim = (
            "The nominal M2 routing decision was "
            "reversed under at least one tested "
            "plant perturbation."
        )
    else:
        routing_claim = (
            "The nominal M2 routing decision was "
            "never reversed in favor of CEM under "
            "the tested plant perturbations at "
            "eta=0.496."
        )


    # ========================================================
    # Claims document
    # ========================================================

    claims = [
        "# Defensible Model-Sensitivity Claims",
        "",
        "## Primary claim",
        "",
        (
            "For the M2 bounded-WLS/PINV controller, "
            "the estimated motor-effectiveness safety "
            "boundary is strongly sensitive to mass and "
            "physical thrust coefficient, while ±10% "
            "perturbations of motor time constant, "
            "thrust-to-torque ratio, and arm length "
            "produce substantially smaller ED50 shifts "
            "under the tested CrazySim/Gazebo simulation model."
        ),
        "",
        "## Quantitative sensitivity",
        "",
        (
            f"- Common-estimator nominal ED50: "
            f"{fmt(nominal_ed50)}."
        ),
    ]


    for rank, row in enumerate(
        parameter_rows,
        start=1,
    ):
        claims.append(
            (
                f"- Rank {rank}: "
                f"`{row['parameter']}`; "
                f"max |ΔED50| = "
                f"{float(row['max_abs_delta_ed50']):.9f}."
            )
        )


    claims.extend(
        [
            "",
            "## Routing stability",
            "",
            f"- {routing_claim}",
            (
                f"- PINV had a higher safe-touchdown count in "
                f"{len(pinv_preferred)}/"
                f"{len(routing_rows)} tested plant states."
            ),
            (
                f"- The controllers tied in "
                f"{len(tied)}/"
                f"{len(routing_rows)} tested plant states."
            ),
            (
                f"- PINV's paired advantage reached "
                f"McNemar p<0.05 in "
                f"{len(pinv_significant)}/"
                f"{len(routing_rows)} tested plant states."
            ),
            (
                f"- Considering only the ten perturbed "
                f"plant states, PINV had the higher safe "
                f"count in {len(perturbed_pinv_higher)}/10 "
                f"and a paired p<0.05 advantage in "
                f"{len(perturbed_pinv_significant)}/10."
            ),
            (
                f"- CEM had a higher safe-touchdown count in "
                f"{len(cem_preferred)}/"
                f"{len(routing_rows)} tested plant states."
            ),
            "",
        ]
    )


    if tied:
        claims.append(
            "- Tied conditions: "
            + ", ".join(
                row["condition_id"]
                for row in tied
            )
            + "."
        )


    claims.extend(
        [
            "",
            "## Safety-criterion violation patterns",
            "",
        ]
    )


    for row in failure_rows:
        claims.append(
            (
                f"- `{row['condition_id']}`: "
                f"most frequent violated safety criterion = "
                f"{row['primary_failure_mechanism']}; "
                f"V/H/T/A/D = "
                f"{row['vertical_fail']}/"
                f"{row['horizontal_fail']}/"
                f"{row['tilt_fail']}/"
                f"{row['angular_fail']}/"
                f"{row['drift_fail']}."
            )
        )


    claims.extend(
        [
            "",
            "## Claim boundaries",
            "",
            (
                "- These are simulator results under the "
                "tested single-motor M2 LoE setup; they do "
                "not establish hardware robustness."
            ),
            (
                "- OFAT perturbations vary one plant "
                "parameter at a time by ±10%; combined "
                "multi-parameter mismatch was not tested."
            ),
            (
                "- Lower ED50 means tolerance to a more "
                "severe motor-loss condition."
            ),
            (
                "- The routing experiment is a fixed "
                "operating-point comparison at eta=0.496, "
                "not a complete perturbed boundary "
                "comparison between PINV and CEM."
            ),
            (
                "- The failed-motor identity is assumed "
                "known; online motor-fault diagnosis was "
                "not evaluated."
            ),
            (
                "- Zero-width seed-bootstrap intervals "
                "for some sharp transitions reflect "
                "identical sampled binary transition "
                "patterns and should not be interpreted "
                "as zero physical uncertainty."
            ),
        ]
    )


    claims_path = (
        OUTPUT_ROOT
        / "model_sensitivity_claims.md"
    )

    claims_path.write_text(
        "\n".join(claims)
        + "\n"
    )


    # ========================================================
    # Full results narrative
    # ========================================================

    narrative = [
        "# Model-Sensitivity Result Synthesis",
        "",
        "## Experimental scope",
        "",
        (
            "The sensitivity study evaluates the M2 "
            "bounded-WLS/PINV controller under one-at-a-time "
            "±10% perturbations of five plant parameters: "
            "mass, physical thrust coefficient, motor time "
            "constant, thrust-to-torque ratio, and arm "
            "length."
        ),
        "",
        (
            "All safety outcomes use the full first-contact "
            "criterion rather than vertical speed alone. "
            "The final boundary experiment contains "
            "2,100 fresh seeded OFAT trials, with 30 paired "
            "seeds at seven eta values for each of ten "
            "perturbed conditions."
        ),
        "",
        "## Boundary sensitivity",
        "",
        (
            f"The common Firth-logistic nominal ED50 is "
            f"{fmt(nominal_ed50)} "
            f"(95% paired-seed bootstrap CI "
            f"[{float(nominal_fit['ed50_ci95_low']):.9f}, "
            f"{float(nominal_fit['ed50_ci95_high']):.9f}])."
        ),
        "",
        (
            "Thrust coefficient and mass dominate the "
            "sensitivity ranking. Their ±10% perturbations "
            "move the estimated ED50 by roughly 0.045–0.055, "
            "whereas the remaining parameters move ED50 by "
            "approximately 10^-4."
        ),
        "",
        "| Rank | Parameter | -10% ΔED50 | +10% ΔED50 | Max |ΔED50| |",
        "|---:|---|---:|---:|---:|",
    ]


    for row in parameter_rows:
        narrative.append(
            (
                f"| {row['rank']} | "
                f"{row['parameter']} | "
                f"{float(row['minus10_delta_ed50']):+.9f} | "
                f"{float(row['plus10_delta_ed50']):+.9f} | "
                f"{float(row['max_abs_delta_ed50']):.9f} |"
            )
        )


    narrative.extend(
        [
            "",
            "## Safety-criterion violation patterns",
            "",
            (
                "The safety boundary is not uniformly "
                "vertical-speed limited. In the mass -10% "
                "condition, angular-rate violation is the "
                "most frequent failed criterion, with "
                "additional horizontal-speed and tilt "
                "violations. In the thrust-coefficient +10% "
                "condition, the observed unsafe trials fail "
                "the angular-rate criterion. Most remaining "
                "perturbations primarily violate the "
                "vertical-speed criterion. Criterion counts "
                "are not mutually exclusive; a single trial "
                "may contribute to multiple columns."
            ),
            "",
            "| Condition | Safe / 210 | Vertical | Horizontal | Tilt | Angular | Drift | Most frequent violated criterion |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )


    for row in failure_rows:
        narrative.append(
            (
                f"| {row['condition_id']} | "
                f"{row['safe_count']}/"
                f"{row['trial_count']} | "
                f"{row['vertical_fail']} | "
                f"{row['horizontal_fail']} | "
                f"{row['tilt_fail']} | "
                f"{row['angular_fail']} | "
                f"{row['drift_fail']} | "
                f"{row['primary_failure_mechanism']} |"
            )
        )


    narrative.extend(
        [
            "",
            "## Controller-routing stability",
            "",
            (
                "A separate fixed-operating-point experiment "
                "tested PINV against the frozen CEM-tuned "
                "QP-lite policy at eta=0.496 using 30 fresh "
                "paired seeds under nominal and all ten "
                "perturbed plant states, for 660 trials."
            ),
            "",
            routing_claim,
            "",
            "| Condition | PINV safe | CEM safe | PINV-only | CEM-only | Neither | Routing |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )


    for row in routing_compact_rows:
        narrative.append(
            (
                f"| {row['condition_id']} | "
                f"{row['pinv_safe']}/30 | "
                f"{row['cem_safe']}/30 | "
                f"{row['pinv_only_safe']} | "
                f"{row['cem_only_safe']} | "
                f"{row['neither_safe']} | "
                f"{row['routing_state']} |"
            )
        )


    narrative.extend(
        [
            "",
            (
                "The two tied adverse conditions are "
                "`mass_plus10` and "
                "`thrust_coefficient_minus10`; neither "
                "controller achieved a safe touchdown in "
                "any of the 30 paired trials at eta=0.496. "
                "Thus, these conditions provide evidence "
                "of loss of safety for both tested "
                "controllers at this operating point, "
                "rather than evidence of a routing reversal."
            ),
            "",
            "## Overall interpretation",
            "",
            (
                "The combined evidence supports a narrower "
                "and more defensible robustness statement "
                "than a generic claim of model invariance. "
                "The M2 PINV safety boundary is highly "
                "sensitive to parameters that directly "
                "change thrust-to-weight authority, "
                "especially mass and thrust coefficient. "
                "The ED50 shifts produced by the tested "
                "±10% changes in motor time constant, "
                "thrust-to-torque ratio, and arm length are "
                "much smaller than the corresponding mass "
                "and thrust-coefficient shifts. Across the "
                "fixed eta=0.496 comparison, no tested plant "
                "state produced a higher safe-touchdown "
                "count for CEM than for PINV."
            ),
            "",
            (
                "The adverse mass +10% and thrust-coefficient "
                "-10% cases also show that absence of a "
                "routing reversal does not imply safety "
                "robustness: neither tested controller "
                "achieved a safe touchdown in any of the "
                "30 paired trials at eta=0.496 under those "
                "two perturbations."
            ),
        ]
    )


    narrative_path = (
        OUTPUT_ROOT
        / "model_sensitivity_results.md"
    )

    narrative_path.write_text(
        "\n".join(narrative)
        + "\n"
    )


    # ========================================================
    # Copy publication figure into synthesis directory
    # ========================================================

    source_plot = (
        SENSITIVITY_ROOT
        / "ofat_ed50_tornado.png"
    )

    copied_plot = (
        OUTPUT_ROOT
        / "ofat_ed50_tornado.png"
    )

    if not source_plot.is_file():
        raise SystemExit(
            "[FAIL] Missing tornado plot."
        )

    shutil.copy2(
        source_plot,
        copied_plot,
    )


    # ========================================================
    # README / provenance
    # ========================================================

    readme = [
        "# Model-Sensitivity Synthesis Package",
        "",
        "This directory contains the curated outputs used to summarize the M2 plant-model sensitivity experiments.",
        "",
        "Source datasets:",
        "",
        "- `../sensitivity_analysis/firth_ed_thresholds.csv`",
        "- `../sensitivity_analysis/delta_ed50_vs_nominal.csv`",
        "- `../sensitivity_analysis/ofat_sensitivity_table.csv`",
        "- `../pinv_boundary_fine_sweep/ofat_fine_condition_summary.csv`",
        "- `../m2_routing_stability_eta0p496/routing_stability_pairwise.csv`",
        "- `../m2_routing_stability_eta0p496/routing_stability_controller_summary.csv`",
        "",
        "Curated outputs:",
        "",
        "- `model_sensitivity_master_table.csv`",
        "- `parameter_sensitivity_ranking.csv`",
        "- `failure_mechanism_summary.csv`",
        "- `routing_stability_compact.csv`",
        "- `model_sensitivity_claims.md`",
        "- `model_sensitivity_results.md`",
        "- `ofat_ed50_tornado.png`",
        "",
        "No additional simulation is performed by the synthesis builder.",
    ]


    readme_path = (
        OUTPUT_ROOT
        / "README.md"
    )

    readme_path.write_text(
        "\n".join(readme)
        + "\n"
    )


    # ========================================================
    # Final audits
    # ========================================================

    assert len(master_rows) == 10
    assert len(parameter_rows) == 5
    assert len(failure_rows) == 10
    assert len(routing_compact_rows) == 11

    assert not cem_preferred

    assert len(pinv_preferred) == 9
    assert len(tied) == 2
    assert len(pinv_significant) == 8
    assert len(perturbed_pinv_higher) == 8
    assert len(perturbed_pinv_significant) == 7

    assert {
        row["condition_id"]
        for row in tied
    } == {
        "mass_plus10",
        "thrust_coefficient_minus10",
    }

    assert parameter_rows[0][
        "parameter"
    ] == "thrust_coefficient"

    assert parameter_rows[1][
        "parameter"
    ] == "mass"


    print("========== SYNTHESIS AUDIT ==========")
    print(f"condition_rows={len(master_rows)}")
    print(f"parameter_rows={len(parameter_rows)}")
    print(f"failure_rows={len(failure_rows)}")
    print(f"routing_rows={len(routing_compact_rows)}")
    print(f"pinv_higher_count={len(pinv_preferred)}")
    print(f"pinv_significant_p_lt_0p05={len(pinv_significant)}")
    print(f"perturbed_pinv_higher_count={len(perturbed_pinv_higher)}")
    print(f"perturbed_pinv_significant_p_lt_0p05={len(perturbed_pinv_significant)}")
    print(f"ties={len(tied)}")
    print(f"cem_higher_count={len(cem_preferred)}")
    print()
    print("[PASS] Sensitivity ranking preserved.")
    print("[PASS] Failure mechanisms integrated.")
    print("[PASS] Routing stability integrated.")
    print("[PASS] No CEM-preferred plant state found.")
    print("[PASS] Synthesis package generated.")
    print()
    print(f"[SAVED] {master_path}")
    print(f"[SAVED] {parameter_path}")
    print(f"[SAVED] {failure_path}")
    print(f"[SAVED] {routing_path}")
    print(f"[SAVED] {claims_path}")
    print(f"[SAVED] {narrative_path}")
    print(f"[SAVED] {copied_plot}")
    print(f"[SAVED] {readme_path}")


if __name__ == "__main__":
    main()
