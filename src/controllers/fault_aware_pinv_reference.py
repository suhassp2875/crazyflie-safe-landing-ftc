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
