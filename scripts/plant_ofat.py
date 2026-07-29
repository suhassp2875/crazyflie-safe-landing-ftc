#!/usr/bin/env python3

"""
Apply one reversible CrazySim/Gazebo plant perturbation at a time.

The controller and firmware model remain fixed. Only the physical Gazebo
plant template is changed.

Supported OFAT parameters:
- mass
- thrust_coefficient
- motor_time_constant
- thrust_to_torque_ratio
- arm_length
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

FIRMWARE_ROOT = Path(
    os.environ.get(
        "CRAZYSIM_FIRMWARE_ROOT",
        "~/crazysim_ws/CrazySim/crazyflie-firmware",
    )
).expanduser()

TEMPLATE = (
    FIRMWARE_ROOT
    / "tools/crazyflie-simulation"
    / "simulator_files/gazebo/models"
    / "crazyflie/model.sdf.jinja"
)

STATE_DIR = PROJECT_ROOT / ".plant_ofat"
BACKUP_PATH = STATE_DIR / "model.sdf.jinja.nominal"
STATE_PATH = STATE_DIR / "state.json"

NOMINAL_SHA256 = (
    "849b83459d1c2d9ea365d7e743ed7fe5"
    "a00151aa39505ec9f6294777881dfee9"
)

BODY_MASS = 0.025
PROP_MASS = 0.0008
PROP_COUNT = 4

TIME_CONSTANT_UP = 0.0125
TIME_CONSTANT_DOWN = 0.025

MOTOR_CONSTANT = 1.7965e-8
MOMENT_CONSTANT = 0.005964552

ROTOR_COORDINATE = 0.031
ROTOR_HEIGHT = 0.021

PARAMETERS = (
    "mass",
    "thrust_coefficient",
    "motor_time_constant",
    "thrust_to_torque_ratio",
    "arm_length",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def require_template() -> None:
    if not TEMPLATE.is_file():
        raise SystemExit(
            f"[FAIL] Gazebo template not found: {TEMPLATE}"
        )


def replace_exact(
    text: str,
    old: str,
    new: str,
    expected_count: int,
    label: str,
) -> str:
    count = text.count(old)

    if count != expected_count:
        raise SystemExit(
            f"[FAIL] {label}: expected {expected_count} "
            f"occurrences of {old!r}, found {count}."
        )

    return text.replace(old, new)


def decimal(value: float, digits: int = 10) -> str:
    rendered = f"{value:.{digits}f}"
    rendered = rendered.rstrip("0").rstrip(".")

    if rendered == "-0":
        rendered = "0"

    return rendered


def scientific(value: float) -> str:
    return f"{value:.10e}"


def nominal_total_mass() -> float:
    return BODY_MASS + PROP_COUNT * PROP_MASS


def body_mass_for_total_factor(factor: float) -> float:
    target_total = nominal_total_mass() * factor
    body_mass = target_total - PROP_COUNT * PROP_MASS

    if body_mass <= 0.0:
        raise SystemExit(
            "[FAIL] Requested total-mass factor produces "
            "a nonpositive central body mass."
        )

    return body_mass


def nominal_pose_tokens() -> list[tuple[str, float, float]]:
    return [
        (
            "<pose>0.031 -0.031 0.021 0 0 0</pose>",
            +ROTOR_COORDINATE,
            -ROTOR_COORDINATE,
        ),
        (
            "<pose>-0.031 -0.031 0.021 0 0 0</pose>",
            -ROTOR_COORDINATE,
            -ROTOR_COORDINATE,
        ),
        (
            "<pose >-0.031 0.031 0.021 0 0 0</pose>",
            -ROTOR_COORDINATE,
            +ROTOR_COORDINATE,
        ),
        (
            "<pose>0.031 0.031 0.021 0 0 0</pose>",
            +ROTOR_COORDINATE,
            +ROTOR_COORDINATE,
        ),
    ]


def pose_token(
    original: str,
    x: float,
    y: float,
) -> str:
    opening = "<pose >" if original.startswith("<pose >") else "<pose>"

    return (
        f"{opening}"
        f"{decimal(x)} {decimal(y)} {decimal(ROTOR_HEIGHT)} "
        "0 0 0</pose>"
    )


def audit_nominal_tokens(text: str) -> None:
    checks = [
        (
            "<mass>0.025</mass>",
            1,
            "central body mass",
        ),
        (
            "<mass>0.0008</mass>",
            4,
            "propeller masses",
        ),
        (
            "<timeConstantUp>0.0125</timeConstantUp>",
            4,
            "motor rise time constants",
        ),
        (
            "<timeConstantDown>0.025</timeConstantDown>",
            4,
            "motor fall time constants",
        ),
        (
            "<motorConstant>1.7965e-8</motorConstant>",
            4,
            "motor thrust constants",
        ),
        (
            "<momentConstant>0.005964552</momentConstant>",
            4,
            "motor moment constants",
        ),
    ]

    for token, expected, label in checks:
        count = text.count(token)

        if count != expected:
            raise SystemExit(
                f"[FAIL] Nominal {label}: expected "
                f"{expected}, found {count}."
            )

    for token, _, _ in nominal_pose_tokens():
        count = text.count(token)

        if count != 1:
            raise SystemExit(
                f"[FAIL] Nominal rotor pose {token!r}: "
                f"expected one occurrence, found {count}."
            )


def ensure_nominal_backup() -> str:
    require_template()
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if BACKUP_PATH.exists():
        backup_sha = sha256_path(BACKUP_PATH)

        if backup_sha != NOMINAL_SHA256:
            raise SystemExit(
                "[FAIL] Nominal backup checksum mismatch:\n"
                f"  expected={NOMINAL_SHA256}\n"
                f"  observed={backup_sha}\n"
                f"  backup={BACKUP_PATH}"
            )

        nominal_text = BACKUP_PATH.read_text()
        audit_nominal_tokens(nominal_text)
        return nominal_text

    current_sha = sha256_path(TEMPLATE)

    if current_sha != NOMINAL_SHA256:
        raise SystemExit(
            "[FAIL] Cannot initialize the nominal backup because "
            "the current template is not the audited nominal file.\n"
            f"  expected={NOMINAL_SHA256}\n"
            f"  observed={current_sha}\n"
            f"  template={TEMPLATE}"
        )

    nominal_text = TEMPLATE.read_text()
    audit_nominal_tokens(nominal_text)
    shutil.copy2(TEMPLATE, BACKUP_PATH)

    print(f"[BACKUP CREATED] {BACKUP_PATH}")
    return nominal_text


def build_perturbed_text(
    nominal_text: str,
    parameter: str,
    factor: float,
) -> tuple[str, dict[str, float | str]]:
    text = nominal_text

    metadata: dict[str, float | str] = {
        "parameter": parameter,
        "factor": factor,
    }

    if parameter == "mass":
        body_mass = body_mass_for_total_factor(factor)
        total_mass = body_mass + PROP_COUNT * PROP_MASS

        text = replace_exact(
            text,
            "<mass>0.025</mass>",
            f"<mass>{decimal(body_mass, 8)}</mass>",
            1,
            "central body mass",
        )

        metadata.update(
            {
                "body_mass_kg": body_mass,
                "prop_mass_each_kg": PROP_MASS,
                "total_mass_kg": total_mass,
            }
        )

    elif parameter == "thrust_coefficient":
        value = MOTOR_CONSTANT * factor

        text = replace_exact(
            text,
            "<motorConstant>1.7965e-8</motorConstant>",
            (
                "<motorConstant>"
                f"{scientific(value)}"
                "</motorConstant>"
            ),
            4,
            "motor thrust coefficient",
        )

        metadata.update(
            {
                "gazebo_motor_constant": value,
                "pwm_conversion_constant": 2.3375e-8,
                "relative_to_nominal": factor,
            }
        )

    elif parameter == "motor_time_constant":
        up = TIME_CONSTANT_UP * factor
        down = TIME_CONSTANT_DOWN * factor

        text = replace_exact(
            text,
            "<timeConstantUp>0.0125</timeConstantUp>",
            (
                "<timeConstantUp>"
                f"{decimal(up)}"
                "</timeConstantUp>"
            ),
            4,
            "motor rise time constant",
        )

        text = replace_exact(
            text,
            "<timeConstantDown>0.025</timeConstantDown>",
            (
                "<timeConstantDown>"
                f"{decimal(down)}"
                "</timeConstantDown>"
            ),
            4,
            "motor fall time constant",
        )

        metadata.update(
            {
                "time_constant_up_s": up,
                "time_constant_down_s": down,
            }
        )

    elif parameter == "thrust_to_torque_ratio":
        value = MOMENT_CONSTANT * factor

        text = replace_exact(
            text,
            (
                "<momentConstant>"
                "0.005964552"
                "</momentConstant>"
            ),
            (
                "<momentConstant>"
                f"{decimal(value, 12)}"
                "</momentConstant>"
            ),
            4,
            "motor moment constant",
        )

        metadata.update(
            {
                "gazebo_moment_constant": value,
                "relative_to_nominal": factor,
            }
        )

    elif parameter == "arm_length":
        coordinate = ROTOR_COORDINATE * factor

        for old, nominal_x, nominal_y in nominal_pose_tokens():
            new = pose_token(
                old,
                nominal_x * factor,
                nominal_y * factor,
            )

            text = replace_exact(
                text,
                old,
                new,
                1,
                "physical rotor pose",
            )

        metadata.update(
            {
                "rotor_xy_coordinate_m": coordinate,
                "physical_rotor_radius_m": (
                    math.sqrt(2.0) * coordinate
                ),
                "firmware_arm_length_m": 0.046,
            }
        )

    else:
        raise SystemExit(
            f"[FAIL] Unsupported parameter: {parameter}"
        )

    return text, metadata


def atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(
        path.name + ".plant_ofat_tmp"
    )

    temporary.write_text(text)
    temporary.chmod(path.stat().st_mode)
    os.replace(temporary, path)


def load_state() -> dict | None:
    if not STATE_PATH.is_file():
        return None

    return json.loads(STATE_PATH.read_text())


def command_show(as_json: bool) -> None:
    require_template()

    state = load_state()

    payload = {
        "template": str(TEMPLATE),
        "template_sha256": sha256_path(TEMPLATE),
        "expected_nominal_sha256": NOMINAL_SHA256,
        "is_nominal": (
            sha256_path(TEMPLATE) == NOMINAL_SHA256
        ),
        "nominal_values": {
            "body_mass_kg": BODY_MASS,
            "prop_mass_each_kg": PROP_MASS,
            "prop_count": PROP_COUNT,
            "total_mass_kg": nominal_total_mass(),
            "time_constant_up_s": TIME_CONSTANT_UP,
            "time_constant_down_s": TIME_CONSTANT_DOWN,
            "motor_constant": MOTOR_CONSTANT,
            "moment_constant": MOMENT_CONSTANT,
            "rotor_xy_coordinate_m": ROTOR_COORDINATE,
            "physical_rotor_radius_m": (
                math.sqrt(2.0) * ROTOR_COORDINATE
            ),
        },
        "active_state": state,
    }

    if as_json:
        print(json.dumps(payload, indent=2))
        return

    print(f"template={payload['template']}")
    print(
        "template_sha256="
        f"{payload['template_sha256']}"
    )
    print(f"is_nominal={payload['is_nominal']}")
    print(
        "nominal_total_mass_kg="
        f"{nominal_total_mass():.8f}"
    )
    print(
        "nominal_motor_constant="
        f"{MOTOR_CONSTANT:.10e}"
    )
    print(
        "nominal_moment_constant="
        f"{MOMENT_CONSTANT:.12f}"
    )
    print(
        "nominal_time_constants_s="
        f"({TIME_CONSTANT_UP}, "
        f"{TIME_CONSTANT_DOWN})"
    )
    print(
        "nominal_rotor_coordinate_m="
        f"{ROTOR_COORDINATE}"
    )
    print(
        "nominal_physical_rotor_radius_m="
        f"{math.sqrt(2.0) * ROTOR_COORDINATE:.9f}"
    )

    if state is None:
        print("active_state=None")
    else:
        print(
            "active_state="
            + json.dumps(
                state,
                sort_keys=True,
            )
        )


def command_verify() -> None:
    require_template()

    current_sha = sha256_path(TEMPLATE)
    state = load_state()

    if state is None:
        if current_sha != NOMINAL_SHA256:
            raise SystemExit(
                "[FAIL] No OFAT state is recorded, but the "
                "template is not nominal.\n"
                f"  expected={NOMINAL_SHA256}\n"
                f"  observed={current_sha}"
            )

        audit_nominal_tokens(TEMPLATE.read_text())
        print("[PASS] Plant template is nominal.")
        return

    expected_sha = state.get("perturbed_sha256")

    if current_sha != expected_sha:
        raise SystemExit(
            "[FAIL] Active OFAT state does not match the "
            "current template.\n"
            f"  state_sha={expected_sha}\n"
            f"  observed={current_sha}"
        )

    if not BACKUP_PATH.is_file():
        raise SystemExit(
            "[FAIL] Active perturbation has no nominal backup."
        )

    if sha256_path(BACKUP_PATH) != NOMINAL_SHA256:
        raise SystemExit(
            "[FAIL] Nominal backup checksum is invalid."
        )

    print(
        "[PASS] Active plant perturbation verified: "
        f"parameter={state['parameter']} "
        f"factor={state['factor']}"
    )


def command_apply(
    parameter: str,
    factor: float,
    dry_run: bool,
) -> None:
    if not math.isfinite(factor) or factor <= 0.0:
        raise SystemExit(
            "[FAIL] Factor must be finite and positive."
        )

    nominal_text = ensure_nominal_backup()

    perturbed_text, metadata = build_perturbed_text(
        nominal_text,
        parameter,
        factor,
    )

    perturbed_sha = sha256_bytes(
        perturbed_text.encode()
    )

    state = {
        **metadata,
        "protocol_id": "plant_ofat_v1",
        "nominal_sha256": NOMINAL_SHA256,
        "perturbed_sha256": perturbed_sha,
        "template": str(TEMPLATE),
        "applied_utc": (
            dt.datetime.now(dt.timezone.utc)
            .isoformat()
        ),
    }

    print(json.dumps(state, indent=2))

    if dry_run:
        print("[DRY RUN] No files were changed.")
        return

    atomic_write(TEMPLATE, perturbed_text)
    STATE_PATH.write_text(
        json.dumps(state, indent=2) + "\n"
    )

    command_verify()
    print(f"[APPLIED] {parameter} factor={factor}")


def command_restore() -> None:
    require_template()

    if not BACKUP_PATH.is_file():
        current_sha = sha256_path(TEMPLATE)

        if current_sha == NOMINAL_SHA256:
            STATE_PATH.unlink(missing_ok=True)
            print(
                "[PASS] Template is already nominal; "
                "no backup restoration was needed."
            )
            return

        raise SystemExit(
            "[FAIL] Cannot restore: nominal backup does not exist."
        )

    backup_sha = sha256_path(BACKUP_PATH)

    if backup_sha != NOMINAL_SHA256:
        raise SystemExit(
            "[FAIL] Refusing restore because the backup "
            "checksum is invalid."
        )

    shutil.copy2(BACKUP_PATH, TEMPLATE)
    STATE_PATH.unlink(missing_ok=True)

    restored_sha = sha256_path(TEMPLATE)

    if restored_sha != NOMINAL_SHA256:
        raise SystemExit(
            "[FAIL] Restoration checksum mismatch."
        )

    audit_nominal_tokens(TEMPLATE.read_text())
    print("[PASS] Nominal Gazebo plant restored.")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument(
        "--json",
        action="store_true",
    )

    subparsers.add_parser("verify")
    subparsers.add_parser("restore")

    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument(
        "--parameter",
        choices=PARAMETERS,
        required=True,
    )
    apply_parser.add_argument(
        "--factor",
        type=float,
        required=True,
    )
    apply_parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    args = parser.parse_args()

    if args.command == "show":
        command_show(args.json)
    elif args.command == "verify":
        command_verify()
    elif args.command == "restore":
        command_restore()
    elif args.command == "apply":
        command_apply(
            args.parameter,
            args.factor,
            args.dry_run,
        )
    else:
        raise SystemExit(
            f"[FAIL] Unknown command: {args.command}"
        )


if __name__ == "__main__":
    main()
