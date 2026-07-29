#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


ROOT = Path(
    "results/final/model_sensitivity/"
    "nominal_m2_boundary/localization"
)

SCHEDULE = ROOT / "schedule.csv"
SUMMARY_DIR = ROOT / "summaries"


def as_bool(value: str) -> bool:
    return value.strip().lower() in {
        "true",
        "1",
        "yes",
    }


def optional_float(
    value: str,
) -> float | None:
    cleaned = value.strip()

    if cleaned == "":
        return None

    return float(cleaned)


def wilson(
    successes: int,
    n: int,
    z: float = 1.96,
) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")

    p = successes / n
    denominator = 1.0 + z * z / n

    center = (
        p + z * z / (2.0 * n)
    ) / denominator

    half = (
        z
        * math.sqrt(
            p * (1.0 - p) / n
            + z * z / (4.0 * n * n)
        )
        / denominator
    )

    return (
        max(0.0, center - half),
        min(1.0, center + half),
    )


def eta_tag(eta: float) -> str:
    return f"{eta:.3f}".replace(
        ".",
        "p",
    )


def trial_tag(
    controller: str,
    eta: float,
    seed: int,
) -> str:
    return (
        "nominal_m2loc_"
        f"{controller}_"
        f"eta{eta_tag(eta)}_"
        f"seed{seed}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-complete",
        action="store_true",
    )
    args = parser.parse_args()

    if not SCHEDULE.is_file():
        raise SystemExit(
            f"[FAIL] Missing schedule: {SCHEDULE}"
        )

    with SCHEDULE.open(newline="") as file:
        schedule_rows = list(
            csv.DictReader(file)
        )

    expected = []

    for row in schedule_rows:
        controller = row[
            "controller"
        ].strip()

        eta = float(row["eta"])
        seed = int(row["trial_seed"])

        tag = trial_tag(
            controller,
            eta,
            seed,
        )

        expected.append(
            {
                **row,
                "tag": tag,
                "summary_path":
                    SUMMARY_DIR
                    / f"{tag}_summary.csv",
            }
        )

    trial_rows = []
    missing = []

    for item in expected:
        path = item["summary_path"]

        if not path.is_file():
            missing.append(item)
            continue

        with path.open(newline="") as file:
            rows = list(csv.DictReader(file))

        if len(rows) != 1:
            raise SystemExit(
                f"[FAIL] Expected one row in {path}; "
                f"found {len(rows)}."
            )

        row = rows[0]

        if (
            row["controller"]
            != item["controller"]
        ):
            raise SystemExit(
                f"[FAIL] Controller mismatch in {path}"
            )

        if int(row["trial_seed"]) != int(
            item["trial_seed"]
        ):
            raise SystemExit(
                f"[FAIL] Seed mismatch in {path}"
            )

        if abs(
            float(row["eta"])
            - float(item["eta"])
        ) > 1.0e-9:
            raise SystemExit(
                f"[FAIL] Eta mismatch in {path}"
            )

        trial_rows.append(row)

    trial_output = (
        ROOT
        / "localization_trial_summaries.csv"
    )

    if trial_rows:
        fieldnames = list(trial_rows[0])

        with trial_output.open(
            "w",
            newline="",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames,
            )
            writer.writeheader()
            writer.writerows(trial_rows)

    grouped = defaultdict(list)

    for row in trial_rows:
        key = (
            row["controller"],
            float(row["eta"]),
        )

        grouped[key].append(row)

    expected_counts = defaultdict(int)

    for item in expected:
        key = (
            item["controller"],
            float(item["eta"]),
        )

        expected_counts[key] += 1

    aggregate_rows = []

    for key in sorted(
        expected_counts,
        key=lambda value: (
            value[0],
            value[1],
        ),
    ):
        controller, eta = key
        group = grouped.get(key, [])

        safe_count = sum(
            as_bool(
                row["safe_touchdown"]
            )
            for row in group
        )

        valid_count = sum(
            as_bool(
                row["valid_prefault"]
            )
            for row in group
        )

        contact_count = sum(
            as_bool(
                row["contact_found"]
            )
            for row in group
        )

        n = len(group)

        safe_rate = (
            safe_count / n
            if n
            else float("nan")
        )

        lower, upper = wilson(
            safe_count,
            n,
        )

        vertical_speeds = [
            value
            for row in group
            if (
                value := optional_float(
                    row[
                        "vertical_speed_mps"
                    ]
                )
            ) is not None
        ]

        aggregate_rows.append(
            {
                "controller": controller,
                "motor": 2,
                "eta": f"{eta:.6f}",
                "n_expected":
                    expected_counts[key],
                "n_present": n,
                "valid_prefault_count":
                    valid_count,
                "contact_count":
                    contact_count,
                "safe_count":
                    safe_count,
                "safe_rate":
                    (
                        safe_rate
                        if n
                        else ""
                    ),
                "wilson95_lower":
                    (
                        lower
                        if n
                        else ""
                    ),
                "wilson95_upper":
                    (
                        upper
                        if n
                        else ""
                    ),
                "mean_vertical_speed_mps":
                    (
                        sum(vertical_speeds)
                        / len(vertical_speeds)
                        if vertical_speeds
                        else ""
                    ),
                "max_vertical_speed_mps":
                    (
                        max(vertical_speeds)
                        if vertical_speeds
                        else ""
                    ),
            }
        )

    aggregate_output = (
        ROOT / "localization_aggregate.csv"
    )

    with aggregate_output.open(
        "w",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(
                aggregate_rows[0]
            ),
        )
        writer.writeheader()
        writer.writerows(
            aggregate_rows
        )

    controller_audits = []

    for controller in (
        "pinv",
        "cem",
    ):
        rows = [
            row
            for row in aggregate_rows
            if (
                row["controller"]
                == controller
                and row["n_present"]
                == row["n_expected"]
            )
        ]

        rates = [
            float(row["safe_rate"])
            for row in rows
            if row["safe_rate"] != ""
        ]

        below = any(
            rate < 0.5
            for rate in rates
        )

        above = any(
            rate > 0.5
            for rate in rates
        )

        exact = any(
            abs(rate - 0.5)
            < 1.0e-12
            for rate in rates
        )

        bracketed = (
            exact
            or (
                below
                and above
            )
        )

        controller_audits.append(
            {
                "controller": controller,
                "complete_eta_conditions":
                    len(rows),
                "bracketed_50":
                    bracketed,
                "minimum_safe_rate":
                    (
                        min(rates)
                        if rates
                        else ""
                    ),
                "maximum_safe_rate":
                    (
                        max(rates)
                        if rates
                        else ""
                    ),
            }
        )

    audit_output = (
        ROOT / "localization_bracketing.csv"
    )

    with audit_output.open(
        "w",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(
                controller_audits[0]
            ),
        )
        writer.writeheader()
        writer.writerows(
            controller_audits
        )

    report_output = (
        ROOT / "localization_report.md"
    )

    report = [
        "# Nominal M2 Boundary Localization",
        "",
        f"- Scheduled trials: {len(expected)}",
        f"- Completed trials: {len(trial_rows)}",
        f"- Missing trials: {len(missing)}",
        "",
        "## Aggregate results",
        "",
        "| Controller | Eta | Present | Safe | Safe rate |",
        "|---|---:|---:|---:|---:|",
    ]

    for row in aggregate_rows:
        safe_rate = row["safe_rate"]

        rendered_rate = (
            f"{float(safe_rate):.3f}"
            if safe_rate != ""
            else ""
        )

        report.append(
            "| "
            f"{row['controller']} | "
            f"{row['eta']} | "
            f"{row['n_present']}/"
            f"{row['n_expected']} | "
            f"{row['safe_count']} | "
            f"{rendered_rate} |"
        )

    report.extend(
        [
            "",
            "## Bracketing audit",
            "",
        ]
    )

    for row in controller_audits:
        report.append(
            "- "
            f"{row['controller']}: "
            f"bracketed_50="
            f"{row['bracketed_50']}, "
            f"complete_eta_conditions="
            f"{row['complete_eta_conditions']}"
        )

    report_output.write_text(
        "\n".join(report) + "\n"
    )

    print(
        "========== M2 LOCALIZATION =========="
    )

    for row in aggregate_rows:
        print(
            f"{row['controller']:5s} "
            f"eta={row['eta']} "
            f"n={row['n_present']}/"
            f"{row['n_expected']} "
            f"safe={row['safe_count']} "
            f"rate={row['safe_rate']}"
        )

    print()
    print(
        f"scheduled={len(expected)}"
    )
    print(
        f"completed={len(trial_rows)}"
    )
    print(f"missing={len(missing)}")

    for row in controller_audits:
        print(
            f"{row['controller']}: "
            f"bracketed_50="
            f"{row['bracketed_50']}"
        )

    print(f"[SAVED] {trial_output}")
    print(f"[SAVED] {aggregate_output}")
    print(f"[SAVED] {audit_output}")
    print(f"[SAVED] {report_output}")

    if (
        args.require_complete
        and missing
    ):
        raise SystemExit(
            "[FAIL] Localization dataset "
            "is incomplete."
        )


if __name__ == "__main__":
    main()
