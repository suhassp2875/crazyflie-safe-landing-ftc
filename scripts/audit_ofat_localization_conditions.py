#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

PLANT_TOOL = (
    PROJECT_ROOT
    / "scripts"
    / "plant_ofat.py"
)

SCHEDULE = (
    PROJECT_ROOT
    / "results/final/model_sensitivity/"
    "ofat/pinv_boundary_localization/"
    "ofat_localization_schedule.csv"
)

BASELINE = (
    PROJECT_ROOT
    / "results/final/model_sensitivity/"
    "ofat/nominal_baseline_manifest.json"
)

OUTPUT = (
    PROJECT_ROOT
    / "results/final/model_sensitivity/"
    "ofat/pinv_boundary_localization/"
    "ofat_condition_manifest.json"
)


def run_tool(
    *arguments: str,
    capture: bool = False,
) -> str:
    completed = subprocess.run(
        [
            sys.executable,
            str(PLANT_TOOL),
            *arguments,
        ],
        cwd=PROJECT_ROOT,
        text=True,
        check=True,
        capture_output=capture,
    )

    if capture:
        return completed.stdout

    return ""


def restore_and_verify() -> None:
    run_tool("restore")
    run_tool("verify")


def main() -> None:
    if not SCHEDULE.is_file():
        raise SystemExit(
            f"[FAIL] Missing schedule: {SCHEDULE}"
        )

    if not BASELINE.is_file():
        raise SystemExit(
            f"[FAIL] Missing baseline manifest: "
            f"{BASELINE}"
        )

    baseline = json.loads(
        BASELINE.read_text()
    )

    with SCHEDULE.open(
        newline=""
    ) as file:
        schedule_rows = list(
            csv.DictReader(file)
        )

    if len(schedule_rows) != 350:
        raise SystemExit(
            "[FAIL] Expected 350 schedule rows; "
            f"found {len(schedule_rows)}."
        )

    conditions: dict[
        str,
        dict[str, str | float],
    ] = {}

    for row in schedule_rows:
        condition_id = row[
            "condition_id"
        ]

        descriptor = {
            "condition_id":
                condition_id,
            "parameter":
                row["parameter"],
            "factor":
                float(row["factor"]),
        }

        if condition_id in conditions:
            if (
                conditions[condition_id]
                != descriptor
            ):
                raise SystemExit(
                    "[FAIL] Conflicting schedule "
                    f"metadata for {condition_id}."
                )
        else:
            conditions[
                condition_id
            ] = descriptor

    if len(conditions) != 10:
        raise SystemExit(
            "[FAIL] Expected 10 unique "
            f"conditions; found {len(conditions)}."
        )

    audited_conditions = []

    try:
        restore_and_verify()

        for descriptor in conditions.values():
            condition_id = str(
                descriptor["condition_id"]
            )

            parameter = str(
                descriptor["parameter"]
            )

            factor = float(
                descriptor["factor"]
            )

            print()
            print(
                "============================================================"
            )
            print(
                "[AUDIT] "
                f"condition={condition_id} "
                f"parameter={parameter} "
                f"factor={factor:.2f}"
            )
            print(
                "============================================================"
            )

            restore_and_verify()

            run_tool(
                "apply",
                "--parameter",
                parameter,
                "--factor",
                f"{factor:.2f}",
            )

            run_tool("verify")

            payload = json.loads(
                run_tool(
                    "show",
                    "--json",
                    capture=True,
                )
            )

            active = payload.get(
                "active_state"
            )

            if not isinstance(
                active,
                dict,
            ):
                raise SystemExit(
                    "[FAIL] Active state missing "
                    f"for {condition_id}."
                )

            if payload.get(
                "is_nominal"
            ):
                raise SystemExit(
                    "[FAIL] Applied condition "
                    f"{condition_id} is nominal."
                )

            if (
                active.get("parameter")
                != parameter
            ):
                raise SystemExit(
                    "[FAIL] Active parameter "
                    f"mismatch for {condition_id}."
                )

            if abs(
                float(active.get("factor"))
                - factor
            ) > 1.0e-12:
                raise SystemExit(
                    "[FAIL] Active factor "
                    f"mismatch for {condition_id}."
                )

            template_sha = payload[
                "template_sha256"
            ]

            if (
                template_sha
                != active[
                    "perturbed_sha256"
                ]
            ):
                raise SystemExit(
                    "[FAIL] Active template "
                    f"checksum mismatch for "
                    f"{condition_id}."
                )

            audited_conditions.append(
                {
                    **descriptor,
                    "template_sha256":
                        template_sha,
                    "nominal_sha256":
                        active[
                            "nominal_sha256"
                        ],
                    "active_state":
                        active,
                }
            )

            print(
                "[PASS] Audited "
                f"{condition_id}"
            )

    finally:
        restore_and_verify()

    nominal_payload = json.loads(
        run_tool(
            "show",
            "--json",
            capture=True,
        )
    )

    if not nominal_payload.get(
        "is_nominal"
    ):
        raise SystemExit(
            "[FAIL] Plant was not restored "
            "after the audit."
        )

    expected_nominal_sha = baseline[
        "plant_template_sha256"
    ]

    observed_nominal_sha = (
        nominal_payload[
            "template_sha256"
        ]
    )

    if (
        observed_nominal_sha
        != expected_nominal_sha
    ):
        raise SystemExit(
            "[FAIL] Restored nominal checksum "
            "does not match the baseline."
        )

    manifest = {
        "protocol_id":
            "crazyflie_ofat_"
            "pinv_localization_v1",
        "baseline_manifest":
            str(BASELINE),
        "nominal_sha256":
            expected_nominal_sha,
        "condition_count":
            len(audited_conditions),
        "conditions":
            audited_conditions,
    }

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.write_text(
        json.dumps(
            manifest,
            indent=2,
        )
        + "\n"
    )

    print()
    print(f"[SAVED] {OUTPUT}")
    print(
        "[PASS] All 10 OFAT conditions "
        "audited and plant restored."
    )


if __name__ == "__main__":
    main()
