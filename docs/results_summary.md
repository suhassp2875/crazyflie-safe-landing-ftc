# Fault-Triggered Safe Touchdown Control for Crazyflie-Class Quadrotors

## 1. Project Goal

This project studies emergency touchdown control for a Crazyflie-class quadrotor under single-motor loss-of-effectiveness, abbreviated as LoE. The goal is to determine whether safe first-contact touchdown can be recovered after a motor fault by moving beyond high-level altitude commands and applying low-level residual control at the motor PWM level.

Central research question:

Can a fault-triggered residual motor-level controller expand the safe touchdown recoverability boundary under partial actuator loss?

---

## 2. Simulation Platform

Experiments were conducted using:

- CrazySim / Crazyflie SITL
- Gazebo Sim
- cflib Python control interface
- Low-level hover setpoints through send_hover_setpoint
- Custom SITL firmware fault injection and residual motor-control hooks

This phase is simulation-only. No Vicon or physical Crazyflie hardware is used.

---

## 3. Fault Model

A single-motor loss-of-effectiveness fault is injected in the Crazyflie SITL motor pipeline.

For a selected faulted motor i, the effective PWM is modeled as:

    u_i_effective = eta * u_i

where:

- eta = 1.0 means healthy motor
- eta < 1.0 means partial loss of effectiveness
- lower eta means more severe motor degradation

The fault is applied after the nominal firmware motor command is generated.

---

## 4. Touchdown Safety Metric

A key correction made during the project was replacing late touchdown or settled-state evaluation with first-contact evaluation.

The official touchdown row is:

    first row after the fault event where z <= 0.03 m

A touchdown is considered safe only if all checks pass:

- vertical speed <= 0.35 m/s
- horizontal speed <= 0.25 m/s
- roll/pitch tilt <= 12 deg
- angular rate <= 1.5 rad/s
- horizontal drift <= 0.75 m

The dominant failure mode observed near the recoverability boundary was excessive first-contact vertical speed. Horizontal drift, tilt, angular rate, and horizontal velocity generally remained within limits near the final boundary.

---

## 5. Baseline: High-Level Emergency Landing

The first controller used high-level hover/altitude commands only. After fault injection, the vehicle was commanded to perform a max-brake landing using:

    z_cmd = 0.95 m

This high-level interface was not sufficient near the boundary.

For motor 1 at eta = 0.50, high-level max-brake first-contact vertical speed remained unsafe:

    vz approximately 0.44 m/s > 0.35 m/s

This showed that simply commanding a higher altitude target could not reliably recover safe touchdown under the degraded actuator condition.

---

## 6. Level 2 Method: Healthy-Motor Residual FTC

To move beyond high-level control, a firmware-level residual controller was added.

For a faulted motor i, equal residual PWM boost is applied only to healthy motors:

    u_j' = u_j + b,  for j != i
    u_i' = u_i,      for i = faulted motor

where b is the healthy-motor residual boost.

The main tested value was:

    b = 10000 PWM

This is a simple fault-aware residual FTC strategy. It does not replace the nominal controller, but it adds low-level authority after the nominal controller computes motor commands.

---

## 7. Eta = 0.50 Result

At eta = 0.50, high-level landing alone was unsafe for all single-motor faults.

With healthy-motor residual boost, the same fault severity became safe.

Minimum safe boost values observed at eta = 0.50:

| Faulted Motor | Minimum Safe Boost |
|---:|---:|
| 1 | 5000 |
| 2 | 3000 |
| 3 | 5000 |
| 4 | 3000 |

A common boost of 5000 PWM was sufficient to recover safe touchdown for all four motors at eta = 0.50.

Main result from this stage:

Low-level healthy-motor residual control can recover safe touchdown cases that high-level emergency braking cannot.

---

## 8. Eta = 0.45 Result

The severe case eta = 0.45 was tested next.

Equal healthy-motor boost did not recover safe touchdown. Increasing boost reduced impact speed only modestly and eventually destabilized the vehicle at high boost.

Asymmetric residual patterns were also tested for motor 1. The best pattern was approximately:

    r = [0, 6000, 18000, 6000]

but first-contact vertical speed was still approximately:

    vz = 0.90 m/s

This remained far above the safe limit of 0.35 m/s.

Conclusion:

Additive residual allocation improves the boundary region but is not sufficient for severe LoE such as eta = 0.45.

For eta substantially below the boundary, a more structural controller is likely needed, such as fault-aware control allocation, yaw-sacrificing degraded-mode control, or birotor-style emergency control.

---

## 9. Final Recoverability Boundary

The final boundary experiment used:

- boost = 10000 PWM
- 3 repeats per motor per eta
- all four single-motor LoE cases

Tested eta values:

- eta = 0.496
- eta = 0.497
- eta = 0.498

Aggregate result:

| Eta | Motor 1 | Motor 2 | Motor 3 | Motor 4 |
|---:|---:|---:|---:|---:|
| 0.496 | 0/3 safe | 0/3 safe | 0/3 safe | 0/3 safe |
| 0.497 | 3/3 safe | 0/3 safe | 3/3 safe | 3/3 safe |
| 0.498 | 3/3 safe | 3/3 safe | 3/3 safe | 3/3 safe |

Motor 2 was the limiting case at eta = 0.497.

The conservative all-motor recoverability boundary is therefore:

    0.497 < eta_boundary <= 0.498

Main result:

Equal healthy-motor residual FTC with boost = 10000 PWM robustly recovers safe first-contact touchdown for all four single-motor LoE cases at eta = 0.498, while eta = 0.496 remains unsafe for all motors.

---

## 10. Key Figures and Tables

Curated final results are stored in:

- results/final/tables/
- results/final/figures/

Important files:

- results/final/tables/final_recoverability_boundary_table.csv
- results/final/tables/final_recoverability_boundary_summary.md
- results/final/tables/ftcboost_boundary_repeats_allmotors_aggregate.csv
- results/final/tables/ftcboost_boundary_repeats_allmotors_summary.csv
- results/final/figures/ftcboost_boundary_repeats_allmotors.png
- results/final/figures/ftcboost_fine_boundary_m1.png
- results/final/figures/ftcboost_allmotors_eta0p50_vertical_speed.png
- results/final/figures/ftcresid_m1_eta0p45_patterns.png

---

## 11. Current Contribution

The project currently demonstrates:

1. High-level emergency landing is insufficient near the single-motor LoE boundary.
2. First-contact touchdown evaluation is necessary to avoid false-safe conclusions.
3. Low-level residual motor control can shift the recoverability boundary.
4. Equal healthy-motor residual FTC robustly recovers all single-motor LoE cases at eta = 0.498.
5. More severe faults such as eta = 0.45 require a structural degraded-mode controller rather than additive boost tuning.

---

## 12. Next Research Direction

The next method should not be more blind boost tuning.

The next controller should move toward one of:

- fault-aware constrained control allocation
- motor-specific residual optimization
- yaw-sacrificing degraded-mode control
- birotor-style emergency landing
- INDI-style acceleration feedback control
- NMPC with degraded rotor constraints

The most natural next step is:

Design a fault-aware allocation layer that chooses motor-specific residuals subject to thrust, tilt, drift, angular-rate, and saturation constraints, instead of applying equal boost to all healthy motors.
