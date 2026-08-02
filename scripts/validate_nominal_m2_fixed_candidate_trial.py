#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import tempfile
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


def read_rows(
    path: Path,
) -> list[dict[str, str]]:
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def unique_nonempty(
    rows: list[dict[str, str]],
    key: str,
) -> set[str]:
    return {
        row.get(key, "").strip()
        for row in rows
        if row.get(key, "").strip()
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--controller",
        choices=["manual"],
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

    rows = read_rows(args.csv)

    if not rows:
        raise SystemExit(
            "[FAIL] Trial CSV contains no rows."
        )

    event_indices = [
        index
        for index, row in enumerate(rows)
        if row.get(
            "selected_candidate",
            "",
        ).strip()
        not in {
            "",
            "none",
        }
    ]

    if not event_indices:
        raise SystemExit(
            "[FAIL] No manual allocation event found."
        )

    event_index = event_indices[0]
    post_rows = rows[event_index:]

    expected_residual = (
        args.expected_r1,
        args.expected_r2,
        args.expected_r3,
        args.expected_r4,
    )

    controllers = unique_nonempty(
        post_rows,
        "controller",
    )

    allocator_configs = unique_nonempty(
        post_rows,
        "allocator_config",
    )

    candidates = unique_nonempty(
        post_rows,
        "selected_candidate",
    )

    residuals = {
        (
            as_int(row["r1"]),
            as_int(row["r2"]),
            as_int(row["r3"]),
            as_int(row["r4"]),
        )
        for row in post_rows
        if row.get(
            "selected_candidate",
            "",
        ).strip()
        not in {
            "",
            "none",
        }
    }

    protocols = unique_nonempty(
        rows,
        "protocol_id",
    )

    seeds = {
        as_int(value)
        for value in unique_nonempty(
            rows,
            "trial_seed",
        )
    }

    if protocols != {"seeded_ic_v1"}:
        raise SystemExit(
            "[FAIL] Protocol mismatch: "
            f"{protocols}"
        )

    if seeds != {args.seed}:
        raise SystemExit(
            "[FAIL] Trial-seed mismatch: "
            f"{seeds} != {{{args.seed}}}"
        )

    if controllers != {"qplite"}:
        raise SystemExit(
            "[FAIL] Internal controller mismatch.\n"
            "expected={'qplite'}\n"
            f"observed={controllers}"
        )

    if allocator_configs != {
        "manual_residual_sweep"
    }:
        raise SystemExit(
            "[FAIL] Allocator-config mismatch.\n"
            "expected={'manual_residual_sweep'}\n"
            f"observed={allocator_configs}"
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

    if expected_residual[1] != 0:
        raise SystemExit(
            "[FAIL] Fixed residual is nonzero "
            "on failed M2."
        )

    guard_enabled = {
        as_bool(
            row.get(
                "m4_guard_enabled",
                "False",
            )
        )
        for row in post_rows
    }

    guard_switched = {
        as_bool(
            row.get(
                "m4_guard_switched",
                "False",
            )
        )
        for row in post_rows
    }

    if guard_enabled != {False}:
        raise SystemExit(
            "[FAIL] M4 guard was unexpectedly enabled."
        )

    if guard_switched != {False}:
        raise SystemExit(
            "[FAIL] M4 guard unexpectedly switched."
        )

    qp_scores = {
        float(row["qp_score"])
        for row in post_rows
        if row.get(
            "qp_score",
            "",
        ).strip()
    }

    if qp_scores != {0.0}:
        raise SystemExit(
            "[FAIL] Manual residual should have "
            f"qp_score=0; observed={qp_scores}"
        )

    args.summary_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # The established boundary validator performs all
    # structural, pre-fault, first-contact and safety checks.
    # Its CEM branch expects the CEM allocator-config label.
    # A temporary validation-only copy changes only that
    # metadata label; the original manual CSV is checked above.
    with tempfile.TemporaryDirectory(
        prefix="m2_fixed_validation_"
    ) as temporary_directory:
        temporary_root = Path(
            temporary_directory
        )

        adapted_csv = (
            temporary_root
            / "adapted_trial.csv"
        )

        adapted_summary = (
            temporary_root
            / "base_summary.csv"
        )

        adapted_rows = []

        for index, original in enumerate(rows):
            adapted = dict(original)

            if index >= event_index:
                adapted[
                    "allocator_config"
                ] = "cem_tuned_boundary"

            adapted_rows.append(adapted)

        with adapted_csv.open(
            "w",
            newline="",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=list(
                    adapted_rows[0]
                ),
                extrasaction="ignore",
                restval="",
                lineterminator="\n",
            )

            writer.writeheader()
            writer.writerows(
                adapted_rows
            )

        command = [
            sys.executable,
            str(BASE_VALIDATOR),
            "--csv",
            str(adapted_csv),
            "--controller",
            "cem",
            "--eta",
            f"{args.eta:.9f}",
            "--seed",
            str(args.seed),
            "--summary-output",
            str(adapted_summary),
        ]

        completed = subprocess.run(
            command,
            cwd=PROJECT_DIR,
            check=False,
        )

        if completed.returncode != 0:
            raise SystemExit(
                "[FAIL] Base structural and "
                "first-contact validation failed."
            )

        base_rows = read_rows(
            adapted_summary
        )

    if len(base_rows) != 1:
        raise SystemExit(
            "[FAIL] Base validator did not "
            "produce exactly one summary row."
        )

    base_row = base_rows[0]

    enriched = {
        **base_row,
        "protocol_id":
            "nominal_m2_fixed_candidate_"
            "counterfactual_v1",
        "controller": "manual",
        "allocator_config":
            "manual_residual_sweep",
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
        "policy_match": True,
        "selected_candidate_verified":
            args.expected_candidate,
        "selected_r1_verified":
            expected_residual[0],
        "selected_r2_verified":
            expected_residual[1],
        "selected_r3_verified":
            expected_residual[2],
        "selected_r4_verified":
            expected_residual[3],
        "validation_basis":
            "base_validator_plus_exact_"
            "manual_policy_checks",
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

    print(
        "[PASS] Fixed-candidate trial validated: "
        f"condition={args.condition_id}, "
        f"eta={args.eta:.6f}, "
        f"seed={args.seed}, "
        f"candidate={args.expected_candidate}, "
        f"residual={expected_residual}"
    )

    print(
        f"[SAVED] {args.summary_output}"
    )


if __name__ == "__main__":
    main()
