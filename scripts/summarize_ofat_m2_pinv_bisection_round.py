#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean


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
        required=True,
    )

    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
    )

    args = parser.parse_args()

    schedule_path = (
        args.root
        / "ofat_bisection_schedule.csv"
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

    if len(schedule) != 50:
        raise SystemExit(
            "[FAIL] Expected 50 scheduled rows; "
            f"found {len(schedule)}."
        )

    round_values = {
        int(row["round"])
        for row in schedule
    }

    if len(round_values) != 1:
        raise SystemExit(
            "[FAIL] Schedule contains multiple "
            f"round numbers: {sorted(round_values)}"
        )

    round_number = next(iter(round_values))

    expected = {
        (
            row["condition_id"],
            round(float(row["eta"]), 6),
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
                "[FAIL] Expected one summary "
                f"row in {path}."
            )

        row = rows[0]

        key = (
            row["condition_id"],
            round(float(row["eta"]), 6),
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

        if condition_id not in condition_order:
            condition_order.append(
                condition_id
            )

    grouped = defaultdict(list)

    for key, row in observed.items():
        grouped[key[0]].append(row)

    result_rows = []
    updated_brackets = []

    for condition_id in condition_order:
        scheduled_rows = [
            row
            for row in schedule
            if row["condition_id"]
            == condition_id
        ]

        descriptor = scheduled_rows[0]

        rows = grouped.get(
            condition_id,
            [],
        )

        bracket_low = float(
            descriptor["bracket_low"]
        )

        bracket_high = float(
            descriptor["bracket_high"]
        )

        midpoint = float(
            descriptor["eta"]
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

        vertical_values = [
            float(
                row["vertical_speed_mps"]
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

        round_complete = (
            len(rows)
            == len(scheduled_rows)
        )

        if not round_complete:
            majority_safe = None
            decision = ""
            new_low = None
            new_high = None
        else:
            majority_safe = (
                safe_count >= 3
            )

            if majority_safe:
                new_low = bracket_low
                new_high = midpoint
                decision = (
                    "midpoint_majority_safe"
                )
            else:
                new_low = midpoint
                new_high = bracket_high
                decision = (
                    "midpoint_majority_unsafe"
                )

        result_rows.append(
            {
                "round":
                    descriptor["round"],
                "condition_id":
                    condition_id,
                "parameter":
                    descriptor["parameter"],
                "factor":
                    descriptor["factor"],
                "bracket_low":
                    f"{bracket_low:.6f}",
                "bracket_high":
                    f"{bracket_high:.6f}",
                "midpoint_eta":
                    f"{midpoint:.6f}",
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
                "majority_safe":
                    majority_safe
                    if round_complete
                    else "",
                "decision":
                    decision
                    if round_complete
                    else "",
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
                "mean_angular_rate_radps": (
                    mean(angular_values)
                    if angular_values
                    else ""
                ),
            }
        )

        updated_brackets.append(
            {
                "condition_id":
                    condition_id,
                "parameter":
                    descriptor["parameter"],
                "factor":
                    descriptor["factor"],
                "previous_low":
                    f"{bracket_low:.6f}",
                "previous_high":
                    f"{bracket_high:.6f}",
                "tested_midpoint":
                    f"{midpoint:.6f}",
                "safe_count":
                    safe_count,
                "n_present":
                    len(rows),
                "decision":
                    decision
                    if round_complete
                    else "",
                "updated_low":
                    f"{new_low:.6f}"
                    if round_complete
                    else "",
                "updated_high":
                    f"{new_high:.6f}"
                    if round_complete
                    else "",
                "updated_width":
                    f"{new_high - new_low:.6f}"
                    if round_complete
                    else "",
            }
        )

    result_path = (
        args.root
        / "ofat_bisection_results.csv"
    )

    bracket_path = (
        args.root
        / "ofat_bisection_updated_brackets.csv"
    )

    report_path = (
        args.root
        / "ofat_bisection_report.md"
    )

    write_csv(
        result_path,
        result_rows,
    )

    write_csv(
        bracket_path,
        updated_brackets,
    )

    report = [
        f"# M2 PINV OFAT Bisection Round {round_number}",
        "",
        f"- Scheduled trials: {len(schedule)}",
        f"- Completed trials: {len(observed)}",
        f"- Missing trials: {len(missing)}",
        "",
        "| Condition | Midpoint | Present | Safe | Decision | Updated bracket |",
        "|---|---:|---:|---:|---|---:|",
    ]

    for result, bracket in zip(
        result_rows,
        updated_brackets,
    ):
        report.append(
            "| "
            f"{result['condition_id']} | "
            f"{result['midpoint_eta']} | "
            f"{result['n_present']}/"
            f"{result['n_expected']} | "
            f"{result['safe_count']} | "
            f"{result['decision']} | "
            f"[{bracket['updated_low']}, "
            f"{bracket['updated_high']}] |"
        )

    report_path.write_text(
        "\n".join(report) + "\n"
    )

    print(
        "condition_id,midpoint,present,safe,"
        "decision,updated_low,updated_high"
    )

    for result, bracket in zip(
        result_rows,
        updated_brackets,
    ):
        print(
            f"{result['condition_id']},"
            f"{result['midpoint_eta']},"
            f"{result['n_present']}/"
            f"{result['n_expected']},"
            f"{result['safe_count']},"
            f"{result['decision']},"
            f"{bracket['updated_low']},"
            f"{bracket['updated_high']}"
        )

    print()
    print(f"[SAVED] {result_path}")
    print(f"[SAVED] {bracket_path}")
    print(f"[SAVED] {report_path}")


if __name__ == "__main__":
    main()
