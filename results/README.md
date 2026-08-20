# Final Results

This directory contains the **paper-supporting experimental results** for the Crazyflie single-motor loss-of-effectiveness emergency-landing study.

The release intentionally excludes early exploratory sweeps, obsolete figures, transient console outputs, pre-fix data, and development-only mechanism studies. Those remain recoverable through Git history and the `experimental-freeze` tag.

The retained result tree is organized around the final paper argument:

```text
results/final/
├── cem_tuning/
├── pinv_baseline/
├── model_sensitivity/
└── project_experimental_synthesis/
```

---

## 1. `project_experimental_synthesis/` — paper-level summary

This is the shortest path to the final experimental story.

Key files include:

```text
controller_complementarity.csv
validation_summary_by_motor.csv
overall_stage_summary.csv
model_sensitivity_ranking.csv
whole_project_claims.md
experimental_results_narrative.md
provenance.json
```

Headline results:

```text
Development-selected routing:     112/120
Fresh-seed frozen-policy holdout: 117/120
Integrated randomized supervisor: 115/120
```

Frozen routing:

```text
M1 -> CEM
M2 -> PINV
M3 -> CEM
M4 -> CEM
```

Rebuild with:

```bash
python scripts/build_project_experimental_synthesis.py
```

---

## 2. `pinv_baseline/` — allocator complementarity and supervisor validation

The retained paper-relevant experiments are under:

```text
results/final/pinv_baseline/seeded_eta0p496/
```

### `production_30/`

Matched 30-seed development comparison at:

```text
eta = 0.496
```

Controller outcomes:

| Failed motor | PINV | QP-lite | CEM-tuned | Selected |
|---|---:|---:|---:|---|
| M1 | 26/30 | 4/30 | 30/30 | CEM |
| M2 | 30/30 | 6/30 | 3/30 | PINV |
| M3 | 19/30 | 28/30 | 29/30 | CEM |
| M4 | 0/30 | 5/30 | 23/30 | CEM |

The resulting selected-policy development total is:

```text
112/120
```

This is **in-sample** because the same development block is used to choose the routing map.

### `motor_conditioned_holdout/`

Fresh-seed evaluation after the routing policy was frozen:

```text
M1 CEM:  30/30
M2 PINV: 30/30
M3 CEM:  30/30
M4 CEM:  27/30

Overall: 117/120 = 97.5%
```

This is the primary independent fresh-seed validation within the same simulator and initial-condition distribution.

### `randomized_supervisor/production120/`

Integrated supervisor evaluation with randomized motor-case execution order:

```text
M1 CEM:  29/30
M2 PINV: 30/30
M3 CEM:  30/30
M4 CEM:  26/30

Overall: 115/120 = 95.8%
```

Failed-motor identity is supplied to the supervisor.

### `randomized_supervisor/production120_v2/`

Negative-result follow-up:

```text
Overall: 113/120
```

The modified M4 policy did not improve the retained supervisor, so `production120/` remains the primary integrated result.

---

## 3. `cem_tuning/` — offline CEM tuning evidence

This directory contains the curated evidence for the offline Cross-Entropy Method tuning stage.

Files include:

```text
cem_baseline_candidate_choices.csv
cem_baseline_vs_tuned_scenario_rows.csv
cem_baseline_vs_tuned_summary.csv
cem_tuned_candidate_choices.csv
cem_tuning_history.csv
cem_tuning_history.png
```

CEM is used **offline** to tune the QP-lite scoring configuration.

It is not reinforcement learning and is not executed as an online optimizer during the final controller evaluation.

The frozen runtime configuration is stored at:

```text
configs/allocator_weights/cem_tuned_boundary.json
```

---

## 4. `model_sensitivity/` — M2/PINV boundary and robustness study

The final sensitivity result tree retains four components.

### `nominal_m2_boundary/pinv_fine_boundary/`

Fine nominal M2/PINV boundary experiment.

Paper-level result:

```text
eta50 ~= 0.4956
95% within-model interval ~= [0.4955, 0.4956]
```

Because eta denotes **remaining effectiveness**, lower ED50 means greater LoE tolerance.

The very narrow interval is a within-model repeated-trial result, not a claim of equivalent physical-model certainty.

### `ofat/pinv_boundary_fine_sweep/`

Final one-factor-at-a-time fine sweep.

Five parameters are perturbed independently by +/-10%:

```text
mass
thrust_coefficient
motor_time_constant
thrust_to_torque_ratio
arm_length
```

The final sweep contains:

```text
10 perturbed conditions
7 eta values per condition
30 paired seeds
2100 trials
```

### `ofat/sensitivity_analysis/`

Statistical bridge between the OFAT sweep and the paper synthesis.

This directory contains the Firth ED50 estimates and associated uncertainty calculations used by the final sensitivity synthesis.

It is a **required paper-pipeline input** and should not be removed.

The main sensitivity ranking is:

| Rank | Parameter | max abs(Delta ED50) |
|---:|---|---:|
| 1 | Thrust coefficient | 0.05495 |
| 2 | Mass | 0.04974 |
| 3 | Motor time constant | 0.000404 |
| 4 | Arm length | 0.000262 |
| 5 | Thrust-to-torque ratio | 0.000262 |

Mass and thrust coefficient therefore dominate the observed boundary shifts.

### `ofat/m2_routing_stability_eta0p496/`

Fixed-operating-point comparison of PINV and frozen CEM for M2 at:

```text
eta = 0.496
```

Across the nominal plant and ten OFAT perturbations:

```text
PINV higher safe-touchdown count: 9/11
tie:                              2/11
CEM higher safe-touchdown count:  0/11
```

Across the ten perturbed states only:

```text
PINV higher count: 8/10
tie:              2/10
CEM higher count: 0/10
```

The two adverse ties are:

```text
mass +10%:               PINV 0/30, CEM 0/30
thrust coefficient -10%: PINV 0/30, CEM 0/30
```

These results support the distinction between **controller-selection robustness** and **available plant authority**.

### `ofat/synthesis/`

Curated model-sensitivity package.

Key files:

```text
model_sensitivity_master_table.csv
parameter_sensitivity_ranking.csv
failure_mechanism_summary.csv
routing_stability_compact.csv
model_sensitivity_claims.md
model_sensitivity_results.md
ofat_ed50_tornado.png
README.md
```

Rebuild with:

```bash
python scripts/build_model_sensitivity_synthesis.py
```

---

## 5. Active safety-constraint result

The model-sensitivity study shows that plant mismatch can change the dominant failure mechanism.

For the mass -10% condition:

```text
vertical-speed violations:    0
horizontal-speed violations: 72
tilt violations:             46
angular-rate violations:    150
drift violations:             0
```

Angular rate is therefore the most frequent violated criterion in that condition.

The thrust-coefficient +10% condition also shows angular-rate-limited failures.

Most other tested conditions are primarily vertical-speed limited.

Violation counts are **not mutually exclusive**.

---

## 6. Result provenance

The release keeps these result classes deliberately separate:

```text
112/120  development data used to select the routing map
117/120  fresh-seed frozen-policy validation
115/120  separate integrated supervisor evaluation
113/120  negative supervisor-v2 follow-up
```

The repository does not present development-set performance as holdout validation.

---

## 7. What was removed from the paper-facing release

The release omits result families that were useful during development but are not needed to support the final paper claims, including:

- early equal-boost and residual-dose studies,
- coarse pre-final boundary studies,
- pre-cadence-fix data,
- contact-audit plots,
- transient-mechanism diagnostics,
- older motor-authority visualizations,
- obsolete aggregate figures and tables,
- runtime consoles and simulator logs.

These artifacts remain recoverable through:

```text
experimental-freeze
```

and the repository's Git history.

---

## 8. Recommended reading order

For the fastest verification of the paper:

```text
1. project_experimental_synthesis/
2. pinv_baseline/seeded_eta0p496/production_30/
3. pinv_baseline/seeded_eta0p496/motor_conditioned_holdout/
4. pinv_baseline/seeded_eta0p496/randomized_supervisor/production120/
5. model_sensitivity/nominal_m2_boundary/pinv_fine_boundary/
6. model_sensitivity/ofat/sensitivity_analysis/
7. model_sensitivity/ofat/m2_routing_stability_eta0p496/
8. model_sensitivity/ofat/synthesis/
```

For exact software and firmware provenance, see:

```text
docs/REPRODUCIBILITY.md
```
