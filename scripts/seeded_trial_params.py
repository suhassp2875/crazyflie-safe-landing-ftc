#!/usr/bin/env python3

"""
Generate controlled randomized trial parameters from a logged seed.

This defines the trial distribution for boundary experiments.

The goal is to replace uncontrolled re-launch nondeterminism with an explicit,
reproducible distribution over initial condition and fault-timing perturbations.

Current distribution, protocol_id=seeded_ic_v1:
- spawn_x, spawn_y: uniform +/- 0.03 m
- spawn_yaw_deg: uniform +/- 5 deg, logged for reproducibility
  NOTE: the current CrazySim launcher may not consume yaw directly. We still log it
  so later launchers can use the same seed distribution.
- hover_z: 0.70 +/- 0.02 m
- fault_time: 10.0 +/- 0.25 s
"""

from __future__ import annotations

import argparse
import json
import random
import shlex


def make_params(seed: int) -> dict:
    rng = random.Random(int(seed))

    return {
        "protocol_id": "seeded_ic_v1",
        "seed": int(seed),
        "spawn_x": rng.uniform(-0.03, 0.03),
        "spawn_y": rng.uniform(-0.03, 0.03),
        "spawn_yaw_deg": rng.uniform(-5.0, 5.0),
        "hover_z": 0.70 + rng.uniform(-0.02, 0.02),
        "fault_time": 10.0 + rng.uniform(-0.25, 0.25),
    }


def shell_escape_value(v):
    return shlex.quote(str(v))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--shell", action="store_true")
    args = parser.parse_args()

    params = make_params(args.seed)

    if args.shell:
        mapping = {
            "PROTOCOL_ID": params["protocol_id"],
            "TRIAL_SEED": params["seed"],
            "SPAWN_X": f"{params['spawn_x']:.6f}",
            "SPAWN_Y": f"{params['spawn_y']:.6f}",
            "SPAWN_YAW_DEG": f"{params['spawn_yaw_deg']:.6f}",
            "HOVER_Z": f"{params['hover_z']:.6f}",
            "FAULT_TIME": f"{params['fault_time']:.6f}",
        }

        for k, v in mapping.items():
            print(f"export {k}={shell_escape_value(v)}")
    else:
        print(json.dumps(params, indent=2))


if __name__ == "__main__":
    main()
