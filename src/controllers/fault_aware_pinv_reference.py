#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# Legacy mixer used by power_distribution_sitl.c:
#
# m1 = T - r + p + y
# m2 = T - r - p - y
# m3 = T + r - p + y
# m4 = T + r + p - y
#
# Therefore, generalized commands reconstructed from motor commands are:
#
# T = (m1 + m2 + m3 + m4) / 4
# r = (-m1 - m2 + m3 + m4) / 4
# p = ( m1 - m2 - m3 + m4) / 4
# y = ( m1 - m2 + m3 - m4) / 4
#
# A maps motor commands into four-times the generalized command.
MIXER_EFFECTIVENESS = np.array(
    [
        [1.0, 1.0, 1.0, 1.0],
        [-1.0, -1.0, 1.0, 1.0],
        [1.0, -1.0, -1.0, 1.0],
        [1.0, -1.0, 1.0, -1.0],
    ],
    dtype=float,
)


@dataclass(frozen=True)
class AllocationResult:
    nominal_pwm: np.ndarray
    requested_pwm: np.ndarray
    applied_pwm: np.ndarray
    desired_generalized: np.ndarray
    achieved_generalized: np.ndarray
    generalized_error: np.ndarray
    clipped: np.ndarray


def effectiveness_matrix(
    fault_motor: int,
    eta: float,
) -> np.ndarray:
    if fault_motor not in (1, 2, 3, 4):
        raise ValueError("fault_motor must be one of 1, 2, 3, 4")

    eta = float(np.clip(eta, 0.0, 1.0))

    d = np.eye(4, dtype=float)
    d[fault_motor - 1, fault_motor - 1] = eta

    return d


def allocate_fault_aware_pinv(
    nominal_pwm: np.ndarray,
    fault_motor: int,
    eta: float,
    weights: np.ndarray | None = None,
    regularization: float = 1e-6,
    pwm_min: float = 0.0,
    pwm_max: float = 65535.0,
) -> AllocationResult:
    """
    Regularized weighted pseudo-inverse allocation followed by actuator
    clipping.

    The objective is:

        min_u || W (A D u - A u0) ||^2
              + regularization ||u - u0||^2

    Here:
      u0 = nominal healthy-mixer motor commands
      D  = motor effectiveness matrix
      A  = legacy command-effectiveness matrix
    """

    u0 = np.asarray(nominal_pwm, dtype=float).reshape(4)

    if weights is None:
        # Preserve collective thrust and roll/pitch more strongly than yaw.
        weights = np.array(
            [1.0, 1.0, 1.0, 0.20],
            dtype=float,
        )

    weights = np.asarray(weights, dtype=float).reshape(4)

    if np.any(weights <= 0.0):
        raise ValueError("All weights must be positive")

    if regularization < 0.0:
        raise ValueError("regularization must be non-negative")

    a = MIXER_EFFECTIVENESS
    d = effectiveness_matrix(fault_motor, eta)
    m = a @ d

    desired = a @ u0

    w2 = np.diag(weights * weights)

    hessian = m.T @ w2 @ m
    rhs = m.T @ w2 @ desired

    if regularization > 0.0:
        hessian = hessian + regularization * np.eye(4)
        rhs = rhs + regularization * u0

    requested_unclipped = np.linalg.solve(hessian, rhs)

    requested = np.clip(
        requested_unclipped,
        pwm_min,
        pwm_max,
    )

    applied = d @ requested
    achieved = a @ applied

    return AllocationResult(
        nominal_pwm=u0,
        requested_pwm=requested,
        applied_pwm=applied,
        desired_generalized=desired,
        achieved_generalized=achieved,
        generalized_error=achieved - desired,
        clipped=np.not_equal(requested, requested_unclipped),
    )


def legacy_mix(
    thrust: float,
    roll_command: float,
    pitch_command: float,
    yaw_command: float,
) -> np.ndarray:
    """
    Reproduce powerDistributionLegacy().

    The C firmware first divides roll and pitch by two.
    """

    r = roll_command / 2.0
    p = pitch_command / 2.0
    y = yaw_command
    t = thrust

    return np.array(
        [
            t - r + p + y,
            t - r - p - y,
            t + r - p + y,
            t + r + p - y,
        ],
        dtype=float,
    )


def allocation_objective(
    requested_pwm: np.ndarray,
    nominal_pwm: np.ndarray,
    fault_motor: int,
    eta: float,
    weights: np.ndarray,
    regularization: float,
) -> float:
    requested = np.asarray(requested_pwm, dtype=float).reshape(4)
    nominal = np.asarray(nominal_pwm, dtype=float).reshape(4)
    weights = np.asarray(weights, dtype=float).reshape(4)

    d = effectiveness_matrix(fault_motor, eta)
    a = MIXER_EFFECTIVENESS

    desired = a @ nominal
    achieved = a @ d @ requested

    weighted_error = weights * (achieved - desired)
    deviation = requested - nominal

    return float(
        weighted_error @ weighted_error
        + regularization * (deviation @ deviation)
    )


def allocate_fault_aware_bounded(
    nominal_pwm: np.ndarray,
    fault_motor: int,
    eta: float,
    weights: np.ndarray | None = None,
    regularization: float = 1e-6,
    pwm_min: float = 0.0,
    pwm_max: float = 65535.0,
) -> AllocationResult:
    """
    Exact bounded weighted least-squares allocation for four motors.

    Every motor is enumerated as:
      -1: fixed at pwm_min
       0: free
      +1: fixed at pwm_max

    The reduced regularized least-squares system is solved for the free
    motors. Infeasible active sets are rejected.
    """

    from itertools import product

    u0 = np.asarray(nominal_pwm, dtype=float).reshape(4)

    if weights is None:
        weights = np.array(
            [1.0, 1.0, 1.0, 0.20],
            dtype=float,
        )

    weights = np.asarray(weights, dtype=float).reshape(4)

    if np.any(weights <= 0.0):
        raise ValueError("All weights must be positive")

    if regularization < 0.0:
        raise ValueError("regularization must be non-negative")

    a = MIXER_EFFECTIVENESS
    d = effectiveness_matrix(fault_motor, eta)
    m = a @ d

    desired = a @ u0
    w2 = np.diag(weights * weights)

    best_u = None
    best_objective = np.inf

    for status in product((-1, 0, 1), repeat=4):
        status = np.asarray(status, dtype=int)

        free = np.flatnonzero(status == 0)
        fixed = np.flatnonzero(status != 0)

        candidate = np.zeros(4, dtype=float)

        for index in fixed:
            candidate[index] = (
                pwm_min if status[index] == -1 else pwm_max
            )

        if len(free) > 0:
            m_free = m[:, free]

            if len(fixed) > 0:
                residual_target = (
                    desired - m[:, fixed] @ candidate[fixed]
                )
            else:
                residual_target = desired.copy()

            hessian = m_free.T @ w2 @ m_free
            rhs = m_free.T @ w2 @ residual_target

            if regularization > 0.0:
                hessian = (
                    hessian
                    + regularization * np.eye(len(free))
                )
                rhs = rhs + regularization * u0[free]

            try:
                candidate[free] = np.linalg.solve(
                    hessian,
                    rhs,
                )
            except np.linalg.LinAlgError:
                continue

        tolerance = 1e-7

        if np.any(candidate < pwm_min - tolerance):
            continue

        if np.any(candidate > pwm_max + tolerance):
            continue

        candidate = np.clip(candidate, pwm_min, pwm_max)

        objective = allocation_objective(
            requested_pwm=candidate,
            nominal_pwm=u0,
            fault_motor=fault_motor,
            eta=eta,
            weights=weights,
            regularization=regularization,
        )

        if objective < best_objective:
            best_objective = objective
            best_u = candidate.copy()

    if best_u is None:
        raise RuntimeError(
            "No feasible bounded allocation was found"
        )

    applied = d @ best_u
    achieved = a @ applied

    return AllocationResult(
        nominal_pwm=u0,
        requested_pwm=best_u,
        applied_pwm=applied,
        desired_generalized=desired,
        achieved_generalized=achieved,
        generalized_error=achieved - desired,
        clipped=(
            np.isclose(best_u, pwm_min)
            | np.isclose(best_u, pwm_max)
        ),
    )
