#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean


DEFAULT_ROOT = Path(
    "results/final/model_sensitivity/ofat/"
    "pinv_boundary_localization"
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
        / "ofat_localization_schedule.csv"
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

    if len(schedule) != 350:
        raise SystemExit(
            "[FAIL] Expected 350 schedule rows; "
            f"found {len(schedule)}."
        )

    expected = {
        (
            row["condition_id"],
            round(float(row["eta"]), 3),
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
        with path.open(
            newline=""
        ) as file:
            rows = list(
                csv.DictReader(file)
            )

        if len(rows) != 1:
            raise SystemExit(
                f"[FAIL] Expected one row "
                f"in {path}."
            )

        row = rows[0]

        key = (
            row["condition_id"],
            round(float(row["eta"]), 3),
            int(row["trial_seed"]),
        )

        if key not in expected:
            raise SystemExit(
                "[FAIL] Unexpected summary "
                f"key: {key}"
            )

        if key in observed:
            raise SystemExit(
                "[FAIL] Duplicate summary "
                f"key: {key}"
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
        condition_id = row[
            "condition_id"
        ]

        if (
            condition_id
            not in condition_order
        ):
            condition_order.append(
                condition_id
            )

    completed_rows = [
        observed[key]
        for key in sorted(
            observed,
            key=lambda key: (
                condition_order.index(
                    key[0]
                ),
                key[1],
                key[2],
            ),
        )
    ]

    grouped = defaultdict(list)

    for row in completed_rows:
        grouped[
            (
                row["condition_id"],
                round(
                    float(row["eta"]),
                    3,
                ),
            )
        ].append(row)

    aggregate_rows = []
    monotonicity_rows = []
    condition_rows = []

    for condition_id in condition_order:
        scheduled_condition = [
            row
            for row in schedule
            if row["condition_id"]
            == condition_id
        ]

        parameter = scheduled_condition[
            0
        ]["parameter"]

        factor = scheduled_condition[
            0
        ]["factor"]

        eta_order = sorted(
            {
                round(
                    float(row["eta"]),
                    3,
                )
                for row
                in scheduled_condition
            }
        )

        condition_aggregates = []

        for eta in eta_order:
            scheduled_rows = [
                row
                for row
                in scheduled_condition
                if round(
                    float(row["eta"]),
                    3,
                )
                == eta
            ]

            rows = grouped.get(
                (
                    condition_id,
                    eta,
                ),
                [],
            )

            safe_count = sum(
                as_bool(
                    row["safe_touchdown"]
                )
                for row in rows
            )

            valid_count = sum(
                as_bool(
                    row["valid_prefault"]
                )
                for row in rows
            )

            contact_count = sum(
                as_bool(
                    row["contact_found"]
                )
                for row in rows
            )

            vertical_fail = sum(
                not as_bool(
                    row[
                        "vertical_speed_ok"
                    ]
                )
                for row in rows
            )

            horizontal_fail = sum(
                not as_bool(
                    row[
                        "horizontal_speed_ok"
                    ]
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
                    row[
                        "angular_rate_ok"
                    ]
                )
                for row in rows
            )

            drift_fail = sum(
                not as_bool(
                    row["drift_ok"]
                )
                for row in rows
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

            aggregate = {
                "condition_id":
                    condition_id,
                "parameter":
                    parameter,
                "factor":
                    factor,
                "controller":
                    "pinv",
                "motor":
                    2,
                "eta":
                    f"{eta:.3f}",
                "n_expected":
                    len(scheduled_rows),
                "n_present":
                    len(rows),
                "valid_prefault_count":
                    valid_count,
                "contact_count":
                    contact_count,
                "safe_count":
                    safe_count,
                "safe_rate": (
                    safe_count / len(rows)
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

            aggregate_rows.append(
                aggregate
            )

            condition_aggregates.append(
                aggregate
            )

        for previous, current in zip(
            condition_aggregates,
            condition_aggregates[1:],
        ):
            if (
                previous["n_present"] > 0
                and current["n_present"] > 0
                and current["safe_rate"]
                < previous["safe_rate"]
            ):
                monotonicity_rows.append(
                    {
                        "condition_id":
                            condition_id,
                        "eta_previous":
                            previous["eta"],
                        "safe_rate_previous":
                            previous[
                                "safe_rate"
                            ],
                        "eta_current":
                            current["eta"],
                        "safe_rate_current":
                            current[
                                "safe_rate"
                            ],
                        "drop":
                            previous[
                                "safe_rate"
                            ]
                            - current[
                                "safe_rate"
                            ],
                    }
                )

        available = [
            row
            for row
            in condition_aggregates
            if row["n_present"] > 0
        ]

        crossing_index = None

        for index, row in enumerate(
            available
        ):
            if row["safe_rate"] >= 0.5:
                crossing_index = index
                break

        bracket_status = ""
        bracket_low = ""
        bracket_high = ""

        if not available:
            bracket_status = "no_data"
        elif crossing_index is None:
            bracket_status = (
                "right_censored"
            )
            bracket_low = available[
                -1
            ]["eta"]
        elif crossing_index == 0:
            bracket_status = (
                "left_censored"
            )
            bracket_high = available[
                0
            ]["eta"]
        else:
            bracket_status = "bracketed"
            bracket_low = available[
                crossing_index - 1
            ]["eta"]
            bracket_high = available[
                crossing_index
            ]["eta"]

        condition_rows.append(
            {
                "condition_id":
                    condition_id,
                "parameter":
                    parameter,
                "factor":
                    factor,
                "n_expected":
                    len(
                        scheduled_condition
                    ),
                "n_present":
                    sum(
                        row["n_present"]
                        for row
                        in condition_aggregates
                    ),
                "valid_prefault_count":
                    sum(
                        row[
                            "valid_prefault_count"
                        ]
                        for row
                        in condition_aggregates
                    ),
                "contact_count":
                    sum(
                        row["contact_count"]
                        for row
                        in condition_aggregates
                    ),
                "minimum_safe_rate":
                    min(
                        (
                            row["safe_rate"]
                            for row
                            in available
                        ),
                        default="",
                    ),
                "maximum_safe_rate":
                    max(
                        (
                            row["safe_rate"]
                            for row
                            in available
                        ),
                        default="",
                    ),
                "majority_bracket_status":
                    bracket_status,
                "majority_bracket_eta_low":
                    bracket_low,
                "majority_bracket_eta_high":
                    bracket_high,
                "monotonicity_violations":
                    sum(
                        row[
                            "condition_id"
                        ]
                        == condition_id
                        for row
                        in monotonicity_rows
                    ),
                "vertical_fail_total":
                    sum(
                        row["vertical_fail"]
                        for row
                        in condition_aggregates
                    ),
                "horizontal_fail_total":
                    sum(
                        row[
                            "horizontal_fail"
                        ]
                        for row
                        in condition_aggregates
                    ),
                "tilt_fail_total":
                    sum(
                        row["tilt_fail"]
                        for row
                        in condition_aggregates
                    ),
                "angular_fail_total":
                    sum(
                        row["angular_fail"]
                        for row
                        in condition_aggregates
                    ),
                "drift_fail_total":
                    sum(
                        row["drift_fail"]
                        for row
                        in condition_aggregates
                    ),
            }
        )

    trial_path = (
        args.root
        / "ofat_localization_trial_summaries.csv"
    )

    aggregate_path = (
        args.root
        / "ofat_localization_aggregate.csv"
    )

    condition_path = (
        args.root
        / "ofat_localization_condition_summary.csv"
    )

    monotonicity_path = (
        args.root
        / "ofat_localization_monotonicity.csv"
    )

    report_path = (
        args.root
        / "ofat_localization_report.md"
    )

    if completed_rows:
        write_csv(
            trial_path,
            completed_rows,
        )

    write_csv(
        aggregate_path,
        aggregate_rows,
    )

    write_csv(
        condition_path,
        condition_rows,
    )

    if monotonicity_rows:
        write_csv(
            monotonicity_path,
            monotonicity_rows,
        )
    else:
        monotonicity_path.write_text(
            "condition_id,eta_previous,"
            "safe_rate_previous,eta_current,"
            "safe_rate_current,drop\n"
        )

    report = [
        "# M2 PINV OFAT Boundary Localization",
        "",
        f"- Scheduled trials: {len(schedule)}",
        f"- Completed trials: {len(completed_rows)}",
        f"- Missing trials: {len(missing)}",
        "",
        "## Condition-level brackets",
        "",
        "| Condition | Parameter | Factor | Present | Status | Eta low | Eta high | Monotonicity violations |",
        "|---|---|---:|---:|---|---:|---:|---:|",
    ]

    for row in condition_rows:
        report.append(
            "| "
            f"{row['condition_id']} | "
            f"{row['parameter']} | "
            f"{row['factor']} | "
            f"{row['n_present']}/"
            f"{row['n_expected']} | "
            f"{row['majority_bracket_status']} | "
            f"{row['majority_bracket_eta_low']} | "
            f"{row['majority_bracket_eta_high']} | "
            f"{row['monotonicity_violations']} |"
        )

    report_path.write_text(
        "\n".join(report) + "\n"
    )

    print(
        "condition_id,parameter,factor,"
        "present,status,eta_low,eta_high,"
        "monotonicity_violations"
    )

    for row in condition_rows:
        print(
            f"{row['condition_id']},"
            f"{row['parameter']},"
            f"{row['factor']},"
            f"{row['n_present']}/"
            f"{row['n_expected']},"
            f"{row['majority_bracket_status']},"
            f"{row['majority_bracket_eta_low']},"
            f"{row['majority_bracket_eta_high']},"
            f"{row['monotonicity_violations']}"
        )

    print()
    print(f"[SAVED] {aggregate_path}")
    print(f"[SAVED] {condition_path}")
    print(f"[SAVED] {monotonicity_path}")
    print(f"[SAVED] {report_path}")

    if completed_rows:
        print(f"[SAVED] {trial_path}")


if __name__ == "__main__":
    main()
