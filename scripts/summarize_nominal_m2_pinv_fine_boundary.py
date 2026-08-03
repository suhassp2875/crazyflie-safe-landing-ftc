#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean


DEFAULT_ROOT = Path(
    "results/final/model_sensitivity/"
    "nominal_m2_boundary/pinv_fine_boundary"
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


def eta_key(value: str | float) -> float:
    return round(
        float(value),
        5,
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
        args.root / "pinv_fine_schedule.csv"
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

    if len(schedule) != 210:
        raise SystemExit(
            "[FAIL] Expected 210 scheduled rows; "
            f"found {len(schedule)}."
        )

    expected = {
        (
            eta_key(row["eta"]),
            int(row["trial_seed"]),
        ): row
        for row in schedule
    }

    observed: dict[
        tuple[float, int],
        dict[str, str],
    ] = {}

    for path in sorted(
        summary_dir.glob("*_summary.csv")
    ):
        with path.open(
            newline=""
        ) as file:
            rows = list(
                csv.DictReader(file)
            )

        if len(rows) != 1:
            raise SystemExit(
                f"[FAIL] Expected exactly one "
                f"row in {path}"
            )

        row = rows[0]

        key = (
            eta_key(row["eta"]),
            int(row["trial_seed"]),
        )

        if key not in expected:
            raise SystemExit(
                "[FAIL] Unexpected summary key: "
                f"{key}"
            )

        if key in observed:
            raise SystemExit(
                "[FAIL] Duplicate summary key: "
                f"{key}"
            )

        row["_summary_path"] = str(path)
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

    eta_order = sorted(
        {
            eta_key(row["eta"])
            for row in schedule
        }
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
            eta_key(row["eta"])
        ].append(row)

    aggregate_rows = []

    for eta in eta_order:
        scheduled_rows = [
            row
            for row in schedule
            if eta_key(row["eta"]) == eta
        ]

        rows = grouped.get(
            eta,
            [],
        )

        valid_count = sum(
            as_bool(row["valid_prefault"])
            for row in rows
        )

        contact_count = sum(
            as_bool(row["contact_found"])
            for row in rows
        )

        safe_count = sum(
            as_bool(row["safe_touchdown"])
            for row in rows
        )

        lower, upper = wilson95(
            safe_count,
            len(rows),
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

        aggregate_rows.append(
            {
                "controller":
                    "pinv",
                "motor":
                    2,
                "eta":
                    f"{eta:.5f}",
                "n_expected":
                    len(scheduled_rows),
                "n_present":
                    len(rows),
                "valid_prefault_count":
                    valid_count,
                "valid_prefault_rate": (
                    valid_count / len(rows)
                    if rows
                    else ""
                ),
                "contact_count":
                    contact_count,
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
                "min_vertical_speed_mps": (
                    min(vertical_values)
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

    monotonicity_violations = []

    complete_aggregates = [
        row
        for row in aggregate_rows
        if row["n_present"] > 0
    ]

    for previous, current in zip(
        complete_aggregates,
        complete_aggregates[1:],
    ):
        if (
            current["safe_rate"]
            < previous["safe_rate"]
        ):
            monotonicity_violations.append(
                {
                    "eta_previous":
                        previous["eta"],
                    "safe_rate_previous":
                        previous["safe_rate"],
                    "eta_current":
                        current["eta"],
                    "safe_rate_current":
                        current["safe_rate"],
                    "drop":
                        (
                            previous["safe_rate"]
                            - current["safe_rate"]
                        ),
                }
            )

    combined_path = (
        args.root
        / "pinv_fine_trial_summaries.csv"
    )

    aggregate_path = (
        args.root
        / "pinv_fine_aggregate.csv"
    )

    monotonicity_path = (
        args.root
        / "pinv_fine_monotonicity.csv"
    )

    report_path = (
        args.root
        / "pinv_fine_report.md"
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

    if monotonicity_violations:
        write_csv(
            monotonicity_path,
            monotonicity_violations,
        )
    else:
        monotonicity_path.write_text(
            "eta_previous,safe_rate_previous,"
            "eta_current,safe_rate_current,drop\n"
        )

    report = [
        "# Nominal M2 PINV Fine Boundary",
        "",
        f"- Scheduled trials: {len(schedule)}",
        f"- Completed trials: {len(completed_rows)}",
        f"- Missing trials: {len(missing)}",
        (
            "- Empirical safe-rate monotonicity "
            f"violations: "
            f"{len(monotonicity_violations)}"
        ),
        "",
        "## Aggregate results",
        "",
        "| Eta | Present | Valid | Contact | Safe | Vertical fail | Angular fail |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for row in aggregate_rows:
        report.append(
            "| "
            f"{row['eta']} | "
            f"{row['n_present']}/"
            f"{row['n_expected']} | "
            f"{row['valid_prefault_count']} | "
            f"{row['contact_count']} | "
            f"{row['safe_count']} | "
            f"{row['vertical_fail']} | "
            f"{row['angular_fail']} |"
        )

    report_path.write_text(
        "\n".join(report) + "\n"
    )

    print(
        "eta,present,valid,contact,safe,"
        "vertical_fail,angular_fail"
    )

    for row in aggregate_rows:
        print(
            f"{row['eta']},"
            f"{row['n_present']}/"
            f"{row['n_expected']},"
            f"{row['valid_prefault_count']},"
            f"{row['contact_count']},"
            f"{row['safe_count']},"
            f"{row['vertical_fail']},"
            f"{row['angular_fail']}"
        )

    print()
    print(
        "monotonicity_violations="
        f"{len(monotonicity_violations)}"
    )
    print(f"[SAVED] {aggregate_path}")
    print(f"[SAVED] {monotonicity_path}")
    print(f"[SAVED] {report_path}")

    if completed_rows:
        print(f"[SAVED] {combined_path}")


if __name__ == "__main__":
    main()
