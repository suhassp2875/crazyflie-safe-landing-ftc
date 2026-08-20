# Paper and Reproduction Scripts

This directory contains the **33 retained scripts** required to support the final paper-facing experiment and analysis workflow.

Early exploratory runners, obsolete controller variants, pre-final boundary studies, and scripts tied only to removed development artifacts were intentionally removed from the release branch. They remain recoverable through Git history and the `experimental-freeze` tag.

The retained scripts fall into five groups.

## 1. Core experiment execution

```text
fault_triggered_landing_qp_event_allocator.py
fault_triggered_landing_motor_supervisor.py
seeded_trial_params.py
```

`fault_triggered_landing_qp_event_allocator.py` is the main final experiment runner for PINV, QP-lite, and frozen CEM-tuned QP-lite.

`fault_triggered_landing_motor_supervisor.py` implements the motor-conditioned integrated supervisor under supplied failed-motor identity.

`seeded_trial_params.py` provides deterministic seeded initial-condition generation for repeated and paired experiments.

## 2. PINV / controller-complementarity pipeline

```text
run_seeded_pinv_eta0p496.sh
run_seeded_cem_matched_eta0p496.sh
compare_pinv_qplite_paired_eta0p496.py
report_pinv_seeded_eta0p496.py
summarize_pinv_seeded_eta0p496.py
summarize_seeded_trials.py
```

These scripts support the matched development comparison used to select:

```text
M1 -> CEM
M2 -> PINV
M3 -> CEM
M4 -> CEM
```

## 3. Holdout and integrated supervisor

```text
summarize_motor_conditioned_holdout_eta0p496.py
run_randomized_motor_supervisor_eta0p496.sh
summarize_randomized_motor_supervisor_eta0p496.py
analyze_randomized_supervisor_failures_eta0p496.py
```

These support the final:

```text
fresh holdout:        117/120
integrated supervisor: 115/120
```

## 4. M2 boundary and model sensitivity

```text
plant_ofat.py
run_nominal_m2_pinv_fine_boundary.sh
validate_nominal_m2_boundary_trial.py
summarize_nominal_m2_pinv_fine_boundary.py
analyze_nominal_m2_pinv_fine_boundary.py
run_ofat_m2_pinv_fine_sweep.sh
summarize_ofat_m2_pinv_fine_sweep.py
analyze_ofat_m2_pinv_sensitivity.py
plot_ofat_m2_pinv_tornado.py
run_m2_routing_stability_eta0p496.sh
summarize_m2_routing_stability.py
```

These support:

- the nominal M2/PINV ED50 result,
- the +/-10% OFAT plant-sensitivity experiment,
- the active-constraint analysis,
- the fixed-eta PINV-vs-CEM routing-stability experiment.

## 5. CEM tuning, verification, and synthesis

```text
cem_tune_allocator_weights.py
smoke_test_pinv_fault.py
summarize_pinv_smoke_matrix.py
test_fault_aware_pinv_reference.py
validate_pinv_firmware_reference.py
validate_pinv_healthy_invariance.py
build_model_sensitivity_synthesis.py
build_project_experimental_synthesis.py
```

CEM is used offline for tuning. It is not reinforcement learning and is not executed as an online optimizer in the final runtime controller.

The two synthesis builders produce the paper-facing result packages without launching new simulation.

## Recommended reading order

For a reviewer or reproducer:

```text
1. ../README.md
2. ../docs/REPRODUCIBILITY.md
3. fault_triggered_landing_qp_event_allocator.py
4. fault_triggered_landing_motor_supervisor.py
5. plant_ofat.py
6. build_model_sensitivity_synthesis.py
7. build_project_experimental_synthesis.py
```

The retained script paths are intentionally stable so that the final result provenance remains easy to trace.
