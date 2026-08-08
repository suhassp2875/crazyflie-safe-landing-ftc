#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

BASE_VALIDATOR = (
    PROJECT_ROOT
    / "scripts"
    / "validate_nominal_m2_boundary_trial.py"
)

DEFAULT_MANIFEST = (
    PROJECT_ROOT
    / "results/final/model_sensitivity/"
    "ofat/pinv_boundary_localization/"
    "ofat_condition_manifest.json"
)


def read_single_csv(
    path: Path,
) -> dict[str, str]:
    with path.open(
        newline=""
    ) as file:
        rows = list(
            csv.DictReader(file)
        )

    if len(rows) != 1:
        raise SystemExit(
            "[FAIL] Expected exactly one "
            f"summary row in {path}; "
            f"found {len(rows)}."
        )

    return rows[0]


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--csv",
        type=Path,
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
        "--parameter",
        required=True,
    )

    parser.add_argument(
        "--factor",
        type=float,
        required=True,
    )

    parser.add_argument(
        "--plant-state-json",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--condition-manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
    )

    parser.add_argument(
        "--ofat-protocol-id",
        default=(
            "crazyflie_ofat_"
            "pinv_localization_v1"
        ),
    )

    parser.add_argument(
        "--summary-output",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    if not args.csv.is_file():
        raise SystemExit(
            f"[FAIL] Missing trial CSV: "
            f"{args.csv}"
        )

    if not args.plant_state_json.is_file():
        raise SystemExit(
            "[FAIL] Missing trial plant-state "
            f"record: {args.plant_state_json}"
        )

    if not args.condition_manifest.is_file():
        raise SystemExit(
            "[FAIL] Missing condition manifest: "
            f"{args.condition_manifest}"
        )

    manifest = json.loads(
        args.condition_manifest.read_text()
    )

    manifest_lookup = {
        row["condition_id"]: row
        for row in manifest[
            "conditions"
        ]
    }

    if (
        args.condition_id
        not in manifest_lookup
    ):
        raise SystemExit(
            "[FAIL] Condition absent from "
            f"manifest: {args.condition_id}"
        )

    expected = manifest_lookup[
        args.condition_id
    ]

    if (
        expected["parameter"]
        != args.parameter
    ):
        raise SystemExit(
            "[FAIL] Manifest parameter "
            "mismatch."
        )

    if abs(
        float(expected["factor"])
        - args.factor
    ) > 1.0e-12:
        raise SystemExit(
            "[FAIL] Manifest factor mismatch."
        )

    plant_payload = json.loads(
        args.plant_state_json.read_text()
    )

    active = plant_payload.get(
        "active_state"
    )

    if not isinstance(active, dict):
        raise SystemExit(
            "[FAIL] Trial plant state has no "
            "active perturbation."
        )

    if plant_payload.get(
        "is_nominal"
    ):
        raise SystemExit(
            "[FAIL] Trial plant state is "
            "unexpectedly nominal."
        )

    if (
        active.get("parameter")
        != args.parameter
    ):
        raise SystemExit(
            "[FAIL] Trial plant parameter "
            "mismatch."
        )

    if abs(
        float(active.get("factor"))
        - args.factor
    ) > 1.0e-12:
        raise SystemExit(
            "[FAIL] Trial plant factor "
            "mismatch."
        )

    if (
        plant_payload[
            "template_sha256"
        ]
        != expected[
            "template_sha256"
        ]
    ):
        raise SystemExit(
            "[FAIL] Trial plant checksum does "
            "not match condition manifest."
        )

    if (
        plant_payload[
            "template_sha256"
        ]
        != active[
            "perturbed_sha256"
        ]
    ):
        raise SystemExit(
            "[FAIL] Trial plant checksum does "
            "not match active-state checksum."
        )

    args.summary_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with tempfile.TemporaryDirectory(
        prefix="ofat_m2_pinv_validation_"
    ) as temporary_directory:
        base_summary = (
            Path(temporary_directory)
            / "base_summary.csv"
        )

        command = [
            sys.executable,
            str(BASE_VALIDATOR),
            "--csv",
            str(args.csv),
            "--controller",
            "pinv",
            "--eta",
            f"{args.eta:.9f}",
            "--seed",
            str(args.seed),
            "--summary-output",
            str(base_summary),
        ]

        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=False,
        )

        if completed.returncode != 0:
            raise SystemExit(
                "[FAIL] Base PINV trial "
                "validation failed."
            )

        base_row = read_single_csv(
            base_summary
        )

    enriched = {
        **base_row,
        "eta": f"{args.eta:.8f}",
        "ofat_protocol_id":
            args.ofat_protocol_id,
        "condition_id":
            args.condition_id,
        "plant_parameter":
            args.parameter,
        "plant_factor":
            f"{args.factor:.2f}",
        "plant_template_sha256":
            plant_payload[
                "template_sha256"
            ],
        "plant_nominal_sha256":
            active[
                "nominal_sha256"
            ],
        "plant_state_verified":
            True,
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
        "[PASS] OFAT PINV trial validated: "
        f"condition={args.condition_id}, "
        f"parameter={args.parameter}, "
        f"factor={args.factor:.2f}, "
        f"eta={args.eta:.3f}, "
        f"seed={args.seed}"
    )

    print(
        f"[SAVED] {args.summary_output}"
    )


if __name__ == "__main__":
    main()
