#!/usr/bin/env python3

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.controllers.residual_allocator_qp import AllocatorState, allocate_residual_qp


def run_case(motor, eta, state):
    result = allocate_residual_qp(motor, eta, state)
    print(
        f"motor={motor}, eta={eta:.3f}, "
        f"candidate={result.candidate_name}, r={result.residual}, "
        f"pred_vz={result.predicted_vz:.4f}, "
        f"score={result.score:.6f}"
    )
    return result


def main():
    print("[TEST] Nominal hover-like state")
    state = AllocatorState(z=0.70, vz=0.0, x=0.0, y=0.0, vx=0.0, vy=0.0)
    for motor in [1, 2, 3, 4]:
        run_case(motor, 0.497, state)

    print("\n[TEST] Low-altitude descending state")
    state = AllocatorState(z=0.25, vz=-0.20, x=0.20, y=0.20, vx=0.02, vy=0.01)
    for motor in [1, 2, 3, 4]:
        run_case(motor, 0.497, state)


if __name__ == "__main__":
    main()
