# M2 PINV OFAT Model-Sensitivity Analysis

## Estimator

- Bias-reduced Firth logistic regression was used for nominal and all OFAT conditions.
- This estimator was chosen because several perturbed boundaries exhibit complete or near-complete separation.
- Bootstrap resampling was clustered by trial seed.
- The same OFAT cluster resample was used across all ten perturbation conditions to preserve their paired-seed structure.
- Nominal seeds were resampled independently because the nominal experiment used a distinct seed set.

## Interpretation

- Lower ED50 means tolerance of a more severe motor-loss condition.
- Therefore negative ΔED50 relative to nominal indicates improved fault tolerance.
- Positive ΔED50 indicates reduced fault tolerance.

## ED50 estimates

| Condition | ED50 | 95% CI | ΔED50 vs nominal |
|---|---:|---:|---:|
| nominal | 0.495574838 | [0.495537109, 0.495613599] | 0 |
| mass_minus10 | 0.448437500 | [0.448437500, 0.448437500] | -0.047137338 |
| mass_plus10 | 0.545312500 | [0.545312500, 0.545312500] | +0.049737662 |
| thrust_coefficient_minus10 | 0.550520855 | [0.550520855, 0.550520855] | +0.054946017 |
| thrust_coefficient_plus10 | 0.450199776 | [0.450061679, 0.450348090] | -0.045375062 |
| motor_time_constant_minus10 | 0.495312500 | [0.495312500, 0.495312500] | -0.000262338 |
| motor_time_constant_plus10 | 0.495170954 | [0.495019772, 0.495276363] | -0.000403884 |
| thrust_to_torque_ratio_minus10 | 0.495485786 | [0.495312500, 0.495581281] | -0.000089052 |
| thrust_to_torque_ratio_plus10 | 0.495312500 | [0.495312500, 0.495312500] | -0.000262338 |
| arm_length_minus10 | 0.495312500 | [0.495312500, 0.495312500] | -0.000262338 |
| arm_length_plus10 | 0.495395629 | [0.495312500, 0.495485786] | -0.000179210 |

## Sensitivity ranking

| Parameter | -10% ΔED50 | +10% ΔED50 | Max |ΔED50| |
|---|---:|---:|---:|
| thrust_coefficient | +0.054946017 | -0.045375062 | 0.054946017 |
| mass | -0.047137338 | +0.049737662 | 0.049737662 |
| motor_time_constant | -0.000262338 | -0.000403884 | 0.000403884 |
| arm_length | -0.000262338 | -0.000179210 | 0.000262338 |
| thrust_to_torque_ratio | -0.000089052 | -0.000262338 | 0.000262338 |
