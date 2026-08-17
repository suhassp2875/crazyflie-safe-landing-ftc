#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean


DEFAULT_ROOT = Path(
    "results/final/model_sensitivity/ofat/"
    "m2_routing_stability_eta0p496"
)


def as_bool(value: str) -> bool:
    return value.strip().lower() in {
        "true",
        "1",
        "yes",
    }


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


def exact_mcnemar(
    pinv_only: int,
    cem_only: int,
) -> float:
    n = pinv_only + cem_only

    if n == 0:
        return 1.0

    k = min(
        pinv_only,
        cem_only,
    )

    lower_tail = sum(
        math.comb(n, index)
        for index in range(k + 1)
    ) / (2 ** n)

    return min(
        1.0,
        2.0 * lower_tail,
    )


def metric_mean(
    rows: list[dict],
    key: str,
):
    values = []

    for row in rows:
        value = row.get(
            key,
            "",
        ).strip()

        if value:
            values.append(
                float(value)
            )

    if not values:
        return ""

    return mean(values)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
    )

    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
    )

    args = parser.parse_args()

    schedule_path = (
        args.root
        / "routing_stability_schedule.csv"
    )

    summary_dir = (
        args.root / "summaries"
    )

    if not schedule_path.is_file():
        raise SystemExit(
            f"[FAIL] Missing schedule: "
            f"{schedule_path}"
        )

    with schedule_path.open(
        newline=""
    ) as file:
        schedule = list(
            csv.DictReader(file)
        )

    if len(schedule) != 660:
        raise SystemExit(
            "[FAIL] Expected 660 schedule rows; "
            f"found {len(schedule)}."
        )


    trial_rows = []
    missing = []

    for scheduled in schedule:
        summary_path = (
            summary_dir
            / (
                scheduled["tag"]
                + "_summary.csv"
            )
        )

        if not summary_path.is_file():
            missing.append(
                scheduled["tag"]
            )
            continue

        with summary_path.open(
            newline=""
        ) as file:
            rows = list(
                csv.DictReader(file)
            )

        if len(rows) != 1:
            raise SystemExit(
                "[FAIL] Expected one summary row in "
                f"{summary_path}."
            )

        row = rows[0]

        if (
            row["controller"]
            != scheduled["controller"]
        ):
            raise SystemExit(
                "[FAIL] Controller mismatch for "
                f"{scheduled['tag']}."
            )

        if (
            int(row["trial_seed"])
            != int(
                scheduled["trial_seed"]
            )
        ):
            raise SystemExit(
                "[FAIL] Seed mismatch for "
                f"{scheduled['tag']}."
            )

        if (
            abs(
                float(row["eta"])
                - float(scheduled["eta"])
            )
            > 1.0e-6
        ):
            raise SystemExit(
                "[FAIL] Eta mismatch for "
                f"{scheduled['tag']}."
            )

        enriched = {
            "condition_id":
                scheduled["condition_id"],
            "parameter":
                scheduled["parameter"],
            "factor":
                scheduled["factor"],
            "plant_sha256":
                scheduled["plant_sha256"],
            "controller":
                scheduled["controller"],
            "controller_order":
                scheduled["controller_order"],
            "motor":
                scheduled["motor"],
            "eta":
                scheduled["eta"],
            "rep":
                scheduled["rep"],
            "trial_seed":
                scheduled["trial_seed"],
            "protocol_id":
                scheduled["protocol_id"],
            "experiment_protocol_id":
                scheduled[
                    "experiment_protocol_id"
                ],
            "tag":
                scheduled["tag"],
        }

        for key, value in row.items():
            if key not in enriched:
                enriched[key] = value

        trial_rows.append(
            enriched
        )


    if (
        missing
        and not args.allow_incomplete
    ):
        raise SystemExit(
            "[FAIL] Missing completed trials: "
            f"{len(missing)}"
        )


    grouped = defaultdict(list)

    for row in trial_rows:
        grouped[
            (
                row["condition_id"],
                row["controller"],
            )
        ].append(row)


    controller_rows = []

    condition_order = []

    for row in schedule:
        condition_id = row[
            "condition_id"
        ]

        if condition_id not in condition_order:
            condition_order.append(
                condition_id
            )


    for condition_id in condition_order:
        schedule_condition = [
            row
            for row in schedule
            if row["condition_id"]
            == condition_id
        ]

        metadata = (
            schedule_condition[0]
        )

        for controller in (
            "pinv",
            "cem",
        ):
            rows = grouped.get(
                (
                    condition_id,
                    controller,
                ),
                [],
            )

            valid = sum(
                as_bool(
                    row["valid_prefault"]
                )
                for row in rows
            )

            contacts = sum(
                as_bool(
                    row["contact_found"]
                )
                for row in rows
            )

            safe = sum(
                as_bool(
                    row["safe_touchdown"]
                )
                for row in rows
            )

            vertical_fail = sum(
                not as_bool(
                    row["vertical_speed_ok"]
                )
                for row in rows
            )

            horizontal_fail = sum(
                not as_bool(
                    row["horizontal_speed_ok"]
                )
                for row in rows
            )

            tilt_fail = sum(
                not as_bool(
                    row["tilt_ok"]
                )
                for row in rows
            )

            angular_fail = sum(
                not as_bool(
                    row["angular_rate_ok"]
                )
                for row in rows
            )

            drift_fail = sum(
                not as_bool(
                    row["drift_ok"]
                )
                for row in rows
            )

            controller_rows.append(
                {
                    "condition_id":
                        condition_id,
                    "parameter":
                        metadata["parameter"],
                    "factor":
                        metadata["factor"],
                    "controller":
                        controller,
                    "n_expected":
                        30,
                    "n_present":
                        len(rows),
                    "valid_prefault_count":
                        valid,
                    "contact_count":
                        contacts,
                    "safe_count":
                        safe,
                    "safe_rate":
                        (
                            safe / len(rows)
                            if rows
                            else ""
                        ),
                    "vertical_fail":
                        vertical_fail,
                    "horizontal_fail":
                        horizontal_fail,
                    "tilt_fail":
                        tilt_fail,
                    "angular_fail":
                        angular_fail,
                    "drift_fail":
                        drift_fail,
                    "mean_vertical_speed_mps":
                        metric_mean(
                            rows,
                            "vertical_speed_mps",
                        ),
                    "mean_angular_rate_radps":
                        metric_mean(
                            rows,
                            "max_angular_rate_radps",
                        ),
                }
            )


    pairwise_rows = []

    for condition_id in condition_order:
        condition_trials = [
            row
            for row in trial_rows
            if row["condition_id"]
            == condition_id
        ]

        metadata = next(
            row
            for row in schedule
            if row["condition_id"]
            == condition_id
        )

        by_seed = defaultdict(dict)

        for row in condition_trials:
            by_seed[
                int(row["trial_seed"])
            ][
                row["controller"]
            ] = row

        pair_count = 0
        both_safe = 0
        pinv_only = 0
        cem_only = 0
        neither_safe = 0

        for seed in sorted(by_seed):
            pair = by_seed[seed]

            if not {
                "pinv",
                "cem",
            }.issubset(pair):
                continue

            pair_count += 1

            pinv_safe = as_bool(
                pair["pinv"][
                    "safe_touchdown"
                ]
            )

            cem_safe = as_bool(
                pair["cem"][
                    "safe_touchdown"
                ]
            )

            if pinv_safe and cem_safe:
                both_safe += 1
            elif pinv_safe:
                pinv_only += 1
            elif cem_safe:
                cem_only += 1
            else:
                neither_safe += 1


        pinv_safe_count = (
            both_safe + pinv_only
        )

        cem_safe_count = (
            both_safe + cem_only
        )

        if pinv_only > cem_only:
            routing_state = (
                "pinv_preferred"
            )
        elif cem_only > pinv_only:
            routing_state = (
                "cem_preferred"
            )
        else:
            routing_state = "tie"


        pairwise_rows.append(
            {
                "condition_id":
                    condition_id,
                "parameter":
                    metadata["parameter"],
                "factor":
                    metadata["factor"],
                "pairs_expected":
                    30,
                "pairs_present":
                    pair_count,
                "both_safe":
                    both_safe,
                "pinv_only_safe":
                    pinv_only,
                "cem_only_safe":
                    cem_only,
                "neither_safe":
                    neither_safe,
                "pinv_safe_count":
                    pinv_safe_count,
                "cem_safe_count":
                    cem_safe_count,
                "pinv_safe_rate":
                    (
                        pinv_safe_count
                        / pair_count
                        if pair_count
                        else ""
                    ),
                "cem_safe_rate":
                    (
                        cem_safe_count
                        / pair_count
                        if pair_count
                        else ""
                    ),
                "safe_count_difference_pinv_minus_cem":
                    (
                        pinv_safe_count
                        - cem_safe_count
                    ),
                "routing_state":
                    routing_state,
                "nominal_route_preserved_strict":
                    (
                        routing_state
                        == "pinv_preferred"
                    ),
                "nominal_route_not_reversed":
                    (
                        routing_state
                        != "cem_preferred"
                    ),
                "mcnemar_exact_p":
                    exact_mcnemar(
                        pinv_only,
                        cem_only,
                    ),
            }
        )


    trial_path = (
        args.root
        / "routing_stability_trial_summaries.csv"
    )

    controller_path = (
        args.root
        / "routing_stability_controller_summary.csv"
    )

    pairwise_path = (
        args.root
        / "routing_stability_pairwise.csv"
    )

    report_path = (
        args.root
        / "routing_stability_report.md"
    )


    if trial_rows:
        write_csv(
            trial_path,
            trial_rows,
        )

    write_csv(
        controller_path,
        controller_rows,
    )

    write_csv(
        pairwise_path,
        pairwise_rows,
    )


    report = [
        "# M2 Controller Routing Stability at eta=0.496",
        "",
        f"- Scheduled trials: {len(schedule)}",
        f"- Completed trials: {len(trial_rows)}",
        f"- Missing trials: {len(missing)}",
        "",
        (
            "The nominal routing decision is PINV for M2. "
            "This experiment tests that fixed operational "
            "choice under ±10% plant perturbations."
        ),
        "",
        (
            "| Condition | Pairs | PINV safe | CEM safe | "
            "PINV-only | CEM-only | Routing state | "
            "McNemar p |"
        ),
        (
            "|---|---:|---:|---:|---:|---:|---|---:|"
        ),
    ]


    for row in pairwise_rows:
        report.append(
            "| "
            f"{row['condition_id']} | "
            f"{row['pairs_present']}/"
            f"{row['pairs_expected']} | "
            f"{row['pinv_safe_count']} | "
            f"{row['cem_safe_count']} | "
            f"{row['pinv_only_safe']} | "
            f"{row['cem_only_safe']} | "
            f"{row['routing_state']} | "
            f"{float(row['mcnemar_exact_p']):.6g} |"
        )


    report.extend(
        [
            "",
            "## Interpretation rules",
            "",
            (
                "- `pinv_preferred`: more paired seeds "
                "are safe under PINV than CEM."
            ),
            (
                "- `cem_preferred`: more paired seeds "
                "are safe under CEM than PINV; the nominal "
                "M2 routing choice reverses."
            ),
            (
                "- `tie`: the fixed-eta experiment does not "
                "distinguish the two controllers."
            ),
            (
                "- This is an operating-point stability test "
                "at eta=0.496, not a complete perturbed "
                "boundary comparison."
            ),
        ]
    )


    report_path.write_text(
        "\n".join(report)
        + "\n"
    )


    print(
        "condition_id,pairs,pinv_safe,cem_safe,"
        "pinv_only,cem_only,routing_state,mcnemar_p"
    )

    for row in pairwise_rows:
        print(
            f"{row['condition_id']},"
            f"{row['pairs_present']}/30,"
            f"{row['pinv_safe_count']},"
            f"{row['cem_safe_count']},"
            f"{row['pinv_only_safe']},"
            f"{row['cem_only_safe']},"
            f"{row['routing_state']},"
            f"{float(row['mcnemar_exact_p']):.6g}"
        )


    print()
    print(f"[SAVED] {trial_path}")
    print(f"[SAVED] {controller_path}")
    print(f"[SAVED] {pairwise_path}")
    print(f"[SAVED] {report_path}")


if __name__ == "__main__":
    main()
