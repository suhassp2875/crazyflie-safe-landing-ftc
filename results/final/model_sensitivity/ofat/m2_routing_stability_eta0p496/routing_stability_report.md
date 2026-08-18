# M2 Controller Routing Stability at eta=0.496

- Scheduled trials: 660
- Completed trials: 660
- Missing trials: 0

The nominal routing decision is PINV for M2. This experiment tests that fixed operational choice under ±10% plant perturbations.

| Condition | Pairs | PINV safe | CEM safe | PINV-only | CEM-only | Routing state | McNemar p |
|---|---:|---:|---:|---:|---:|---|---:|
| nominal | 30/30 | 30 | 0 | 30 | 0 | pinv_preferred | 1.86265e-09 |
| mass_minus10 | 30/30 | 30 | 27 | 3 | 0 | pinv_preferred | 0.25 |
| mass_plus10 | 30/30 | 0 | 0 | 0 | 0 | tie | 1 |
| thrust_coefficient_minus10 | 30/30 | 0 | 0 | 0 | 0 | tie | 1 |
| thrust_coefficient_plus10 | 30/30 | 30 | 18 | 12 | 0 | pinv_preferred | 0.000488281 |
| motor_time_constant_minus10 | 30/30 | 30 | 0 | 30 | 0 | pinv_preferred | 1.86265e-09 |
| motor_time_constant_plus10 | 30/30 | 30 | 0 | 30 | 0 | pinv_preferred | 1.86265e-09 |
| thrust_to_torque_ratio_minus10 | 30/30 | 30 | 0 | 30 | 0 | pinv_preferred | 1.86265e-09 |
| thrust_to_torque_ratio_plus10 | 30/30 | 30 | 0 | 30 | 0 | pinv_preferred | 1.86265e-09 |
| arm_length_minus10 | 30/30 | 30 | 0 | 30 | 0 | pinv_preferred | 1.86265e-09 |
| arm_length_plus10 | 30/30 | 30 | 0 | 30 | 0 | pinv_preferred | 1.86265e-09 |

## Interpretation rules

- `pinv_preferred`: more paired seeds are safe under PINV than CEM.
- `cem_preferred`: more paired seeds are safe under CEM than PINV; the nominal M2 routing choice reverses.
- `tie`: the fixed-eta experiment does not distinguish the two controllers.
- This is an operating-point stability test at eta=0.496, not a complete perturbed boundary comparison.
