#!/usr/bin/env python3

"""
Fault-aware residual allocation QP-lite.

This module computes motor residuals

    r = [r1, r2, r3, r4]

under:
    r_faulted = 0
    0 <= r_i <= r_max

The objective is quadratic and encodes:
    1. vertical-impact-speed margin,
    2. drift / lateral-risk penalty,
    3. residual effort penalty,
    4. saturation penalty,
    5. motor-specific empirical prior from previous CrazySim sweeps.

This is not yet a formal CBF-QP. It is the first optimizer-based bridge
between the static residual policy map and a future CBF-QP/MPC layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple
import argparse
import math


Residual = List[int]


@dataclass
class AllocatorState:
    z: float = 0.70
    vz: float = 0.0
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    angular_rate_radps: float = 0.0
    max_motor_pwm: float = 33000.0


@dataclass
class AllocationResult:
    residual: Residual
    candidate_name: str
    score: float
    predicted_vz: float
    predicted_drift: float
    predicted_tilt: float
    details: Dict[str, float]


def opposite_motor(fault_motor: int) -> int:
    mapping = {
        1: 3,
        2: 4,
        3: 1,
        4: 2,
    }
    return mapping[fault_motor]


def empirical_prior_candidates(fault_motor: int) -> List[Tuple[str, Residual]]:
    """
    Candidate set centered around experimentally useful residual structures.

    The optimizer scores these candidates using a quadratic objective. This is
    safer than continuous unconstrained optimization for the current SITL setup
    because residual values are applied through CFLib params and the dynamics are
    not yet calibrated enough for a full analytical MPC.
    """

    if fault_motor == 1:
        return [
            ("zero", [0, 0, 0, 0]),
            ("opp_m3_9000", [0, 0, 9000, 0]),
            ("opp_m3_10000", [0, 0, 10000, 0]),
            ("opp_m3_11000", [0, 0, 11000, 0]),
            ("opp_m3_12000", [0, 0, 12000, 0]),
            ("m3dom_2000_10000_2000", [0, 2000, 10000, 2000]),
            ("m3dom_3000_11000_3000", [0, 3000, 11000, 3000]),
        ]

    if fault_motor == 2:
        return [
            ("zero", [0, 0, 0, 0]),
            ("opp_m4_10000", [0, 0, 0, 10000]),
            ("opp_m4_11000", [0, 0, 0, 11000]),
            ("opp_m4_12000", [0, 0, 0, 12000]),
            ("balanced_1000_0_1000_12000", [1000, 0, 1000, 12000]),
            ("balanced_2000_0_2000_12000", [2000, 0, 2000, 12000]),
            ("balanced_2500_0_2500_12000", [2500, 0, 2500, 12000]),
            ("balanced_3000_0_3000_12000", [3000, 0, 3000, 12000]),
        ]

    if fault_motor == 3:
        return [
            ("zero", [0, 0, 0, 0]),
            ("opp_m1_10000", [10000, 0, 0, 0]),
            ("opp_m1_11000", [11000, 0, 0, 0]),
            ("opp_m1_12000", [12000, 0, 0, 0]),
            ("opp_m1_13000", [13000, 0, 0, 0]),
            ("m1dom_3000_10000_3000", [10000, 3000, 0, 3000]),
            ("m1dom_4000_11000_4000", [11000, 4000, 0, 4000]),
            ("m1dom_5000_12000_5000", [12000, 5000, 0, 5000]),
        ]

    if fault_motor == 4:
        return [
            ("zero", [0, 0, 0, 0]),
            ("opp_m2_9000", [0, 9000, 0, 0]),
            ("opp_m2_10000", [0, 10000, 0, 0]),
            ("opp_m2_11000", [0, 11000, 0, 0]),
            ("opp_m2_12000", [0, 12000, 0, 0]),
            ("m2dom_2000_10000_2000", [2000, 10000, 2000, 0]),
            ("m2dom_3000_11000_3000", [3000, 11000, 3000, 0]),
        ]

    raise ValueError(f"fault_motor must be 1..4, got {fault_motor}")


def nominal_reference(fault_motor: int, eta: float) -> Residual:
    """
    Empirical reference policy from previous studies.
    This acts like a prior in the QP objective, not a hard-coded final policy.
    """

    # Current best known map around eta=0.497.
    if fault_motor == 1:
        return [0, 0, 10000, 0]
    if fault_motor == 2:
        return [2000, 0, 2000, 12000]
    if fault_motor == 3:
        return [12000, 0, 0, 0]
    if fault_motor == 4:
        return [0, 10000, 0, 0]

    raise ValueError(fault_motor)


def predict_metrics(
    fault_motor: int,
    eta: float,
    state: AllocatorState,
    residual: Residual,
) -> Tuple[float, float, float]:
    """
    Lightweight local surrogate.

    It is intentionally simple and conservative. It is not the final plant model.
    The next research step is to replace this with an identified dynamics model
    or a CBF/MPC prediction model.
    """

    r = [float(v) for v in residual]
    opp_idx = opposite_motor(fault_motor) - 1

    opp_resid = r[opp_idx]
    support_resid = sum(r) - opp_resid

    down_speed_now = max(0.0, -state.vz)
    drift_now = math.sqrt(state.x * state.x + state.y * state.y)
    hspeed_now = math.sqrt(state.vx * state.vx + state.vy * state.vy)
    tilt_now = max(abs(state.roll_deg), abs(state.pitch_deg))

    # Boundary-risk base estimate.
    # Calibrated from eta=0.496/0.497/0.498 first-contact experiments.
    # This is a local surrogate near the measured recoverability boundary.
    severity = max(0.0, 0.500 - eta)
    base_vz = 0.350 + 6.0 * severity

    # If currently descending fast or low, increase predicted touchdown speed.
    base_vz += 0.16 * max(0.0, down_speed_now - 0.05)
    base_vz += 0.06 * max(0.0, 0.35 - state.z)

    # Residual authority model.
    # Opposite-motor residual is the main authority term.
    # Support residual is deliberately weaker because experiments showed
    # support-heavy maps can become brittle near the boundary.
    predicted_vz = base_vz - 2.20e-6 * opp_resid - 1.5e-7 * support_resid

    # Over-boost penalty: experiments showed too much residual can worsen motor 2.
    if fault_motor == 2:
        over = max(0.0, opp_resid - 12000.0)
        predicted_vz += 2.0e-9 * over * over

    if fault_motor in [1, 3, 4]:
        over = max(0.0, opp_resid - 12500.0)
        predicted_vz += 1.0e-9 * over * over

    predicted_drift = drift_now + 0.60 * hspeed_now + 4.0e-6 * sum(r)
    predicted_tilt = tilt_now + 0.006 * (support_resid / 1000.0)

    return predicted_vz, predicted_drift, predicted_tilt


def score_candidate(
    fault_motor: int,
    eta: float,
    state: AllocatorState,
    residual: Residual,
    ref: Residual,
) -> Tuple[float, Dict[str, float]]:
    pred_vz, pred_drift, pred_tilt = predict_metrics(fault_motor, eta, state, residual)

    r = [float(v) for v in residual]
    ref_f = [float(v) for v in ref]

    total_effort = sum(v * v for v in r)
    ref_error = sum((v - rv) ** 2 for v, rv in zip(r, ref_f))

    pwm_margin = 65535.0 - state.max_motor_pwm
    saturation_excess = max(0.0, max(r) - pwm_margin)

    vertical_violation = max(0.0, pred_vz - 0.330)
    hard_vertical_violation = max(0.0, pred_vz - 0.350)
    drift_violation = max(0.0, pred_drift - 0.65)
    tilt_violation = max(0.0, pred_tilt - 8.0)

    support_resid = sum(r) - r[opposite_motor(fault_motor) - 1]

    # Quadratic QP-like objective.
    # Important: penalize support residual separately so the allocator does not
    # blindly choose support-heavy candidates unless vertical-risk reduction
    # justifies it.
    score = (
        1800.0 * vertical_violation ** 2
        + 5000.0 * hard_vertical_violation ** 2
        + 80.0 * drift_violation ** 2
        + 0.08 * tilt_violation ** 2
        + 2.0e-9 * total_effort
        + 1.0e-7 * ref_error
        + 2.0e-8 * support_resid ** 2
        + 20.0 * (saturation_excess / 10000.0) ** 2
    )

    # Empirical regularization from experiments:
    # 13000-class policies were worse for motor 2, and over-boost can add variance.
    if fault_motor == 2 and residual[3] > 12500:
        score += 0.50

    # Keep opposite-only policies near the empirical map unless risk is severe.
    opp = residual[opposite_motor(fault_motor) - 1]
    if fault_motor in [1, 4] and opp > 10000:
        score += 0.15 * ((opp - 10000) / 1000.0) ** 2

    if fault_motor == 3 and opp > 12000:
        score += 0.25 * ((opp - 12000) / 1000.0) ** 2

    details = {
        "predicted_vz": pred_vz,
        "predicted_drift": pred_drift,
        "predicted_tilt": pred_tilt,
        "total_effort": total_effort,
        "ref_error": ref_error,
        "saturation_excess": saturation_excess,
    }

    return score, details


def allocate_residual_qp(
    fault_motor: int,
    eta: float,
    state: AllocatorState,
) -> AllocationResult:
    ref = nominal_reference(fault_motor, eta)
    candidates = empirical_prior_candidates(fault_motor)

    best = None

    for name, residual in candidates:
        if residual[fault_motor - 1] != 0:
            continue

        score, details = score_candidate(fault_motor, eta, state, residual, ref)

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
        raise RuntimeError("No feasible residual candidate found.")

    return best


def main():
    parser = argparse.ArgumentParser()
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
    parser.add_argument("--rate", type=float, default=0.0)
    parser.add_argument("--max-motor-pwm", type=float, default=33000.0)
    args = parser.parse_args()

    state = AllocatorState(
        z=args.z,
        vz=args.vz,
        x=args.x,
        y=args.y,
        vx=args.vx,
        vy=args.vy,
        roll_deg=args.roll,
        pitch_deg=args.pitch,
        angular_rate_radps=args.rate,
        max_motor_pwm=args.max_motor_pwm,
    )

    result = allocate_residual_qp(args.motor, args.eta, state)

    print("[QP ALLOCATION RESULT]")
    print(f"fault_motor: {args.motor}")
    print(f"eta: {args.eta}")
    print(f"candidate: {result.candidate_name}")
    print(f"residual: {result.residual}")
    print(f"score: {result.score:.6f}")
    print(f"predicted_vz: {result.predicted_vz:.6f}")
    print(f"predicted_drift: {result.predicted_drift:.6f}")
    print(f"predicted_tilt: {result.predicted_tilt:.6f}")
    print("details:")
    for k, v in result.details.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
