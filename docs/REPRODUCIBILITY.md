# Reproducibility Guide

This document records the software revisions, firmware patch, controller configuration, evaluation conventions, and paper-facing result locations used for the Crazyflie emergency-landing experiments.

The goal is to make the final paper results traceable without requiring readers to reconstruct the project's development history.

---

## 1. Release provenance

Paper/release branch:

```text
crazyflie-v1.0
```

Experimental state immediately before repository cleanup:

```text
experimental-freeze
```

The `experimental-freeze` tag preserves the exact project state from which the final release curation began.

---

## 2. Simulation software revisions

### CrazySim

Repository:

```text
https://github.com/gtfactslab/CrazySim.git
```

Pinned revision:

```text
3ec8b55da4bff887da542a9f314da825460e65be
```

Commit summary:

```text
Add flowdeck docs and replace ASCII diagram with architecture image in README
```

### Crazyflie firmware

Repository:

```text
https://github.com/llanesc/crazyflie-firmware.git
```

Pinned base revision:

```text
aa6571dc465f06f7d1f9aaf7b0b861fbcd1b3d67
```

Commit summary:

```text
Update crazyflie-simulation submodule (flowdeck simulation)
```

The fault-injection and allocator implementation is supplied as a patch against this firmware revision.

---

## 3. Firmware patch

Tracked patch:

```text
patches/fault_aware_bounded_allocator.patch
```

SHA-256:

```text
cab514533873039c75c0207cd7557f802047eddc5c6cee974ff168b9666ffe45
```

The release patch was checked against the active experimental firmware and was byte-for-byte identical to the active diff.

It was also verified to apply cleanly to the pinned firmware base revision:

```text
aa6571dc465f06f7d1f9aaf7b0b861fbcd1b3d67
```

### Patch application

From a clean checkout of the pinned firmware revision:

```bash
git checkout aa6571dc465f06f7d1f9aaf7b0b861fbcd1b3d67
git apply /path/to/safe-landing-ftc/patches/fault_aware_bounded_allocator.patch
```

A dry-run check can be performed first with:

```bash
git apply --check /path/to/safe-landing-ftc/patches/fault_aware_bounded_allocator.patch
```

---

## 4. Experimental software environment

The final experiments were run with:

```text
Ubuntu 22.04
ROS 2 Humble
Gazebo Sim 7.9.0
CrazySim / Crazyflie SITL
Python 3.10
cflib
```

The project was run from the Conda environment:

```text
crazysim310
```

This release records the source revisions and controller artifacts used by the experiments. Exact package recreation may additionally depend on the local ROS 2 / Gazebo installation.

---

## 5. Fault model

For faulted motor \(i\), remaining effectiveness is represented by

\[
u_i^{\mathrm{effective}}=\eta u_i.
\]

Interpretation:

- \(\eta=1\): healthy motor
- \(0<\eta<1\): partial loss of effectiveness
- smaller \(\eta\): more severe loss of effectiveness

The main controller-complementarity and supervisor experiments use:

```text
eta = 0.496
```

Only one motor is faulted at a time.

Failed-motor identity is supplied to the supervisor. Online fault detection and isolation are outside the scope of this release.

---

## 6. First-contact safety definition

The official touchdown sample is the first post-fault row satisfying:

```text
z <= 0.03 m
```

A trial is safe only if all of the following conditions hold at first contact:

| Quantity | Limit |
|---|---:|
| Vertical speed | <= 0.35 m/s |
| Horizontal speed | <= 0.25 m/s |
| Roll/pitch magnitude | <= 12 deg |
| Angular rate | <= 1.5 rad/s |
| Horizontal drift | <= 0.75 m |
| Ground contact | required |

Safety-criterion violations can overlap. Criterion counts therefore must not be interpreted as mutually exclusive failure classes.

---

## 7. Controller implementations

### Main experiment runner

```text
scripts/fault_triggered_landing_qp_event_allocator.py
```

Supported controller families used in the final comparison include:

```text
qplite
pinv
```

### Bounded WLS/PINV

The bounded allocator uses fixed weights:

```text
[1, 1, 1, 0.2]
```

and regularization:

```text
lambda = 1e-6
```

The implementation operates in the Crazyflie PWM command domain and compensates for known motor effectiveness subject to command bounds.

It should not be interpreted as a full physical force/wrench allocator.

### Frozen CEM-tuned residual policy

Configuration:

```text
configs/allocator_weights/cem_tuned_boundary.json
```

SHA-256:

```text
705310dda32718993a3df38353caa567d4ca1387b0652b507130c889ea713a5b
```

CEM is used offline for score-weight tuning only.

At runtime:

- CEM is not executed,
- no reinforcement-learning policy is used,
- QP-lite selects from a fixed empirical residual candidate library,
- no formal continuous CBF-QP guarantee is claimed.

---

## 8. Frozen routing policy

The controller-complementarity development experiment produced:

| Failed motor | PINV | QP-lite | CEM-tuned | Frozen selection |
|---|---:|---:|---:|---|
| M1 | 26/30 | 4/30 | 30/30 | CEM |
| M2 | 30/30 | 6/30 | 3/30 | PINV |
| M3 | 19/30 | 28/30 | 29/30 | CEM |
| M4 | 0/30 | 5/30 | 23/30 | CEM |

Frozen routing:

```text
M1 -> CEM
M2 -> PINV
M3 -> CEM
M4 -> CEM
```

The development-selected result is:

```text
112/120
```

This is in-sample and must not be reported as independent validation.

---

## 9. Primary validation results

### Fresh-seed frozen-policy holdout

Authoritative directory:

```text
results/final/pinv_baseline/seeded_eta0p496/motor_conditioned_holdout/
```

Result:

```text
M1: 30/30
M2: 30/30
M3: 30/30
M4: 27/30

Overall: 117/120 = 97.5%
```

Wilson 95% confidence interval:

```text
approximately [92.9%, 99.1%]
```

### Randomized integrated supervisor

Authoritative directory:

```text
results/final/pinv_baseline/seeded_eta0p496/randomized_supervisor/production120/
```

Result:

```text
M1: 29/30
M2: 30/30
M3: 30/30
M4: 26/30

Overall: 115/120 = 95.8%
```

A later M4-modified supervisor achieved:

```text
113/120
```

and was not retained.

---

## 10. Seeded trial protocol

Seeded trial generation is implemented in:

```text
scripts/seeded_trial_params.py
```

Protocol identifier:

```text
seeded_ic_v1
```

Randomized quantities include:

```text
spawn x:      uniform +/- 0.03 m
spawn y:      uniform +/- 0.03 m
hover z:      0.70 +/- 0.02 m
fault time:   10.0 +/- 0.25 s
```

Spawn yaw is generated/logged within approximately +/-5 deg, but the current launcher does not apply that yaw value. It therefore must not be described as an applied randomized initial condition.

---

## 11. Plant-model sensitivity

Plant perturbations are managed by:

```text
scripts/plant_ofat.py
```

The sensitivity study independently perturbs five physical/model parameters by +/-10%:

```text
mass
thrust_coefficient
motor_time_constant
thrust_to_torque_ratio
arm_length
```

The study is one-factor-at-a-time (OFAT). Simultaneous multi-parameter mismatch is not evaluated.

### Nominal M2/PINV boundary

Paper-level reporting:

```text
eta50 ~= 0.4956
95% within-model interval ~= [0.4955, 0.4956]
```

Because \(\eta\) is remaining effectiveness:

> Lower ED50 means better LoE tolerance.

Full-precision values are retained in the analysis files, but paper prose should use meaningful rounded precision.

### Sensitivity ranking

Maximum absolute ED50 shifts:

| Rank | Parameter | max abs(Delta ED50) |
|---:|---|---:|
| 1 | Thrust coefficient | 0.05495 |
| 2 | Mass | 0.04974 |
| 3 | Motor time constant | 0.000404 |
| 4 | Arm length | 0.000262 |
| 5 | Thrust-to-torque ratio | 0.000262 |

The practical boundary uncertainty is dominated by mass and thrust-coefficient uncertainty rather than repeated-seed uncertainty within the nominal simulator.

---

## 12. Active-constraint change under model mismatch

The sensitivity study shows that plant mismatch can change the dominant safety limitation.

For the mass -10% fine-boundary condition:

```text
vertical-speed violations:    0
horizontal-speed violations: 72
tilt violations:             46
angular-rate violations:    150
drift violations:             0
```

Angular rate is therefore the most frequent violated criterion in this condition.

Criterion counts overlap.

The thrust-coefficient +10% condition likewise exhibits angular-rate-limited failures rather than the vertical-speed-dominated pattern seen in many other conditions.

---

## 13. M2 routing stability under plant mismatch

At fixed:

```text
eta = 0.496
```

PINV and frozen CEM are compared under the nominal plant and all ten OFAT perturbations.

Across all 11 plant states:

```text
PINV higher safe-touchdown count: 9/11
tie:                              2/11
CEM higher safe-touchdown count:  0/11
```

Across the ten perturbed states only:

```text
PINV higher safe-touchdown count: 8/10
tie:                              2/10
CEM higher safe-touchdown count:  0/10
```

The two adverse ties are:

```text
mass +10%:               PINV 0/30, CEM 0/30
thrust coefficient -10%: PINV 0/30, CEM 0/30
```

These observations support the interpretation that controller selection and available plant authority are distinct limitations.

No formal attainable-wrench-set proof is claimed.

---

## 14. Paper-facing synthesis

### Whole-project synthesis

Directory:

```text
results/final/project_experimental_synthesis/
```

Important outputs:

```text
controller_complementarity.csv
validation_summary_by_motor.csv
overall_stage_summary.csv
model_sensitivity_ranking.csv
whole_project_claims.md
experimental_results_narrative.md
provenance.json
```

Rebuild:

```bash
python scripts/build_project_experimental_synthesis.py
```

### Model-sensitivity synthesis

Directory:

```text
results/final/model_sensitivity/ofat/synthesis/
```

Important outputs:

```text
model_sensitivity_master_table.csv
parameter_sensitivity_ranking.csv
failure_mechanism_summary.csv
routing_stability_compact.csv
model_sensitivity_claims.md
model_sensitivity_results.md
ofat_ed50_tornado.png
```

Rebuild:

```bash
python scripts/build_model_sensitivity_synthesis.py
```

These synthesis builders do not launch new simulation. They derive curated paper-facing outputs from the authoritative experiment files.

---

## 15. Minimal paper-result rebuild

From the project repository:

```bash
conda activate crazysim310

python scripts/plant_ofat.py verify
python scripts/build_model_sensitivity_synthesis.py
python scripts/build_project_experimental_synthesis.py
```

Before sensitivity analysis is regenerated, the active CrazySim plant should be verified as nominal.

---

## 16. Reproduction levels

### Level A — core paper evidence

Reproduce or inspect:

1. controller-complementarity table,
2. frozen routing policy,
3. fresh-seed holdout,
4. integrated randomized supervisor.

These establish the main fault-geometry-aware allocation result.

### Level B — robustness evidence

Reproduce or inspect:

1. nominal M2/PINV fine boundary,
2. OFAT fine-boundary sensitivity,
3. failure-mechanism summary,
4. M2 PINV-vs-CEM routing stability.

These establish the model-sensitivity claims.

### Level C — supporting and negative experiments

The repository also preserves supporting experiments such as:

- M4 authority tuning,
- supervisor-v2 evaluation,
- earlier boundary-localization runs,
- candidate and guard studies.

These are useful for provenance but are not required to understand the main paper claim.

---

## 17. Scope and limitations

The release does not establish:

- physical Crazyflie hardware robustness,
- online fault detection or isolation,
- robustness to unknown failed-motor identity,
- simultaneous multi-motor failures,
- simultaneous multi-parameter model mismatch,
- universal robustness outside the tested simulator/domain,
- formal closed-loop safety guarantees,
- formal attainable-wrench feasibility,
- globally optimal residual allocation,
- formal CBF-QP control,
- reinforcement-learning-based fault-tolerant control.

The paper-level question is deliberately narrower:

> Given known partial LoE of one motor, can fault-dependent allocation improve safe emergency first-contact landing, and how sensitive is that conclusion to plant-model mismatch?
