#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from statistics import mean


DEFAULT_ROOT = Path(
    "results/final/model_sensitivity/"
    "nominal_m2_boundary/"
    "fixed_candidate_counterfactual"
)


def as_bool(value: str) -> bool:
    return value.strip().lower() in {
        "true",
        "1",
        "yes",
    }


def wilson95(
    successes: int,
    total: int,
) -> tuple[float, float]:
    if total == 0:
        return float("nan"), float("nan")

    z = 1.959963984540054
    proportion = successes / total

    denominator = (
        1.0 + z * z / total
    )

    center = (
        proportion
        + z * z / (2.0 * total)
    ) / denominator

    radius = (
        z
        / denominator
        * math.sqrt(
            proportion
            * (1.0 - proportion)
            / total
            + z * z
            / (4.0 * total * total)
        )
    )

    return (
        max(0.0, center - radius),
        min(1.0, center + radius),
    )


def exact_mcnemar(
    a_safe_b_unsafe: int,
    a_unsafe_b_safe: int,
) -> float:
    discordant = (
        a_safe_b_unsafe
        + a_unsafe_b_safe
    )

    if discordant == 0:
        return 1.0

    lower = min(
        a_safe_b_unsafe,
        a_unsafe_b_safe,
    )

    probability = sum(
        math.comb(
            discordant,
            index,
        )
        for index in range(
            lower + 1
        )
    ) / (2 ** discordant)

    return min(
        1.0,
        2.0 * probability,
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
        / "fixed_candidate_schedule.csv"
    )

    summary_dir = (
        args.root / "summaries"
    )

    with schedule_path.open(
        newline=""
    ) as file:
        schedule = list(
            csv.DictReader(file)
        )

    if len(schedule) != 90:
        raise SystemExit(
            "[FAIL] Expected 90 schedule rows; "
            f"found {len(schedule)}."
        )

    expected = {
        (
            row["condition_id"],
            int(row["trial_seed"]),
        ): row
        for row in schedule
    }

    observed = {}

    for path in sorted(
        summary_dir.glob(
            "*_summary.csv"
        )
    ):
        with path.open(newline="") as file:
            rows = list(
                csv.DictReader(file)
            )

        if len(rows) != 1:
            raise SystemExit(
                f"[FAIL] Expected one row in {path}"
            )

        row = rows[0]

        key = (
            row["condition_id"],
            int(row["trial_seed"]),
        )

        if key not in expected:
            raise SystemExit(
                "[FAIL] Unexpected summary: "
                f"{key}"
            )

        if key in observed:
            raise SystemExit(
                "[FAIL] Duplicate summary: "
                f"{key}"
            )

        observed[key] = row

    missing = sorted(
        set(expected) - set(observed)
    )

    if (
        missing
        and not args.allow_incomplete
    ):
        raise SystemExit(
            "[FAIL] Missing completed trials: "
            f"{len(missing)}"
        )

    condition_order = []

    for row in schedule:
        condition = row["condition_id"]

        if condition not in condition_order:
            condition_order.append(
                condition
            )

    completed_rows = [
        observed[key]
        for key in sorted(
            observed,
            key=lambda item: (
                condition_order.index(
                    item[0]
                ),
                item[1],
            ),
        )
    ]

    grouped = defaultdict(list)

    for row in completed_rows:
        grouped[
            row["condition_id"]
        ].append(row)

    aggregate_rows = []

    for condition_id in condition_order:
        scheduled_rows = [
            row
            for row in schedule
            if row["condition_id"]
            == condition_id
        ]

        rows = grouped.get(
            condition_id,
            [],
        )

        schedule_row = scheduled_rows[0]

        safe_count = sum(
            as_bool(
                row["safe_touchdown"]
            )
            for row in rows
        )

        lower, upper = wilson95(
            safe_count,
            len(rows),
        )

        vertical_values = [
            float(
                row[
                    "vertical_speed_mps"
                ]
            )
            for row in rows
        ]

        angular_values = [
            float(
                row[
                    "max_angular_rate_radps"
                ]
            )
            for row in rows
        ]

        candidates = Counter(
            row[
                "selected_candidate_verified"
            ]
            for row in rows
        )

        aggregate_rows.append(
            {
                "condition_id":
                    condition_id,
                "controller": "manual",
                "motor": 2,
                "eta":
                    schedule_row["eta"],
                "candidate":
                    schedule_row[
                        "expected_candidate"
                    ],
                "r1":
                    schedule_row[
                        "expected_r1"
                    ],
                "r2":
                    schedule_row[
                        "expected_r2"
                    ],
                "r3":
                    schedule_row[
                        "expected_r3"
                    ],
                "r4":
                    schedule_row[
                        "expected_r4"
                    ],
                "n_expected":
                    len(scheduled_rows),
                "n_present":
                    len(rows),
                "valid_prefault_count":
                    sum(
                        as_bool(
                            row[
                                "valid_prefault"
                            ]
                        )
                        for row in rows
                    ),
                "contact_count":
                    sum(
                        as_bool(
                            row[
                                "contact_found"
                            ]
                        )
                        for row in rows
                    ),
                "policy_match_count":
                    sum(
                        as_bool(
                            row[
                                "policy_match"
                            ]
                        )
                        for row in rows
                    ),
                "unique_candidates":
                    len(candidates),
                "safe_count":
                    safe_count,
                "safe_rate": (
                    safe_count / len(rows)
                    if rows
                    else ""
                ),
                "wilson95_lower": (
                    lower
                    if rows
                    else ""
                ),
                "wilson95_upper": (
                    upper
                    if rows
                    else ""
                ),
                "vertical_fail":
                    sum(
                        not as_bool(
                            row[
                                "vertical_speed_ok"
                            ]
                        )
                        for row in rows
                    ),
                "horizontal_fail":
                    sum(
                        not as_bool(
                            row[
                                "horizontal_speed_ok"
                            ]
                        )
                        for row in rows
                    ),
                "tilt_fail":
                    sum(
                        not as_bool(
                            row["tilt_ok"]
                        )
                        for row in rows
                    ),
                "angular_fail":
                    sum(
                        not as_bool(
                            row[
                                "angular_rate_ok"
                            ]
                        )
                        for row in rows
                    ),
                "drift_fail":
                    sum(
                        not as_bool(
                            row["drift_ok"]
                        )
                        for row in rows
                    ),
                "mean_vertical_speed_mps": (
                    mean(vertical_values)
                    if vertical_values
                    else ""
                ),
                "max_vertical_speed_mps": (
                    max(vertical_values)
                    if vertical_values
                    else ""
                ),
                "mean_angular_rate_radps": (
                    mean(angular_values)
                    if angular_values
                    else ""
                ),
                "max_angular_rate_radps": (
                    max(angular_values)
                    if angular_values
                    else ""
                ),
            }
        )

    by_condition_seed = {
        condition: {
            int(row["trial_seed"]):
                row
            for row in grouped.get(
                condition,
                [],
            )
        }
        for condition in condition_order
    }

    pairwise_rows = []

    for condition_a, condition_b in combinations(
        condition_order,
        2,
    ):
        rows_a = by_condition_seed[
            condition_a
        ]

        rows_b = by_condition_seed[
            condition_b
        ]

        common_seeds = sorted(
            set(rows_a) & set(rows_b)
        )

        a_safe_b_unsafe = 0
        a_unsafe_b_safe = 0
        both_safe = 0
        both_unsafe = 0

        vertical_differences = []
        angular_differences = []

        for seed in common_seeds:
            row_a = rows_a[seed]
            row_b = rows_b[seed]

            safe_a = as_bool(
                row_a["safe_touchdown"]
            )

            safe_b = as_bool(
                row_b["safe_touchdown"]
            )

            if safe_a and safe_b:
                both_safe += 1
            elif safe_a and not safe_b:
                a_safe_b_unsafe += 1
            elif not safe_a and safe_b:
                a_unsafe_b_safe += 1
            else:
                both_unsafe += 1

            vertical_differences.append(
                float(
                    row_a[
                        "vertical_speed_mps"
                    ]
                )
                - float(
                    row_b[
                        "vertical_speed_mps"
                    ]
                )
            )

            angular_differences.append(
                float(
                    row_a[
                        "max_angular_rate_radps"
                    ]
                )
                - float(
                    row_b[
                        "max_angular_rate_radps"
                    ]
                )
            )

        pairwise_rows.append(
            {
                "condition_a":
                    condition_a,
                "condition_b":
                    condition_b,
                "paired_n":
                    len(common_seeds),
                "both_safe":
                    both_safe,
                "both_unsafe":
                    both_unsafe,
                "a_safe_b_unsafe":
                    a_safe_b_unsafe,
                "a_unsafe_b_safe":
                    a_unsafe_b_safe,
                "safe_rate_difference_a_minus_b":
                    (
                        (
                            a_safe_b_unsafe
                            - a_unsafe_b_safe
                        )
                        / len(common_seeds)
                        if common_seeds
                        else ""
                    ),
                "exact_mcnemar_p":
                    exact_mcnemar(
                        a_safe_b_unsafe,
                        a_unsafe_b_safe,
                    ),
                "mean_vertical_speed_difference_a_minus_b":
                    (
                        mean(
                            vertical_differences
                        )
                        if vertical_differences
                        else ""
                    ),
                "mean_angular_rate_difference_a_minus_b":
                    (
                        mean(
                            angular_differences
                        )
                        if angular_differences
                        else ""
                    ),
            }
        )

    combined_path = (
        args.root
        / "fixed_candidate_trial_summaries.csv"
    )

    aggregate_path = (
        args.root
        / "fixed_candidate_aggregate.csv"
    )

    pairwise_path = (
        args.root
        / "fixed_candidate_pairwise.csv"
    )

    report_path = (
        args.root
        / "fixed_candidate_report.md"
    )

    if completed_rows:
        write_csv(
            combined_path,
            completed_rows,
        )

    write_csv(
        aggregate_path,
        aggregate_rows,
    )

    write_csv(
        pairwise_path,
        pairwise_rows,
    )

    report = [
        "# Nominal M2 Fixed-Candidate Counterfactual",
        "",
        "- Common eta: 0.499675",
        f"- Scheduled trials: {len(schedule)}",
        f"- Completed trials: {len(completed_rows)}",
        f"- Missing trials: {len(missing)}",
        "",
        "## Aggregate results",
        "",
        "| Condition | Candidate | Present | Safe | Vertical fail | Angular fail |",
        "|---|---|---:|---:|---:|---:|",
    ]

    for row in aggregate_rows:
        report.append(
            "| "
            f"{row['condition_id']} | "
            f"{row['candidate']} | "
            f"{row['n_present']}/"
            f"{row['n_expected']} | "
            f"{row['safe_count']} | "
            f"{row['vertical_fail']} | "
            f"{row['angular_fail']} |"
        )

    report.extend(
        [
            "",
            "## Paired comparisons",
            "",
            "| A | B | Paired n | A safe/B unsafe | A unsafe/B safe | McNemar p |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )

    for row in pairwise_rows:
        report.append(
            "| "
            f"{row['condition_a']} | "
            f"{row['condition_b']} | "
            f"{row['paired_n']} | "
            f"{row['a_safe_b_unsafe']} | "
            f"{row['a_unsafe_b_safe']} | "
            f"{row['exact_mcnemar_p']} |"
        )

    report_path.write_text(
        "\n".join(report) + "\n"
    )

    print(
        "condition_id,eta,candidate,"
        "present,safe,vertical_fail,"
        "angular_fail"
    )

    for row in aggregate_rows:
        print(
            f"{row['condition_id']},"
            f"{row['eta']},"
            f"{row['candidate']},"
            f"{row['n_present']}/"
            f"{row['n_expected']},"
            f"{row['safe_count']},"
            f"{row['vertical_fail']},"
            f"{row['angular_fail']}"
        )

    print()
    print(f"[SAVED] {aggregate_path}")
    print(f"[SAVED] {pairwise_path}")
    print(f"[SAVED] {report_path}")

    if completed_rows:
        print(f"[SAVED] {combined_path}")


if __name__ == "__main__":
    main()
