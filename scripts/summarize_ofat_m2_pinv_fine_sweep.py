#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean


DEFAULT_ROOT = Path(
    "results/final/model_sensitivity/ofat/"
    "pinv_boundary_fine_sweep"
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
        / "ofat_fine_schedule.csv"
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

    if len(schedule) != 2100:
        raise SystemExit(
            "[FAIL] Expected 2100 schedule rows; "
            f"found {len(schedule)}."
        )

    expected = {
        (
            row["condition_id"],
            round(float(row["eta"]), 8),
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

        condition_id = row[
            "condition_id"
        ]

        trial_seed = int(
            row["trial_seed"]
        )

        observed_eta = float(
            row["eta"]
        )

        candidates = [
            schedule_row
            for schedule_row in schedule
            if (
                schedule_row["condition_id"]
                == condition_id
                and int(
                    schedule_row["trial_seed"]
                )
                == trial_seed
            )
        ]

        if len(candidates) != 7:
            raise SystemExit(
                "[FAIL] Expected seven scheduled "
                "eta candidates for "
                f"condition={condition_id}, "
                f"seed={trial_seed}; "
                f"found {len(candidates)}."
            )

        matched = min(
            candidates,
            key=lambda schedule_row: abs(
                float(schedule_row["eta"])
                - observed_eta
            ),
        )

        scheduled_eta = float(
            matched["eta"]
        )

        eta_match_error = abs(
            scheduled_eta
            - observed_eta
        )

        # Existing validator summaries rounded eta
        # to six decimals. The largest expected
        # quantization error is < 5e-7. Keep a
        # conservative 1e-6 matching tolerance,
        # still far below the ~1.04e-3 grid spacing.
        if eta_match_error > 1.0e-6:
            raise SystemExit(
                "[FAIL] Summary eta does not match "
                "any scheduled eta within tolerance: "
                f"condition={condition_id}, "
                f"seed={trial_seed}, "
                f"summary_eta={observed_eta:.9f}, "
                f"nearest_schedule_eta="
                f"{scheduled_eta:.9f}, "
                f"error={eta_match_error:.3e}"
            )

        key = (
            condition_id,
            round(scheduled_eta, 8),
            trial_seed,
        )

        if key not in expected:
            raise SystemExit(
                "[FAIL] Canonicalized summary key "
                f"is not scheduled: {key}"
            )

        if key in observed:
            raise SystemExit(
                "[FAIL] Duplicate canonicalized "
                f"summary key: {key}"
            )

        # Restore the exact scheduled eta so all
        # downstream analyses retain the designed
        # eight-decimal grid rather than the
        # validator's historical six-decimal value.
        row = dict(row)
        row["eta"] = matched["eta"]

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
        grouped[
            (
                key[0],
                key[1],
            )
        ].append(row)

    aggregate_rows = []
    condition_rows = []
    monotonicity_rows = []

    for condition_id in condition_order:
        scheduled_condition = [
            row
            for row in schedule
            if row["condition_id"]
            == condition_id
        ]

        descriptor = scheduled_condition[0]

        eta_values = sorted(
            {
                round(
                    float(row["eta"]),
                    8,
                )
                for row
                in scheduled_condition
            }
        )

        condition_aggregates = []

        for eta in eta_values:
            scheduled_eta_rows = [
                row
                for row
                in scheduled_condition
                if round(
                    float(row["eta"]),
                    8,
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

            aggregate = {
                "condition_id":
                    condition_id,
                "parameter":
                    descriptor["parameter"],
                "factor":
                    descriptor["factor"],
                "controller":
                    "pinv",
                "motor":
                    2,
                "eta":
                    f"{eta:.8f}",
                "n_expected":
                    len(scheduled_eta_rows),
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

        available = [
            row
            for row
            in condition_aggregates
            if row["n_present"] > 0
        ]

        for previous, current in zip(
            available,
            available[1:],
        ):
            if (
                current["safe_rate"]
                < previous["safe_rate"]
            ):
                monotonicity_rows.append(
                    {
                        "condition_id":
                            condition_id,
                        "eta_previous":
                            previous["eta"],
                        "safe_rate_previous":
                            previous["safe_rate"],
                        "eta_current":
                            current["eta"],
                        "safe_rate_current":
                            current["safe_rate"],
                        "drop":
                            previous["safe_rate"]
                            - current["safe_rate"],
                    }
                )

        condition_rows.append(
            {
                "condition_id":
                    condition_id,
                "parameter":
                    descriptor["parameter"],
                "factor":
                    descriptor["factor"],
                "n_expected":
                    len(scheduled_condition),
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
                "safe_count":
                    sum(
                        row["safe_count"]
                        for row
                        in condition_aggregates
                    ),
                "minimum_safe_rate":
                    min(
                        (
                            row["safe_rate"]
                            for row in available
                        ),
                        default="",
                    ),
                "maximum_safe_rate":
                    max(
                        (
                            row["safe_rate"]
                            for row in available
                        ),
                        default="",
                    ),
                "monotonicity_violations":
                    sum(
                        row["condition_id"]
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
                        row["horizontal_fail"]
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

    completed_rows = [
        observed[key]
        for key in sorted(
            observed,
            key=lambda item: (
                condition_order.index(
                    item[0]
                ),
                item[1],
                item[2],
            ),
        )
    ]

    trial_path = (
        args.root
        / "ofat_fine_trial_summaries.csv"
    )

    aggregate_path = (
        args.root
        / "ofat_fine_aggregate.csv"
    )

    condition_path = (
        args.root
        / "ofat_fine_condition_summary.csv"
    )

    monotonicity_path = (
        args.root
        / "ofat_fine_monotonicity.csv"
    )

    report_path = (
        args.root
        / "ofat_fine_report.md"
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
        "# M2 PINV OFAT Fine Boundary Sweep",
        "",
        f"- Scheduled trials: {len(schedule)}",
        f"- Completed trials: {len(observed)}",
        f"- Missing trials: {len(missing)}",
        "",
        "| Condition | Present | Valid | Contact | Safe | Monotonicity violations |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for row in condition_rows:
        report.append(
            "| "
            f"{row['condition_id']} | "
            f"{row['n_present']}/"
            f"{row['n_expected']} | "
            f"{row['valid_prefault_count']} | "
            f"{row['contact_count']} | "
            f"{row['safe_count']} | "
            f"{row['monotonicity_violations']} |"
        )

    report_path.write_text(
        "\n".join(report) + "\n"
    )

    print(
        "condition_id,present,valid,contact,"
        "safe,monotonicity_violations"
    )

    for row in condition_rows:
        print(
            f"{row['condition_id']},"
            f"{row['n_present']}/"
            f"{row['n_expected']},"
            f"{row['valid_prefault_count']},"
            f"{row['contact_count']},"
            f"{row['safe_count']},"
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
