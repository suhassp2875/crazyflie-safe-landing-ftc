#!/usr/bin/env python3

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
CANONICAL_RUNNER = (
    PROJECT_DIR
    / "scripts/fault_triggered_landing_qp_event_allocator.py"
)

DEFAULT_CEM_CONFIG = (
    PROJECT_DIR
    / "configs/allocator_weights/cem_tuned_boundary.json"
)

POLICY_ID = "oracle_motor_conditioned_v1"


def option_value(
    arguments: list[str],
    option: str,
) -> str | None:
    for index, argument in enumerate(arguments):
        if argument == option:
            if index + 1 >= len(arguments):
                raise SystemExit(
                    f"[FAIL] {option} requires a value."
                )

            return arguments[index + 1]

        prefix = option + "="

        if argument.startswith(prefix):
            return argument[len(prefix):]

    return None


def contains_option(
    arguments: list[str],
    option: str,
) -> bool:
    return any(
        argument == option
        or argument.startswith(option + "=")
        for argument in arguments
    )


def main() -> int:
    arguments = sys.argv[1:]

    if not CANONICAL_RUNNER.is_file():
        raise SystemExit(
            f"[FAIL] Missing canonical runner: "
            f"{CANONICAL_RUNNER}"
        )

    motor_text = option_value(arguments, "--motor")

    if motor_text is None:
        raise SystemExit(
            "[FAIL] The supervisor requires --motor."
        )

    try:
        motor = int(motor_text)
    except ValueError as error:
        raise SystemExit(
            f"[FAIL] Invalid motor: {motor_text!r}"
        ) from error

    if motor not in (1, 2, 3, 4):
        raise SystemExit(
            f"[FAIL] Motor must be 1, 2, 3, or 4; "
            f"received {motor}."
        )

    for forbidden in (
        "--controller",
        "--weight-config",
    ):
        if contains_option(arguments, forbidden):
            raise SystemExit(
                f"[FAIL] Do not pass {forbidden}; "
                "the supervisor selects it."
            )

    if motor == 2:
        selected_policy = "pinv_bounded_wls"
        forwarded = [
            *arguments,
            "--controller",
            "pinv",
        ]
    else:
        cem_config = Path(
            os.environ.get(
                "CEM_CONFIG",
                str(DEFAULT_CEM_CONFIG),
            )
        ).expanduser().resolve()

        if not cem_config.is_file():
            raise SystemExit(
                f"[FAIL] Missing CEM configuration: "
                f"{cem_config}"
            )

        selected_policy = "cem_tuned_qplite"
        forwarded = [
            *arguments,
            "--controller",
            "qplite",
            "--weight-config",
            str(cem_config),
        ]

    command = [
        sys.executable,
        str(CANONICAL_RUNNER),
        *forwarded,
    ]

    print(
        "[SUPERVISOR] "
        f"policy_id={POLICY_ID} "
        f"failed_motor=M{motor} "
        f"selected_policy={selected_policy}",
        flush=True,
    )

    print(
        "[SUPERVISOR] Executing canonical "
        "fault-triggered landing runner.",
        flush=True,
    )

    completed = subprocess.run(
        command,
        cwd=PROJECT_DIR,
        check=False,
    )

    print(
        "[SUPERVISOR] "
        f"canonical_exit_status="
        f"{completed.returncode}",
        flush=True,
    )

    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
