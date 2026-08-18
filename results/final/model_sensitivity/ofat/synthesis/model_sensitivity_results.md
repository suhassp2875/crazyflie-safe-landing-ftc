# Model-Sensitivity Result Synthesis

## Experimental scope

The sensitivity study evaluates the M2 bounded-WLS/PINV controller under one-at-a-time ±10% perturbations of five plant parameters: mass, physical thrust coefficient, motor time constant, thrust-to-torque ratio, and arm length.

All safety outcomes use the full first-contact criterion rather than vertical speed alone. The final boundary experiment contains 2,100 fresh seeded OFAT trials, with 30 paired seeds at seven eta values for each of ten perturbed conditions.

## Boundary sensitivity

The common Firth-logistic nominal ED50 is 0.495574838 (95% paired-seed bootstrap CI [0.495537109, 0.495613599]).

Thrust coefficient and mass dominate the sensitivity ranking. Their ±10% perturbations move the estimated ED50 by roughly 0.045–0.055, whereas the remaining parameters move ED50 by approximately 10^-4.

| Rank | Parameter | -10% ΔED50 | +10% ΔED50 | Max |ΔED50| |
|---:|---|---:|---:|---:|
| 1 | thrust_coefficient | +0.054946017 | -0.045375062 | 0.054946017 |
| 2 | mass | -0.047137338 | +0.049737662 | 0.049737662 |
| 3 | motor_time_constant | -0.000262338 | -0.000403884 | 0.000403884 |
| 4 | arm_length | -0.000262338 | -0.000179210 | 0.000262338 |
| 5 | thrust_to_torque_ratio | -0.000089052 | -0.000262338 | 0.000262338 |

## Safety-criterion violation patterns

The safety boundary is not uniformly vertical-speed limited. In the mass -10% condition, angular-rate violation is the most frequent failed criterion, with additional horizontal-speed and tilt violations. In the thrust-coefficient +10% condition, the observed unsafe trials fail the angular-rate criterion. Most remaining perturbations primarily violate the vertical-speed criterion. Criterion counts are not mutually exclusive; a single trial may contribute to multiple columns.

| Condition | Safe / 210 | Vertical | Horizontal | Tilt | Angular | Drift | Most frequent violated criterion |
|---|---:|---:|---:|---:|---:|---:|---|
| mass_minus10 | 60/210 | 0 | 72 | 46 | 150 | 0 | angular_rate |
| mass_plus10 | 150/210 | 60 | 0 | 0 | 0 | 0 | vertical_speed |
| thrust_coefficient_minus10 | 180/210 | 30 | 0 | 0 | 0 | 0 | vertical_speed |
| thrust_coefficient_plus10 | 188/210 | 0 | 0 | 0 | 22 | 0 | angular_rate |
| motor_time_constant_minus10 | 150/210 | 60 | 0 | 0 | 0 | 0 | vertical_speed |
| motor_time_constant_plus10 | 154/210 | 56 | 0 | 0 | 0 | 0 | vertical_speed |
| thrust_to_torque_ratio_minus10 | 147/210 | 63 | 0 | 0 | 0 | 0 | vertical_speed |
| thrust_to_torque_ratio_plus10 | 150/210 | 60 | 0 | 0 | 0 | 0 | vertical_speed |
| arm_length_minus10 | 150/210 | 60 | 0 | 0 | 0 | 0 | vertical_speed |
| arm_length_plus10 | 149/210 | 61 | 0 | 0 | 0 | 0 | vertical_speed |

## Controller-routing stability

A separate fixed-operating-point experiment tested PINV against the frozen CEM-tuned QP-lite policy at eta=0.496 using 30 fresh paired seeds under nominal and all ten perturbed plant states, for 660 trials.

The nominal M2 routing decision was never reversed in favor of CEM under the tested plant perturbations at eta=0.496.

| Condition | PINV safe | CEM safe | PINV-only | CEM-only | Neither | Routing |
|---|---:|---:|---:|---:|---:|---|
| nominal | 30/30 | 0/30 | 30 | 0 | 0 | pinv_preferred |
| mass_minus10 | 30/30 | 27/30 | 3 | 0 | 0 | pinv_preferred |
| mass_plus10 | 0/30 | 0/30 | 0 | 0 | 30 | tie |
| thrust_coefficient_minus10 | 0/30 | 0/30 | 0 | 0 | 30 | tie |
| thrust_coefficient_plus10 | 30/30 | 18/30 | 12 | 0 | 0 | pinv_preferred |
| motor_time_constant_minus10 | 30/30 | 0/30 | 30 | 0 | 0 | pinv_preferred |
| motor_time_constant_plus10 | 30/30 | 0/30 | 30 | 0 | 0 | pinv_preferred |
| thrust_to_torque_ratio_minus10 | 30/30 | 0/30 | 30 | 0 | 0 | pinv_preferred |
| thrust_to_torque_ratio_plus10 | 30/30 | 0/30 | 30 | 0 | 0 | pinv_preferred |
| arm_length_minus10 | 30/30 | 0/30 | 30 | 0 | 0 | pinv_preferred |
| arm_length_plus10 | 30/30 | 0/30 | 30 | 0 | 0 | pinv_preferred |

The two tied adverse conditions are `mass_plus10` and `thrust_coefficient_minus10`; neither controller achieved a safe touchdown in any of the 30 paired trials at eta=0.496. Thus, these conditions provide evidence of loss of safety for both tested controllers at this operating point, rather than evidence of a routing reversal.

## Overall interpretation

The combined evidence supports a narrower and more defensible robustness statement than a generic claim of model invariance. The M2 PINV safety boundary is highly sensitive to parameters that directly change thrust-to-weight authority, especially mass and thrust coefficient. The ED50 shifts produced by the tested ±10% changes in motor time constant, thrust-to-torque ratio, and arm length are much smaller than the corresponding mass and thrust-coefficient shifts. Across the fixed eta=0.496 comparison, no tested plant state produced a higher safe-touchdown count for CEM than for PINV.

The adverse mass +10% and thrust-coefficient -10% cases also show that absence of a routing reversal does not imply safety robustness: neither tested controller achieved a safe touchdown in any of the 30 paired trials at eta=0.496 under those two perturbations.
