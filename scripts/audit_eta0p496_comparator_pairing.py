#!/usr/bin/env python3

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional


LOG_DIR = Path("logs")

PROD_DIR = Path(
    "results/final/pinv_baseline/"
    "seeded_eta0p496/production_30/trials"
)

OUTPUT = Path(
    "results/final/pinv_baseline/"
    "seeded_eta0p496/production_30/"
    "comparator_pairing_audit.csv"
)

MOTOR_PATTERN = re.compile(
    r"(?:^|_)m([1-4])(?:_|$)",
    re.IGNORECASE,
)

SEED_PATTERN = re.compile(
    r"(?:^|_)seed(\d+)(?:_|\.csv$)",
    re.IGNORECASE,
)


def controller_from_path(path: Path) -> Optional[str]:
    text = path.name.lower()

    if "pinv" in text:
        return "pinv"

    if "cem" in text:
        return "cem"

    if "qplite" in text:
        return "qplite"

    return None


def first_value(
    row: dict[str, str],
    names: tuple[str, ...],
) -> Optional[float]:
    for name in names:
        value = row.get(name, "").strip()

        if value == "":
            continue

        try:
            return float(value)
        except ValueError:
            continue

    return None


def rounded(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None

    return round(value, 9)


def parameter_signature(
    row: dict[str, str],
) -> Optional[tuple[float, ...]]:
    values = (
        first_value(row, ("spawn_x",)),
        first_value(row, ("spawn_y",)),
        first_value(
            row,
            (
                "spawn_yaw_deg",
                "spawn_yaw",
            ),
        ),
        first_value(
            row,
            (
                "fault_time_cmd",
                "fault_time",
                "fault_time_s",
            ),
        ),
        first_value(
            row,
            (
                "hover_z",
                "hover_z_cmd",
            ),
        ),
    )

    if any(value is None for value in values):
        return None

    return tuple(
        rounded(value)
        for value in values
    )


def load_record(path: Path) -> Optional[dict[str, object]]:
    controller = controller_from_path(path)

    if controller is None:
        return None

    motor_match = MOTOR_PATTERN.search(path.name)
    seed_match = SEED_PATTERN.search(path.name)

    if motor_match is None or seed_match is None:
        return None

    try:
        with path.open(newline="") as file:
            reader = csv.DictReader(file)
            first = next(reader, None)
            fields = reader.fieldnames or []
    except Exception:
        return None

    if first is None:
        return None

    motor = int(motor_match.group(1))
    filename_seed = int(seed_match.group(1))

    csv_seed_text = first.get("trial_seed", "").strip()

    try:
        csv_seed = int(float(csv_seed_text))
    except ValueError:
        csv_seed = filename_seed

    return {
        "path": str(path),
        "controller": controller,
        "motor": motor,
        "seed": csv_seed,
        "seed_prefix": csv_seed // 100,
        "rep": csv_seed % 100,
        "signature": parameter_signature(first),
        "fieldnames": "|".join(fields),
        "protocol_id": first.get("protocol_id", ""),
        "allocator_config": first.get(
            "allocator_config",
            "",
        ),
    }


# ----------------------------------------------------------
# Load the exact PINV production set.
# ----------------------------------------------------------

pinv_records = []

for path in sorted(PROD_DIR.glob("*.csv")):
    record = load_record(path)

    if record is not None:
        pinv_records.append(record)

if len(pinv_records) != 120:
    raise SystemExit(
        f"[FAIL] Expected 120 production PINV records; "
        f"found {len(pinv_records)}"
    )

pinv_by_motor: dict[int, list[dict[str, object]]] = defaultdict(list)

for record in pinv_records:
    pinv_by_motor[int(record["motor"])].append(record)

# ----------------------------------------------------------
# Load raw comparator logs only.
# ----------------------------------------------------------

all_records = []

for path in sorted(LOG_DIR.glob("*.csv")):
    name = path.name.lower()

    if "eta0p496" not in name:
        continue

    record = load_record(path)

    if record is None:
        continue

    all_records.append(record)

grouped: dict[
    tuple[str, int, int],
    list[dict[str, object]],
] = defaultdict(list)

for record in all_records:
    key = (
        str(record["controller"]),
        int(record["motor"]),
        int(record["seed_prefix"]),
    )
    grouped[key].append(record)

audit_rows = []

print(
    "========== COMPLETE ETA=0.496 "
    "COMPARATOR BLOCKS =========="
)

for controller in ("qplite", "cem"):
    for motor in (1, 2, 3, 4):
        pinv_group = pinv_by_motor[motor]

        pinv_seeds = {
            int(record["seed"])
            for record in pinv_group
        }

        pinv_signatures = {
            record["signature"]
            for record in pinv_group
            if record["signature"] is not None
        }

        found_block = False

        for (
            group_controller,
            group_motor,
            prefix,
        ), records in sorted(grouped.items()):
            if group_controller != controller:
                continue

            if group_motor != motor:
                continue

            by_rep = {
                int(record["rep"]): record
                for record in records
                if 1 <= int(record["rep"]) <= 30
            }

            if set(by_rep) != set(range(1, 31)):
                continue

            block = [
                by_rep[rep]
                for rep in range(1, 31)
            ]

            block_seeds = {
                int(record["seed"])
                for record in block
            }

            block_signatures = {
                record["signature"]
                for record in block
                if record["signature"] is not None
            }

            exact_seed_overlap = len(
                pinv_seeds & block_seeds
            )

            signature_overlap = len(
                pinv_signatures & block_signatures
            )

            complete_signatures = (
                len(pinv_signatures) == 30
                and len(block_signatures) == 30
            )

            if exact_seed_overlap == 30:
                pairing_status = "exact_seed_paired"
            elif (
                complete_signatures
                and signature_overlap == 30
            ):
                pairing_status = "exact_parameter_paired"
            elif complete_signatures:
                pairing_status = "unpaired_parameter_sets"
            else:
                pairing_status = "metadata_incomplete"

            audit = {
                "controller": controller,
                "motor": motor,
                "seed_prefix": prefix,
                "n": len(block),
                "seed_min": min(block_seeds),
                "seed_max": max(block_seeds),
                "exact_seed_overlap_with_pinv":
                    exact_seed_overlap,
                "parameter_signature_overlap_with_pinv":
                    signature_overlap,
                "pinv_complete_signatures":
                    len(pinv_signatures) == 30,
                "comparator_complete_signatures":
                    len(block_signatures) == 30,
                "pairing_status": pairing_status,
                "protocol_ids": "|".join(
                    sorted(
                        {
                            str(record["protocol_id"])
                            for record in block
                        }
                    )
                ),
                "paths": "|".join(
                    str(record["path"])
                    for record in block
                ),
            }

            audit_rows.append(audit)
            found_block = True

            print(
                f"{controller:7s} "
                f"M{motor} "
                f"prefix={prefix} "
                f"seeds=[{min(block_seeds)},"
                f"{max(block_seeds)}] "
                f"seed_overlap={exact_seed_overlap}/30 "
                f"parameter_overlap={signature_overlap}/30 "
                f"status={pairing_status}"
            )

        if not found_block:
            print(
                f"{controller:7s} "
                f"M{motor}: "
                "NO COMPLETE 30-TRIAL BLOCK"
            )

OUTPUT.parent.mkdir(parents=True, exist_ok=True)

fieldnames = [
    "controller",
    "motor",
    "seed_prefix",
    "n",
    "seed_min",
    "seed_max",
    "exact_seed_overlap_with_pinv",
    "parameter_signature_overlap_with_pinv",
    "pinv_complete_signatures",
    "comparator_complete_signatures",
    "pairing_status",
    "protocol_ids",
    "paths",
]

with OUTPUT.open("w", newline="") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=fieldnames,
    )
    writer.writeheader()
    writer.writerows(audit_rows)

print(f"[SAVED] {OUTPUT}")
