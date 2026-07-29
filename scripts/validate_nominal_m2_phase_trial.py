#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]

BASE_VALIDATOR = (
    PROJECT_DIR
    / "scripts"
    / "validate_nominal_m2_boundary_trial.py"
)


def as_bool(value: str) -> bool:
    return value.strip().lower() in {
        "true",
        "1",
        "yes",
    }


def as_int(value: str) -> int:
    return int(float(value))


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--controller",
        choices=["cem"],
        required=True,
    )

    parser.add_argument(
        "--eta",
        type=float,
        required=True,
    )

    parser.add_argument(
        "--seed",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--condition-id",
        required=True,
    )

    parser.add_argument(
        "--expected-candidate",
        required=True,
    )

    parser.add_argument(
        "--expected-r1",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--expected-r2",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--expected-r3",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--expected-r4",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--summary-output",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    if not args.csv.is_file():
        raise SystemExit(
            f"[FAIL] Missing trial CSV: {args.csv}"
        )

    if not BASE_VALIDATOR.is_file():
        raise SystemExit(
            f"[FAIL] Missing base validator: "
            f"{BASE_VALIDATOR}"
        )

    args.summary_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    base_summary = args.summary_output.with_name(
        args.summary_output.stem
        + ".base_validation.csv"
    )

    command = [
        sys.executable,
        str(BASE_VALIDATOR),
        "--csv",
        str(args.csv),
        "--controller",
        args.controller,
        "--eta",
        f"{args.eta:.8f}",
        "--seed",
        str(args.seed),
        "--summary-output",
        str(base_summary),
    ]

    completed = subprocess.run(
        command,
        cwd=PROJECT_DIR,
        check=False,
    )

    if completed.returncode != 0:
        raise SystemExit(
            "[FAIL] Base localization validation failed."
        )

    trial_rows = read_rows(args.csv)

    if not trial_rows:
        raise SystemExit(
            "[FAIL] Trial CSV contains no rows."
        )

    selected_rows = [
        row
        for row in trial_rows
        if row.get(
            "selected_candidate",
            "",
        ).strip()
        not in {
            "",
            "none",
        }
    ]

    if not selected_rows:
        raise SystemExit(
            "[FAIL] No post-selection rows found."
        )

    candidates = {
        row["selected_candidate"].strip()
        for row in selected_rows
    }

    residuals = {
        (
            as_int(row["r1"]),
            as_int(row["r2"]),
            as_int(row["r3"]),
            as_int(row["r4"]),
        )
        for row in selected_rows
    }

    controllers = {
        row["controller"].strip()
        for row in selected_rows
    }

    allocator_configs = {
        row["allocator_config"].strip()
        for row in selected_rows
    }

    guards_enabled = {
        as_bool(
            row.get(
                "m4_guard_enabled",
                "False",
            )
        )
        for row in selected_rows
    }

    expected_residual = (
        args.expected_r1,
        args.expected_r2,
        args.expected_r3,
        args.expected_r4,
    )

    if candidates != {
        args.expected_candidate
    }:
        raise SystemExit(
            "[FAIL] Candidate mismatch.\n"
            f"expected={args.expected_candidate}\n"
            f"observed={sorted(candidates)}"
        )

    if residuals != {
        expected_residual
    }:
        raise SystemExit(
            "[FAIL] Residual mismatch.\n"
            f"expected={expected_residual}\n"
            f"observed={sorted(residuals)}"
        )

    if controllers != {"qplite"}:
        raise SystemExit(
            "[FAIL] Controller mismatch.\n"
            f"expected=qplite\n"
            f"observed={sorted(controllers)}"
        )

    if allocator_configs != {
        "cem_tuned_boundary"
    }:
        raise SystemExit(
            "[FAIL] Allocator-config mismatch.\n"
            "expected=cem_tuned_boundary\n"
            f"observed={sorted(allocator_configs)}"
        )

    if guards_enabled != {False}:
        raise SystemExit(
            "[FAIL] Unexpected M4 guard activation."
        )

    base_rows = read_rows(base_summary)

    if len(base_rows) != 1:
        raise SystemExit(
            "[FAIL] Base validator did not produce "
            "exactly one summary row."
        )

    base_row = base_rows[0]

    enriched = {
        "condition_id":
            args.condition_id,
        "expected_candidate":
            args.expected_candidate,
        "expected_r1":
            args.expected_r1,
        "expected_r2":
            args.expected_r2,
        "expected_r3":
            args.expected_r3,
        "expected_r4":
            args.expected_r4,
        "selector_match":
            True,
        "selected_candidate_verified":
            next(iter(candidates)),
        "selected_r1_verified":
            expected_residual[0],
        "selected_r2_verified":
            expected_residual[1],
        "selected_r3_verified":
            expected_residual[2],
        "selected_r4_verified":
            expected_residual[3],
        **base_row,
    }

    with args.summary_output.open(
        "w",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(enriched),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(enriched)

    base_summary.unlink(
        missing_ok=True
    )

    print(
        "[PASS] Phase trial validated: "
        f"condition={args.condition_id}, "
        f"eta={args.eta:.5f}, "
        f"seed={args.seed}, "
        f"candidate={args.expected_candidate}, "
        f"residual={expected_residual}"
    )

    print(
        f"[SAVED] {args.summary_output}"
    )


if __name__ == "__main__":
    main()
