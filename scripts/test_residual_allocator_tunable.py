#!/usr/bin/env python3

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.controllers.residual_allocator_qp import AllocatorState
from src.controllers.residual_allocator_tunable import (
    load_weight_config,
    allocate_residual_tunable,
)


def run_case(motor, eta, state, cfg):
    result = allocate_residual_tunable(motor, eta, state, cfg)
    print(
        f"motor={motor}, eta={eta:.4f}, "
        f"candidate={result.candidate_name}, r={result.residual}, "
        f"pred_vz={result.predicted_vz:.4f}, score={result.score:.6f}"
    )


def main():
    cfg = load_weight_config("configs/allocator_weights/qplite_baseline.json")

    print("[TEST] Tunable allocator baseline config")
    print(f"config={cfg.name}")

    print("\n[TEST] Nominal fault-event state, eta=0.497")
    state = AllocatorState(z=0.70, vz=0.0, x=0.0, y=0.0, vx=0.0, vy=0.0)
    for motor in [1, 2, 3, 4]:
        run_case(motor, 0.497, state, cfg)

    print("\n[TEST] Low-altitude descending state, eta=0.497")
    state = AllocatorState(z=0.25, vz=-0.20, x=0.20, y=0.20, vx=0.02, vy=0.01)
    for motor in [1, 2, 3, 4]:
        run_case(motor, 0.497, state, cfg)

    print("\n[TEST] Nominal fault-event state, eta=0.496")
    state = AllocatorState(z=0.70, vz=0.0, x=0.0, y=0.0, vx=0.0, vy=0.0)
    for motor in [1, 2, 3, 4]:
        run_case(motor, 0.496, state, cfg)


if __name__ == "__main__":
    main()
