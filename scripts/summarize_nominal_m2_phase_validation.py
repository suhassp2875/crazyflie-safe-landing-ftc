#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean


DEFAULT_ROOT = Path(
    "results/final/model_sensitivity/"
    "nominal_m2_boundary/phase_validation"
)


def as_bool(value: str) -> bool:
    return value.strip().lower() in {
        "true",
        "1",
        "yes",
    }


def as_float(
    row: dict[str, str],
    key: str,
) -> float:
    return float(row[key])


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
        / "phase_validation_schedule.csv"
    )

    summary_dir = (
        args.root / "summaries"
    )

    if not schedule_path.is_file():
        raise SystemExit(
            f"[FAIL] Missing {schedule_path}"
        )

    with schedule_path.open(
        newline=""
    ) as file:
        schedule = list(
            csv.DictReader(file)
        )

    expected = {
        (
            row["condition_id"],
            int(row["trial_seed"]),
        ): row
        for row in schedule
    }

    summary_rows = []

    for path in sorted(
        summary_dir.glob("*_summary.csv")
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
        row["_summary_path"] = str(path)
        summary_rows.append(row)

    observed: dict[
        tuple[str, int],
        dict[str, str],
    ] = {}

    for row in summary_rows:
        key = (
            row["condition_id"],
            int(row["trial_seed"]),
        )

        if key in observed:
            raise SystemExit(
                "[FAIL] Duplicate summary key: "
                f"{key}"
            )

        if key not in expected:
            raise SystemExit(
                "[FAIL] Unexpected summary key: "
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
            "[FAIL] Missing phase trials: "
            f"{len(missing)}"
        )

    completed_rows = [
        observed[key]
        for key in sorted(
            observed,
            key=lambda item: (
                item[0],
                item[1],
            ),
        )
    ]

    grouped = defaultdict(list)

    for row in completed_rows:
        grouped[
            row["condition_id"]
        ].append(row)

    condition_order = []

    for row in schedule:
        condition = row["condition_id"]

        if condition not in condition_order:
            condition_order.append(condition)

    aggregate_rows = []

    for condition_id in condition_order:
        expected_rows = [
            row
            for row in schedule
            if row["condition_id"]
            == condition_id
        ]

        rows = grouped.get(
            condition_id,
            [],
        )

        schedule_row = expected_rows[0]

        valid_count = sum(
            as_bool(row["valid_prefault"])
            for row in rows
        )

        contact_count = sum(
            as_bool(row["contact_found"])
            for row in rows
        )

        selector_match_count = sum(
            as_bool(row["selector_match"])
            for row in rows
        )

        safe_count = sum(
            as_bool(row["safe_touchdown"])
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
            not as_bool(row["tilt_ok"])
            for row in rows
        )

        angular_fail = sum(
            not as_bool(
                row["angular_rate_ok"]
            )
            for row in rows
        )

        drift_fail = sum(
            not as_bool(row["drift_ok"])
            for row in rows
        )

        lower, upper = wilson95(
            safe_count,
            len(rows),
        )

        vertical_values = [
            as_float(
                row,
                "vertical_speed_mps",
            )
            for row in rows
        ]

        angular_values = [
            as_float(
                row,
                "max_angular_rate_radps",
            )
            for row in rows
        ]

        candidate_counts = Counter(
            row[
                "selected_candidate_verified"
            ]
            for row in rows
        )

        aggregate_rows.append(
            {
                "condition_id":
                    condition_id,
                "controller": "cem",
                "motor": 2,
                "eta":
                    schedule_row["eta"],
                "expected_candidate":
                    schedule_row[
                        "expected_candidate"
                    ],
                "n_expected":
                    len(expected_rows),
                "n_present":
                    len(rows),
                "valid_prefault_count":
                    valid_count,
                "contact_count":
                    contact_count,
                "selector_match_count":
                    selector_match_count,
                "unique_selected_candidates":
                    len(candidate_counts),
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
        )

    combined_path = (
        args.root
        / "phase_validation_trial_summaries.csv"
    )

    aggregate_path = (
        args.root
        / "phase_validation_aggregate.csv"
    )

    report_path = (
        args.root
        / "phase_validation_report.md"
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

    report_lines = [
        "# Nominal M2 CEM Phase Validation",
        "",
        f"- Scheduled trials: {len(schedule)}",
        f"- Completed trials: {len(completed_rows)}",
        f"- Missing trials: {len(missing)}",
        "",
        "## Aggregate results",
        "",
        "| Phase | Eta | Candidate | Present | Safe | Vertical fail | Angular fail |",
        "|---|---:|---|---:|---:|---:|---:|",
    ]

    for row in aggregate_rows:
        report_lines.append(
            "| "
            f"{row['condition_id']} | "
            f"{row['eta']} | "
            f"{row['expected_candidate']} | "
            f"{row['n_present']}/"
            f"{row['n_expected']} | "
            f"{row['safe_count']} | "
            f"{row['vertical_fail']} | "
            f"{row['angular_fail']} |"
        )

    report_path.write_text(
        "\n".join(report_lines) + "\n"
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
            f"{row['expected_candidate']},"
            f"{row['n_present']}/"
            f"{row['n_expected']},"
            f"{row['safe_count']},"
            f"{row['vertical_fail']},"
            f"{row['angular_fail']}"
        )

    print()
    print(f"[SAVED] {aggregate_path}")
    print(f"[SAVED] {report_path}")

    if completed_rows:
        print(f"[SAVED] {combined_path}")


if __name__ == "__main__":
    main()
