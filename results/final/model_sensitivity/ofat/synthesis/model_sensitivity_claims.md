# Defensible Model-Sensitivity Claims

## Primary claim

For the M2 bounded-WLS/PINV controller, the estimated motor-effectiveness safety boundary is strongly sensitive to mass and physical thrust coefficient, while ±10% perturbations of motor time constant, thrust-to-torque ratio, and arm length produce substantially smaller ED50 shifts under the tested CrazySim/Gazebo simulation model.

## Quantitative sensitivity

- Common-estimator nominal ED50: 0.495574838.
- Rank 1: `thrust_coefficient`; max |ΔED50| = 0.054946017.
- Rank 2: `mass`; max |ΔED50| = 0.049737662.
- Rank 3: `motor_time_constant`; max |ΔED50| = 0.000403884.
- Rank 4: `arm_length`; max |ΔED50| = 0.000262338.
- Rank 5: `thrust_to_torque_ratio`; max |ΔED50| = 0.000262338.

## Routing stability

- The nominal M2 routing decision was never reversed in favor of CEM under the tested plant perturbations at eta=0.496.
- PINV had a higher safe-touchdown count in 9/11 tested plant states.
- The controllers tied in 2/11 tested plant states.
- PINV's paired advantage reached McNemar p<0.05 in 8/11 tested plant states.
- Considering only the ten perturbed plant states, PINV had the higher safe count in 8/10 and a paired p<0.05 advantage in 7/10.
- CEM had a higher safe-touchdown count in 0/11 tested plant states.

- Tied conditions: mass_plus10, thrust_coefficient_minus10.

## Safety-criterion violation patterns

- `mass_minus10`: most frequent violated safety criterion = angular_rate; V/H/T/A/D = 0/72/46/150/0.
- `mass_plus10`: most frequent violated safety criterion = vertical_speed; V/H/T/A/D = 60/0/0/0/0.
- `thrust_coefficient_minus10`: most frequent violated safety criterion = vertical_speed; V/H/T/A/D = 30/0/0/0/0.
- `thrust_coefficient_plus10`: most frequent violated safety criterion = angular_rate; V/H/T/A/D = 0/0/0/22/0.
- `motor_time_constant_minus10`: most frequent violated safety criterion = vertical_speed; V/H/T/A/D = 60/0/0/0/0.
- `motor_time_constant_plus10`: most frequent violated safety criterion = vertical_speed; V/H/T/A/D = 56/0/0/0/0.
- `thrust_to_torque_ratio_minus10`: most frequent violated safety criterion = vertical_speed; V/H/T/A/D = 63/0/0/0/0.
- `thrust_to_torque_ratio_plus10`: most frequent violated safety criterion = vertical_speed; V/H/T/A/D = 60/0/0/0/0.
- `arm_length_minus10`: most frequent violated safety criterion = vertical_speed; V/H/T/A/D = 60/0/0/0/0.
- `arm_length_plus10`: most frequent violated safety criterion = vertical_speed; V/H/T/A/D = 61/0/0/0/0.

## Claim boundaries

- These are simulator results under the tested single-motor M2 LoE setup; they do not establish hardware robustness.
- OFAT perturbations vary one plant parameter at a time by ±10%; combined multi-parameter mismatch was not tested.
- Lower ED50 means tolerance to a more severe motor-loss condition.
- The routing experiment is a fixed operating-point comparison at eta=0.496, not a complete perturbed boundary comparison between PINV and CEM.
- The failed-motor identity is assumed known; online motor-fault diagnosis was not evaluated.
- Zero-width seed-bootstrap intervals for some sharp transitions reflect identical sampled binary transition patterns and should not be interpreted as zero physical uncertainty.
