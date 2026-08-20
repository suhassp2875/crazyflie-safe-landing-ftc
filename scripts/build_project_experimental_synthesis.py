#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
import subprocess
from collections import defaultdict
from pathlib import Path


ROOT = Path("results/final")

DEV = (
    ROOT
    / "pinv_baseline/seeded_eta0p496/production_30/"
    "three_controller_paired_trials.csv"
)

HOLDOUT = (
    ROOT
    / "pinv_baseline/seeded_eta0p496/"
    "motor_conditioned_holdout/"
    "holdout_aggregate_by_motor.csv"
)

SUPERVISOR = (
    ROOT
    / "pinv_baseline/seeded_eta0p496/"
    "randomized_supervisor/production120/"
    "supervisor_aggregate_by_motor.csv"
)

SENSITIVITY = (
    ROOT
    / "model_sensitivity/ofat/synthesis/"
    "parameter_sensitivity_ranking.csv"
)

ROUTING_STABILITY = (
    ROOT
    / "model_sensitivity/ofat/synthesis/"
    "routing_stability_compact.csv"
)

OUT = ROOT / "project_experimental_synthesis"


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise SystemExit(
            f"[FAIL] Missing required input: {path}"
        )

    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise SystemExit(
            f"[FAIL] Empty input: {path}"
        )

    return rows


def write_csv(
    path: Path,
    rows: list[dict],
) -> None:
    with path.open(
        "w",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def wilson95(
    safe: int,
    n: int,
) -> tuple[float, float]:
    z = 1.959963984540054

    p = safe / n

    denom = 1.0 + z * z / n

    center = (
        p + z * z / (2.0 * n)
    ) / denom

    half = (
        z
        * (
            p * (1.0 - p) / n
            + z * z / (4.0 * n * n)
        ) ** 0.5
        / denom
    )

    return (
        center - half,
        center + half,
    )


def pct(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def main() -> None:
    OUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    dev = read_csv(DEV)
    holdout = read_csv(HOLDOUT)
    supervisor = read_csv(SUPERVISOR)
    sensitivity = read_csv(SENSITIVITY)
    routing = read_csv(ROUTING_STABILITY)

    # ========================================================
    # Development controller complementarity
    # ========================================================

    if len(dev) != 120:
        raise SystemExit(
            "[FAIL] Expected 120 development paired rows."
        )

    dev_by_motor = defaultdict(
        lambda: {
            "n": 0,
            "pinv": 0,
            "qplite": 0,
            "cem": 0,
        }
    )

    for row in dev:
        motor = int(row["motor"])

        d = dev_by_motor[motor]

        d["n"] += 1

        d["pinv"] += as_bool(
            row["pinv_safe"]
        )

        d["qplite"] += as_bool(
            row["qplite_safe"]
        )

        d["cem"] += as_bool(
            row["cem_tuned_safe"]
        )

    if set(dev_by_motor) != {
        1,
        2,
        3,
        4,
    }:
        raise SystemExit(
            "[FAIL] Development motors are incomplete."
        )

    expected_selection = {
        1: "cem",
        2: "pinv",
        3: "cem",
        4: "cem",
    }

    complementarity_rows = []

    development_selected_total = 0

    for motor in range(1, 5):
        d = dev_by_motor[motor]

        if d["n"] != 30:
            raise SystemExit(
                f"[FAIL] M{motor}: expected 30 dev trials."
            )

        scores = {
            "pinv":
                d["pinv"],
            "qplite":
                d["qplite"],
            "cem":
                d["cem"],
        }

        maximum = max(
            scores.values()
        )

        winners = [
            name
            for name, value in scores.items()
            if value == maximum
        ]

        if len(winners) != 1:
            raise SystemExit(
                f"[FAIL] M{motor}: controller-selection tie."
            )

        selected = winners[0]

        if (
            selected
            != expected_selection[motor]
        ):
            raise SystemExit(
                f"[FAIL] M{motor}: unexpected selected "
                f"controller {selected}."
            )

        development_selected_total += (
            scores[selected]
        )

        complementarity_rows.append(
            {
                "motor":
                    motor,
                "n":
                    d["n"],
                "pinv_safe":
                    d["pinv"],
                "qplite_safe":
                    d["qplite"],
                "cem_tuned_safe":
                    d["cem"],
                "selected_controller":
                    selected,
                "selected_safe":
                    scores[selected],
            }
        )

    assert development_selected_total == 112

    # ========================================================
    # Fresh holdout
    # ========================================================

    if len(holdout) != 4:
        raise SystemExit(
            "[FAIL] Expected four holdout aggregate rows."
        )

    holdout_lookup = {
        int(row["motor"]): row
        for row in holdout
    }

    holdout_total = sum(
        int(row["safe_count"])
        for row in holdout
    )

    holdout_n = sum(
        int(row["n"])
        for row in holdout
    )

    assert holdout_total == 117
    assert holdout_n == 120

    # ========================================================
    # Randomized supervisor v1
    # ========================================================

    if len(supervisor) != 4:
        raise SystemExit(
            "[FAIL] Expected four supervisor aggregate rows."
        )

    supervisor_lookup = {
        int(row["motor"]): row
        for row in supervisor
    }

    supervisor_total = sum(
        int(row["safe_count"])
        for row in supervisor
    )

    supervisor_n = sum(
        int(row["n"])
        for row in supervisor
    )

    assert supervisor_total == 115
    assert supervisor_n == 120

    # ========================================================
    # Validation summary
    # ========================================================

    validation_rows = []

    for motor in range(1, 5):
        dev_row = next(
            row
            for row in complementarity_rows
            if int(row["motor"]) == motor
        )

        hold = holdout_lookup[motor]
        sup = supervisor_lookup[motor]

        validation_rows.append(
            {
                "motor":
                    motor,
                "selected_controller":
                    dev_row[
                        "selected_controller"
                    ],
                "development_safe":
                    dev_row[
                        "selected_safe"
                    ],
                "development_n":
                    30,
                "fresh_holdout_safe":
                    int(
                        hold["safe_count"]
                    ),
                "fresh_holdout_n":
                    int(
                        hold["n"]
                    ),
                "supervisor_v1_safe":
                    int(
                        sup["safe_count"]
                    ),
                "supervisor_v1_n":
                    int(
                        sup["n"]
                    ),
            }
        )

    # ========================================================
    # Model sensitivity summary
    # ========================================================

    if len(sensitivity) != 5:
        raise SystemExit(
            "[FAIL] Expected five sensitivity rows."
        )

    if (
        sensitivity[0]["parameter"]
        != "thrust_coefficient"
    ):
        raise SystemExit(
            "[FAIL] Unexpected first sensitivity rank."
        )

    if (
        sensitivity[1]["parameter"]
        != "mass"
    ):
        raise SystemExit(
            "[FAIL] Unexpected second sensitivity rank."
        )

    if len(routing) != 11:
        raise SystemExit(
            "[FAIL] Expected 11 M2 routing states."
        )

    pinv_higher = [
        row
        for row in routing
        if row["routing_state"]
        == "pinv_preferred"
    ]

    cem_higher = [
        row
        for row in routing
        if row["routing_state"]
        == "cem_preferred"
    ]

    ties = [
        row
        for row in routing
        if row["routing_state"]
        == "tie"
    ]

    assert len(pinv_higher) == 9
    assert len(cem_higher) == 0
    assert len(ties) == 2

    # ========================================================
    # Write tables
    # ========================================================

    write_csv(
        OUT
        / "controller_complementarity.csv",
        complementarity_rows,
    )

    write_csv(
        OUT
        / "validation_summary_by_motor.csv",
        validation_rows,
    )

    sensitivity_out = []

    for rank, row in enumerate(
        sensitivity,
        start=1,
    ):
        sensitivity_out.append(
            {
                "rank":
                    rank,
                "parameter":
                    row["parameter"],
                "minus10_delta_ed50":
                    row[
                        "minus10_delta_ed50"
                    ],
                "plus10_delta_ed50":
                    row[
                        "plus10_delta_ed50"
                    ],
                "max_abs_delta_ed50":
                    row[
                        "max_abs_delta_ed50"
                    ],
            }
        )

    write_csv(
        OUT
        / "model_sensitivity_ranking.csv",
        sensitivity_out,
    )

    # ========================================================
    # Overall numerical summary
    # ========================================================

    dev_lo, dev_hi = wilson95(
        development_selected_total,
        120,
    )

    hold_lo, hold_hi = wilson95(
        holdout_total,
        holdout_n,
    )

    sup_lo, sup_hi = wilson95(
        supervisor_total,
        supervisor_n,
    )

    overall_rows = [
        {
            "stage":
                "development_selected_policy",
            "safe":
                development_selected_total,
            "n":
                120,
            "rate":
                development_selected_total / 120,
            "wilson95_lower":
                dev_lo,
            "wilson95_upper":
                dev_hi,
            "role":
                "policy_selection_in_sample",
        },
        {
            "stage":
                "fresh_seed_holdout",
            "safe":
                holdout_total,
            "n":
                holdout_n,
            "rate":
                holdout_total / holdout_n,
            "wilson95_lower":
                hold_lo,
            "wilson95_upper":
                hold_hi,
            "role":
                "fresh_seed_validation_same_simulator_distribution",
        },
        {
            "stage":
                "randomized_supervisor_v1",
            "safe":
                supervisor_total,
            "n":
                supervisor_n,
            "rate":
                supervisor_total / supervisor_n,
            "wilson95_lower":
                sup_lo,
            "wilson95_upper":
                sup_hi,
            "role":
                "integrated_randomized_order_validation_known_motor_identity",
        },
    ]

    write_csv(
        OUT / "overall_stage_summary.csv",
        overall_rows,
    )

    # ========================================================
    # Claims
    # ========================================================

    claims = [
        "# Defensible Whole-Project Experimental Claims",
        "",
        "## Controller complementarity",
        "",
        (
            "At eta=0.496, no single tested allocator "
            "dominated across all four single-motor LoE "
            "geometries."
        ),
        "",
        (
            "- M1 development: PINV 26/30, "
            "QP-lite 4/30, CEM-tuned 30/30."
        ),
        (
            "- M2 development: PINV 30/30, "
            "QP-lite 6/30, CEM-tuned 3/30."
        ),
        (
            "- M3 development: PINV 19/30, "
            "QP-lite 28/30, CEM-tuned 29/30."
        ),
        (
            "- M4 development: PINV 0/30, "
            "QP-lite 5/30, CEM-tuned 23/30."
        ),
        "",
        (
            "The resulting frozen motor-conditioned "
            "routing policy was M1->CEM, M2->PINV, "
            "M3->CEM, M4->CEM."
        ),
        "",
        "## Frozen-policy validation",
        "",
        (
            f"- Development selected-policy total: "
            f"{development_selected_total}/120 "
            f"({pct(development_selected_total / 120)})."
        ),
        (
            f"- Fresh-seed holdout: "
            f"{holdout_total}/{holdout_n} "
            f"({pct(holdout_total / holdout_n)}), "
            f"Wilson 95% CI "
            f"[{pct(hold_lo)}, {pct(hold_hi)}]."
        ),
        (
            f"- Randomized-order supervisor v1: "
            f"{supervisor_total}/{supervisor_n} "
            f"({pct(supervisor_total / supervisor_n)}), "
            f"Wilson 95% CI "
            f"[{pct(sup_lo)}, {pct(sup_hi)}]."
        ),
        "",
        (
            "The development result is policy-selection "
            "evidence and must not be presented as an "
            "independent validation result."
        ),
        "",
        "## Model sensitivity",
        "",
        (
            "For the M2 PINV branch, thrust coefficient "
            "and mass produced the largest ED50 shifts "
            "under the tested +/-10% OFAT perturbations."
        ),
        (
            f"- Thrust coefficient: max |Delta ED50| = "
            f"{float(sensitivity[0]['max_abs_delta_ed50']):.9f}."
        ),
        (
            f"- Mass: max |Delta ED50| = "
            f"{float(sensitivity[1]['max_abs_delta_ed50']):.9f}."
        ),
        (
            "Motor time constant, arm length, and "
            "thrust-to-torque ratio produced much smaller "
            "ED50 shifts in the tested range."
        ),
        "",
        (
            "At eta=0.496, PINV had a higher safe-touchdown "
            "count than frozen CEM in 9/11 nominal-plus-OFAT "
            "plant states, tied in 2/11, and CEM had the "
            "higher count in 0/11."
        ),
        "",
        "## Claim boundaries",
        "",
        (
            "- All reported results are simulation results "
            "from the tested CrazySim/Gazebo setup."
        ),
        (
            "- Failed-motor identity is supplied by the "
            "experiment; online fault diagnosis is not "
            "validated."
        ),
        (
            "- The fresh holdout uses new seeds but the same "
            "simulator and initial-condition distribution."
        ),
        (
            "- The model-sensitivity experiment varies one "
            "plant parameter at a time; simultaneous "
            "multi-parameter mismatch is not tested."
        ),
        (
            "- The M2 routing-stability comparison is made "
            "at eta=0.496 and is not a complete perturbed "
            "boundary comparison between controllers."
        ),
        (
            "- These experiments do not establish transfer "
            "to physical Crazyflie hardware."
        ),
    ]

    (
        OUT / "whole_project_claims.md"
    ).write_text(
        "\n".join(claims) + "\n"
    )

    # ========================================================
    # Paper-style results narrative
    # ========================================================

    narrative = [
        "# Whole-Project Experimental Synthesis",
        "",
        "## 1. Controller complementarity",
        "",
        (
            "The central development result is that allocator "
            "performance depends strongly on failed-motor "
            "geometry. At eta=0.496, PINV is strongest for "
            "M2, whereas the CEM-tuned residual allocator is "
            "strongest for M1, M3, and M4."
        ),
        "",
        (
            "This motivates motor-conditioned controller "
            "selection rather than use of a single global "
            "allocator."
        ),
        "",
        "## 2. Frozen motor-conditioned policy",
        "",
        (
            "The development block selects M1->CEM, "
            "M2->PINV, M3->CEM, and M4->CEM, yielding "
            "112/120 safe first-contact touchdowns on the "
            "development seeds. Because those same results "
            "were used to choose the routing policy, this "
            "112/120 figure is in-sample selection evidence."
        ),
        "",
        "## 3. Fresh validation",
        "",
        (
            "With the routing frozen and evaluated on a new "
            "30-seed block per motor, the policy achieves "
            "117/120 safe touchdowns (97.5%)."
        ),
        "",
        (
            "A separate randomized-order integrated "
            "supervisor evaluation achieves 115/120 "
            "(95.8%). The failed-motor identity is supplied "
            "by the experiment, so this validates allocator "
            "selection and execution but not online fault "
            "diagnosis."
        ),
        "",
        "## 4. Plant-model sensitivity",
        "",
        (
            "The M2 PINV branch was then subjected to "
            "one-at-a-time +/-10% perturbations of mass, "
            "physical thrust coefficient, motor time "
            "constant, thrust-to-torque ratio, and arm "
            "length."
        ),
        "",
        (
            "Mass and thrust coefficient dominate the ED50 "
            "sensitivity, while the remaining three "
            "parameters produce much smaller shifts over the "
            "tested range."
        ),
        "",
        (
            "A separate fixed-eta PINV-versus-CEM check "
            "shows no tested plant state in which CEM has a "
            "higher safe-touchdown count than PINV for M2. "
            "However, adverse +10% mass and -10% thrust "
            "coefficient perturbations cause both tested "
            "controllers to fail all paired trials at "
            "eta=0.496."
        ),
        "",
        "## 5. Overall interpretation",
        "",
        (
            "The combined experiments support a "
            "motor-conditioned allocation strategy: the "
            "best controller depends on failed-motor "
            "geometry, and freezing that routing generalizes "
            "well to fresh seeds within the same simulator "
            "distribution."
        ),
        "",
        (
            "At the same time, controller selection does not "
            "remove dependence on plant authority. Large "
            "mass or thrust-coefficient mismatch can shift "
            "the safety boundary enough that both candidate "
            "controllers fail at the nominal operating point."
        ),
    ]

    (
        OUT / "experimental_results_narrative.md"
    ).write_text(
        "\n".join(narrative) + "\n"
    )

    # ========================================================
    # Provenance
    # ========================================================

    commit = subprocess.check_output(
        [
            "git",
            "rev-parse",
            "HEAD",
        ],
        text=True,
    ).strip()

    provenance = {
        "builder_commit":
            commit,
        "eta":
            0.496,
        "development_source":
            str(DEV),
        "holdout_source":
            str(HOLDOUT),
        "supervisor_v1_source":
            str(SUPERVISOR),
        "model_sensitivity_source":
            str(SENSITIVITY),
        "m2_routing_stability_source":
            str(ROUTING_STABILITY),
        "selected_policy": {
            "M1":
                "CEM-tuned QP-lite",
            "M2":
                "bounded WLS/PINV",
            "M3":
                "CEM-tuned QP-lite",
            "M4":
                "CEM-tuned QP-lite",
        },
    }

    (
        OUT / "provenance.json"
    ).write_text(
        json.dumps(
            provenance,
            indent=2,
        )
        + "\n"
    )

    readme = """# Project Experimental Synthesis

Curated paper-level synthesis of the completed Crazyflie
single-motor LoE experiments.

Outputs:

- `controller_complementarity.csv`
- `validation_summary_by_motor.csv`
- `overall_stage_summary.csv`
- `model_sensitivity_ranking.csv`
- `whole_project_claims.md`
- `experimental_results_narrative.md`
- `provenance.json`

The package performs no simulation and derives its numerical
results from the frozen authoritative result files listed in
`provenance.json`.
"""

    (
        OUT / "README.md"
    ).write_text(readme)

    print("========== PROJECT SYNTHESIS ==========")
    print(
        "development_selected="
        f"{development_selected_total}/120"
    )
    print(
        f"fresh_holdout={holdout_total}/{holdout_n}"
    )
    print(
        "randomized_supervisor_v1="
        f"{supervisor_total}/{supervisor_n}"
    )
    print(
        "routing=M1:CEM,M2:PINV,M3:CEM,M4:CEM"
    )
    print(
        "sensitivity_rank_1="
        + sensitivity[0]["parameter"]
    )
    print(
        "sensitivity_rank_2="
        + sensitivity[1]["parameter"]
    )
    print(
        f"m2_ofat_pinv_higher={len(pinv_higher)}/11"
    )
    print(
        f"m2_ofat_ties={len(ties)}/11"
    )
    print(
        f"m2_ofat_cem_higher={len(cem_higher)}/11"
    )
    print()
    print("[PASS] Project-level synthesis generated.")


if __name__ == "__main__":
    main()
