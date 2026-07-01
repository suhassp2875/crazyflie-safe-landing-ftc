#!/usr/bin/env python3

"""
Tunable fault-aware residual allocator.

This wrapper keeps the existing residual candidate set and surrogate model,
but exposes the scoring weights through a JSON config. This is the interface
that RL / CEM / Bayesian optimization will tune.

Important:
- This does NOT replace the safety controller with black-box RL.
- RL tunes the allocator gains/weights.
- Runtime allocation remains constrained and interpretable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.controllers.residual_allocator_qp import (
    AllocatorState,
    AllocationResult,
    empirical_prior_candidates,
    nominal_reference,
    opposite_motor,
    predict_metrics,
)


@dataclass
class AllocatorWeightConfig:
    name: str = "qplite_baseline"

    vertical_threshold: float = 0.330
    hard_vertical_threshold: float = 0.350

    vertical_weight: float = 1800.0
    hard_vertical_weight: float = 5000.0
    drift_weight: float = 80.0
    tilt_weight: float = 0.08
    effort_weight: float = 2.0e-9
    reference_weight: float = 1.0e-7
    support_weight: float = 2.0e-8
    saturation_weight: float = 20.0

    motor2_overboost_penalty: float = 0.50
    motor14_overboost_penalty: float = 0.15
    motor3_overboost_penalty: float = 0.25


def load_weight_config(path: Optional[str | Path]) -> AllocatorWeightConfig:
    if path is None:
        return AllocatorWeightConfig()

    p = Path(path)
    data = json.loads(p.read_text())

    allowed = set(AllocatorWeightConfig.__dataclass_fields__.keys())
    filtered = {k: v for k, v in data.items() if k in allowed}

    return AllocatorWeightConfig(**filtered)


def score_candidate_tunable(
    fault_motor: int,
    eta: float,
    state: AllocatorState,
    residual: list[int],
    ref: list[int],
    cfg: AllocatorWeightConfig,
) -> tuple[float, Dict[str, float]]:
    pred_vz, pred_drift, pred_tilt = predict_metrics(
        fault_motor=fault_motor,
        eta=eta,
        state=state,
        residual=residual,
    )

    r = [float(v) for v in residual]
    ref_f = [float(v) for v in ref]

    opp_idx = opposite_motor(fault_motor) - 1
    support_resid = sum(r) - r[opp_idx]

    total_effort = sum(v * v for v in r)
    ref_error = sum((v - rv) ** 2 for v, rv in zip(r, ref_f))

    pwm_margin = 65535.0 - state.max_motor_pwm
    saturation_excess = max(0.0, max(r) - pwm_margin)

    vertical_violation = max(0.0, pred_vz - cfg.vertical_threshold)
    hard_vertical_violation = max(0.0, pred_vz - cfg.hard_vertical_threshold)
    drift_violation = max(0.0, pred_drift - 0.65)
    tilt_violation = max(0.0, pred_tilt - 8.0)

    score = (
        cfg.vertical_weight * vertical_violation ** 2
        + cfg.hard_vertical_weight * hard_vertical_violation ** 2
        + cfg.drift_weight * drift_violation ** 2
        + cfg.tilt_weight * tilt_violation ** 2
        + cfg.effort_weight * total_effort
        + cfg.reference_weight * ref_error
        + cfg.support_weight * support_resid ** 2
        + cfg.saturation_weight * (saturation_excess / 10000.0) ** 2
    )

    # Empirical regularization from CrazySim sweeps.
    if fault_motor == 2 and residual[3] > 12500:
        score += cfg.motor2_overboost_penalty

    opp = residual[opp_idx]

    if fault_motor in [1, 4] and opp > 10000:
        score += cfg.motor14_overboost_penalty * ((opp - 10000) / 1000.0) ** 2

    if fault_motor == 3 and opp > 12000:
        score += cfg.motor3_overboost_penalty * ((opp - 12000) / 1000.0) ** 2

    details = {
        "predicted_vz": pred_vz,
        "predicted_drift": pred_drift,
        "predicted_tilt": pred_tilt,
        "total_effort": total_effort,
        "ref_error": ref_error,
        "support_resid": support_resid,
        "saturation_excess": saturation_excess,
        "vertical_violation": vertical_violation,
        "hard_vertical_violation": hard_vertical_violation,
    }

    return score, details


def allocate_residual_tunable(
    fault_motor: int,
    eta: float,
    state: AllocatorState,
    cfg: Optional[AllocatorWeightConfig] = None,
) -> AllocationResult:
    if cfg is None:
        cfg = AllocatorWeightConfig()

    ref = nominal_reference(fault_motor, eta)
    candidates = empirical_prior_candidates(fault_motor)

    best: Optional[AllocationResult] = None

    for name, residual in candidates:
        if residual[fault_motor - 1] != 0:
            continue

        score, details = score_candidate_tunable(
            fault_motor=fault_motor,
            eta=eta,
            state=state,
            residual=residual,
            ref=ref,
            cfg=cfg,
        )

        if best is None or score < best.score:
            best = AllocationResult(
                residual=[int(v) for v in residual],
                candidate_name=name,
                score=score,
                predicted_vz=details["predicted_vz"],
                predicted_drift=details["predicted_drift"],
                predicted_tilt=details["predicted_tilt"],
                details=details,
            )

    if best is None:
        raise RuntimeError("No feasible candidate found.")

    return best


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/allocator_weights/qplite_baseline.json")
    parser.add_argument("--motor", type=int, required=True)
    parser.add_argument("--eta", type=float, default=0.497)
    parser.add_argument("--z", type=float, default=0.70)
    parser.add_argument("--vz", type=float, default=0.0)
    parser.add_argument("--x", type=float, default=0.0)
    parser.add_argument("--y", type=float, default=0.0)
    parser.add_argument("--vx", type=float, default=0.0)
    parser.add_argument("--vy", type=float, default=0.0)
    parser.add_argument("--roll", type=float, default=0.0)
    parser.add_argument("--pitch", type=float, default=0.0)
    parser.add_argument("--max-motor-pwm", type=float, default=33000.0)
    args = parser.parse_args()

    cfg = load_weight_config(args.config)

    state = AllocatorState(
        z=args.z,
        vz=args.vz,
        x=args.x,
        y=args.y,
        vx=args.vx,
        vy=args.vy,
        roll_deg=args.roll,
        pitch_deg=args.pitch,
        max_motor_pwm=args.max_motor_pwm,
    )

    result = allocate_residual_tunable(args.motor, args.eta, state, cfg)

    print("[TUNABLE ALLOCATOR RESULT]")
    print(f"config: {cfg.name}")
    print(f"fault_motor: {args.motor}")
    print(f"eta: {args.eta}")
    print(f"candidate: {result.candidate_name}")
    print(f"residual: {result.residual}")
    print(f"score: {result.score:.6f}")
    print(f"predicted_vz: {result.predicted_vz:.6f}")
    print(f"predicted_drift: {result.predicted_drift:.6f}")
    print(f"predicted_tilt: {result.predicted_tilt:.6f}")


if __name__ == "__main__":
    main()
