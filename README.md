# Fault-Geometry-Aware Control Allocation for Emergency Quadrotor Landing under Single-Motor Loss of Effectiveness

This repository contains the simulation framework, controller implementations, experiment orchestration, and curated results for **fault-tolerant emergency landing of a Crazyflie-class quadrotor under partial single-motor loss of effectiveness (LoE)**.

The central experimental finding is:

> **No single tested control-allocation strategy is best across all single-motor fault geometries.**

A bounded weighted-least-squares allocator is strongest for the M2 failure geometry, while a CEM-tuned residual allocator is stronger for M1, M3, and M4. This motivates a **fault-geometry-aware supervisor** that selects the allocation strategy using the known failed-motor identity.

The frozen routing policy achieved:

| Evaluation | Safe first-contact touchdowns |
|---|---:|
| Development-selected routing | 112/120 (93.3%) |
| **Fresh-seed holdout** | **117/120 (97.5%)** |
| **Randomized integrated supervisor** | **115/120 (95.8%)** |

The development result is used to select the routing map and is therefore **not an independent validation result**. The 117/120 result is the primary fresh-seed validation after the routing policy was frozen.

A subsequent plant-model sensitivity study shows that the safety boundary is dominated by **mass and thrust coefficient uncertainty**, and that model mismatch can change not only where failure occurs but also **which safety constraint becomes active**.

> **Scope assumption:** failed-motor identity is supplied to the supervisor. This work studies control allocation and reconfiguration after the failed motor is known; it does not implement or validate online fault detection or fault isolation.

---

## Contents

- [Problem formulation](#problem-formulation)
- [Safety definition](#safety-definition)
- [Allocation methods](#allocation-methods)
- [Result 1: allocator complementarity](#result-1-allocator-complementarity)
- [Result 2: frozen-policy validation](#result-2-frozen-policy-validation)
- [Result 3: integrated supervisor](#result-3-integrated-supervisor)
- [Result 4: model mismatch changes the failure mode](#result-4-model-mismatch-changes-the-failure-mode)
- [Result 5: M2/PINV safety boundary](#result-5-m2pinv-safety-boundary)
- [Result 6: plant-model sensitivity](#result-6-plant-model-sensitivity)
- [Result 7: routing stability under plant mismatch](#result-7-routing-stability-under-plant-mismatch)
- [Simulation platform](#simulation-platform)
- [Repository structure](#repository-structure)
- [Paper-facing result packages](#paper-facing-result-packages)
- [Reproducibility](#reproducibility)
- [Result provenance](#result-provenance)
- [Limitations](#limitations)

---

## Problem formulation

For a faulted motor \(i\), remaining effectiveness is modeled as

\[
u_i^{\mathrm{effective}} = \eta u_i,
\]

where:

- \(\eta = 1\) denotes a healthy motor,
- \(0 < \eta < 1\) denotes partial loss of effectiveness,
- smaller \(\eta\) denotes a more severe fault.

The study considers one failed motor at a time: **M1, M2, M3, or M4**.

The primary controller-complementarity and supervisor experiments are performed at:

\[
\eta = 0.496.
\]

For the single-motor LoE setting studied here, the failed-motor index determines the corresponding actuator/control-authority geometry. The implemented supervisor therefore instantiates **fault-geometry-aware routing through discrete failed-motor identity**.

---

## Safety definition

Safety is evaluated at the **first post-fault ground-contact sample**, defined as the first row satisfying:

\[
z \le 0.03\ \mathrm{m}.
\]

A touchdown is considered safe only when **all** criteria pass:

| Quantity | Safety limit |
|---|---:|
| Vertical speed | \(\le 0.35\) m/s |
| Horizontal speed | \(\le 0.25\) m/s |
| Roll/pitch magnitude | \(\le 12^\circ\) |
| Angular rate | \(\le 1.5\) rad/s |
| Horizontal drift | \(\le 0.75\) m |
| Ground contact | Required |

Safety-criterion violations are **not mutually exclusive**. A single unsafe trial may violate more than one constraint.

This multidimensional first-contact definition is used throughout the final evaluation.

---

## Allocation methods

### Bounded WLS/PINV

The model-informed allocator performs bounded weighted least-squares allocation in the Crazyflie PWM-command domain.

The final configuration uses:

\[
w_T=w_R=w_P=1,\qquad w_Y=0.2,
\]

with regularization:

\[
\lambda=10^{-6}.
\]

The implementation compensates for known motor effectiveness while respecting motor-command limits.

This is a **PWM-domain command-effectiveness allocator**. It is not presented as a complete physical force-domain or attainable-wrench allocator.

### QP-lite residual allocation

QP-lite evaluates an empirical library of bounded motor-residual candidates and selects one using a quadratic state-dependent score.

It is **not a formal continuous CBF-QP**, and no formal CBF-QP safety guarantee is claimed.

### CEM-tuned QP-lite

The Cross-Entropy Method (CEM) is used **offline** to tune the QP-lite scoring configuration.

At runtime:

- CEM is not executed,
- no reinforcement-learning policy is used,
- the residual candidate library remains fixed,
- the controller selects candidates using frozen scoring weights.

Final configuration:

```text
configs/allocator_weights/cem_tuned_boundary.json
```

---

## Result 1: allocator complementarity

The three controllers are compared using the same 30-seed development block for each failed motor at \(\eta=0.496\).

| Failed motor | Bounded WLS/PINV | QP-lite | CEM-tuned | Selected |
|---|---:|---:|---:|---|
| M1 | 26/30 | 4/30 | **30/30** | CEM |
| M2 | **30/30** | 6/30 | 3/30 | PINV |
| M3 | 19/30 | 28/30 | **29/30** | CEM |
| M4 | 0/30 | 5/30 | **23/30** | CEM |

The resulting frozen routing policy is:

```text
M1 -> CEM
M2 -> PINV
M3 -> CEM
M4 -> CEM
```

The main conclusion is not that one allocator globally dominates. It is the opposite:

> **Allocator suitability depends strongly on the failed-motor geometry.**

The M2 preference for bounded WLS/PINV is particularly strong. M3 is the closest development comparison: CEM achieves 29/30 while ordinary QP-lite achieves 28/30. This near-tie is retained explicitly rather than presented as a large separation.

Applying the selected policy back to the same development data gives:

\[
112/120 = 93.3\%.
\]

This is an **in-sample controller-selection result**, not independent validation.

Authoritative development table:

```text
results/final/project_experimental_synthesis/controller_complementarity.csv
```

---

## Result 2: frozen-policy validation

After the routing map was selected, it was frozen and evaluated on a fresh 30-seed block for each failed motor.

| Failed motor | Frozen controller | Safe touchdowns |
|---|---|---:|
| M1 | CEM | 30/30 |
| M2 | PINV | 30/30 |
| M3 | CEM | 30/30 |
| M4 | CEM | 27/30 |
| **Overall** | — | **117/120** |

Overall:

\[
\boxed{117/120 = 97.5\%}
\]

with Wilson 95% confidence interval approximately:

\[
[92.9\%,\,99.1\%].
\]

This is a **fresh-seed validation under the same simulator and initial-condition distribution**. It does not establish transfer to physical hardware or to a different fault distribution.

Authoritative holdout results:

```text
results/final/pinv_baseline/seeded_eta0p496/motor_conditioned_holdout/
```

---

## Result 3: integrated supervisor

The same frozen routing policy was then evaluated as an integrated supervisor with randomized motor-case execution order.

| Failed motor | Selected controller | Safe touchdowns |
|---|---|---:|
| M1 | CEM | 29/30 |
| M2 | PINV | 30/30 |
| M3 | CEM | 30/30 |
| M4 | CEM | 26/30 |
| **Overall** | — | **115/120** |

Overall:

\[
\boxed{115/120 = 95.8\%}.
\]

The failed-motor identity is supplied by the experiment. This result validates **controller selection and execution under known fault identity**, not online fault diagnosis.

Authoritative retained-supervisor results:

```text
results/final/pinv_baseline/seeded_eta0p496/randomized_supervisor/production120/
```

A later M4 modification was also evaluated. That supervisor-v2 experiment achieved **113/120**, below the retained 115/120 result, so the original frozen policy was kept.

The negative result is retained in the repository as part of the experimental record rather than omitted.

---

## Result 4: model mismatch changes the failure mode

The final sensitivity study perturbs five plant parameters independently by \(\pm10\%\):

- total mass,
- physical thrust coefficient,
- motor time constant,
- thrust-to-torque ratio,
- physical arm length.

The sensitivity study reveals a non-obvious result:

> **Plant mismatch can change not only where the safety boundary lies, but also how the landing becomes unsafe.**

For the **mass -10%** fine-boundary sweep:

| Violated criterion | Count |
|---|---:|
| Vertical speed | 0 |
| Horizontal speed | 72 |
| Tilt | 46 |
| Angular rate | **150** |
| Drift | 0 |

Angular rate is therefore the most frequent violated safety criterion in this condition, with additional horizontal-speed and tilt violations.

For the **thrust-coefficient +10%** condition, unsafe trials are likewise associated with angular-rate violation rather than vertical-speed violation.

Most of the remaining tested perturbations are primarily vertical-speed limited.

Because criterion counts overlap, these values must not be interpreted as mutually exclusive failure classes.

This result shows that model uncertainty can alter the **active safety limitation**, rather than merely translating a fixed vertical-impact-speed boundary.

---

## Result 5: M2/PINV safety boundary

M2 is the failure geometry for which bounded WLS/PINV most strongly outperforms the residual controllers, so its LoE boundary is characterized in greater detail.

Using Firth bias-reduced logistic regression, the nominal simulator gives approximately:

\[
\boxed{\eta_{50} \approx 0.4956}
\]

with a within-model paired-seed bootstrap 95% interval of approximately:

\[
\boxed{[0.4955,\ 0.4956]}.
\]

Because \(\eta\) represents **remaining motor effectiveness**:

> **Lower ED50 is better.**

A lower ED50 means that the controller remains safe under a more severe motor LoE.

The narrow nominal interval characterizes repeated-trial uncertainty **within the fixed plant model and tested seed distribution**. It should not be interpreted as equivalent uncertainty about a physical vehicle.

---

## Result 6: plant-model sensitivity

Applying the same boundary analysis under the ten \(\pm10\%\) one-factor-at-a-time plant perturbations gives:

| Rank | Parameter | Maximum \(|\Delta \mathrm{ED50}|\) |
|---:|---|---:|
| 1 | **Thrust coefficient** | **0.05495** |
| 2 | **Mass** | **0.04974** |
| 3 | Motor time constant | 0.000404 |
| 4 | Arm length | 0.000262 |
| 5 | Thrust-to-torque ratio | 0.000262 |

Representative shifts:

| Perturbation | \(\Delta \mathrm{ED50}\) | Interpretation |
|---|---:|---|
| Mass -10% | -0.04714 | Improved LoE tolerance |
| Mass +10% | +0.04974 | Reduced LoE tolerance |
| Thrust coefficient -10% | +0.05495 | Reduced LoE tolerance |
| Thrust coefficient +10% | -0.04538 | Improved LoE tolerance |

Because lower ED50 corresponds to greater LoE tolerance, increased mass and reduced thrust coefficient degrade the boundary, whereas reduced mass and increased thrust coefficient improve it.

The important contrast is:

> **The safety transition can be localized sharply within a fixed plant model, but plausible plant mismatch moves the estimated boundary by roughly two orders of magnitude more. Practical boundary uncertainty is therefore dominated by model uncertainty rather than repeated-trial uncertainty in the nominal simulator.**

Paper-facing sensitivity outputs:

```text
results/final/model_sensitivity/ofat/synthesis/
```

> **ED50 convention:** \(\eta\) is remaining effectiveness; therefore lower ED50 means better fault tolerance.

---

## Result 7: routing stability under plant mismatch

A separate fixed-operating-point experiment tests whether the nominal M2 routing choice between PINV and frozen CEM reverses under the same plant perturbations.

The comparison is performed at:

\[
\eta = 0.496.
\]

Across the nominal plant plus ten perturbed plants:

| Routing outcome | Plant states |
|---|---:|
| PINV higher safe-touchdown count | **9/11** |
| Tie | **2/11** |
| CEM higher safe-touchdown count | **0/11** |

Considering only the ten perturbed plant models:

| Routing outcome | Perturbed states |
|---|---:|
| PINV higher safe-touchdown count | **8/10** |
| Tie | **2/10** |
| CEM higher safe-touchdown count | **0/10** |

PINV's paired advantage reaches McNemar \(p<0.05\) in 7 of the 10 perturbed conditions.

The two tied adverse cases are:

| Perturbation | PINV | CEM |
|---|---:|---:|
| Mass +10% | 0/30 | 0/30 |
| Thrust coefficient -10% | 0/30 | 0/30 |

No tested perturbation reverses the M2 routing direction in favor of CEM at \(\eta=0.496\).

However:

> **Stable controller ordering does not imply safety robustness.**

For +10% mass and -10% thrust coefficient, neither tested controller achieves a safe touchdown in any of the 30 paired trials at the tested operating point.

This is consistent with an **available-control-authority limitation rather than merely a controller-selection limitation**. No formal attainable-wrench-set proof is claimed.

Authoritative routing-stability results:

```text
results/final/model_sensitivity/ofat/m2_routing_stability_eta0p496/
```

---

## Experimental story

The completed experiments support the following evidence chain:

```text
Single-motor partial LoE
          |
          v
Different failed motors induce different
actuator/control-authority geometries
          |
          v
Allocator performance depends on fault geometry
          |
          +--> M1 -> CEM
          +--> M2 -> PINV
          +--> M3 -> CEM
          +--> M4 -> CEM
          |
          v
Freeze routing policy
          |
          +--> Development selection: 112/120
          |
          +--> Fresh-seed holdout: 117/120
          |
          +--> Randomized integrated supervisor: 115/120
          |
          v
Stress the critical M2/PINV branch
          |
          +--> Mass and thrust coefficient dominate ED50 shifts
          |
          +--> Active touchdown-safety constraint can change
          |
          +--> PINV-vs-CEM routing direction does not reverse
          |    at eta = 0.496 in tested OFAT states
          |
          +--> Adverse plant mismatch can defeat both allocators
```

The resulting claim is intentionally narrower than a generic robustness claim:

> **Fault-geometry-aware allocator selection improves emergency-landing reliability in the tested single-motor LoE setting, while controller selection and available plant authority remain distinct limitations.**

---

## Simulation platform

The final experiments use:

- Ubuntu 22.04
- ROS 2 Humble
- Gazebo Sim 7
- CrazySim / Crazyflie SITL
- Python 3.10
- `cflib`
- custom single-motor LoE fault injection
- firmware-level residual-control hooks
- bounded fault-aware WLS allocation

The work reported here is **simulation-only**.

The main experiment runner is:

```text
scripts/fault_triggered_landing_qp_event_allocator.py
```

Plant perturbations are managed by:

```text
scripts/plant_ofat.py
```

Seeded initial-condition generation is provided by:

```text
scripts/seeded_trial_params.py
```

Relevant Crazyflie firmware modifications are preserved under:

```text
patches/
```

---

## Repository structure

```text
.
├── configs/
│   └── controller and allocator configurations
│
├── patches/
│   └── Crazyflie firmware modifications
│
├── results/
│   └── final/
│       ├── project_experimental_synthesis/
│       ├── model_sensitivity/
│       ├── pinv_baseline/
│       ├── figures/
│       └── tables/
│
├── scripts/
│   ├── experiment runners
│   ├── analysis utilities
│   ├── sensitivity tools
│   └── paper-level synthesis builders
│
├── src/
│   └── project source modules
│
└── README.md
```

Large simulator logs, temporary files, local plant-state backups, and many raw/intermediate trial outputs are intentionally excluded from version control.

---

## Paper-facing result packages

Two generated synthesis layers provide the shortest path from frozen experiment outputs to the paper-level claims.

### Whole-project synthesis

```text
results/final/project_experimental_synthesis/
```

Key files:

```text
controller_complementarity.csv
validation_summary_by_motor.csv
overall_stage_summary.csv
model_sensitivity_ranking.csv
whole_project_claims.md
experimental_results_narrative.md
provenance.json
```

Regenerate with:

```bash
python scripts/build_project_experimental_synthesis.py
```

This command performs no new simulation. It rebuilds the paper-facing summary from the authoritative result files.

### Model-sensitivity synthesis

```text
results/final/model_sensitivity/ofat/synthesis/
```

Key files:

```text
model_sensitivity_master_table.csv
parameter_sensitivity_ranking.csv
failure_mechanism_summary.csv
routing_stability_compact.csv
model_sensitivity_claims.md
model_sensitivity_results.md
ofat_ed50_tornado.png
```

Regenerate with:

```bash
python scripts/build_model_sensitivity_synthesis.py
```

---

## Reproducibility

From the repository root, the curated paper-level summaries can be regenerated with:

```bash
conda activate crazysim310

python scripts/plant_ofat.py verify
python scripts/build_model_sensitivity_synthesis.py
python scripts/build_project_experimental_synthesis.py
```

Full simulator reproduction additionally requires a compatible CrazySim/Crazyflie SITL environment and the firmware modifications under `patches/`.

The primary runner is:

```text
scripts/fault_triggered_landing_qp_event_allocator.py
```

The frozen CEM configuration is:

```text
configs/allocator_weights/cem_tuned_boundary.json
```

---

## Result provenance

The release deliberately separates development, validation, and robustness evidence:

```text
112/120  development data used to select the routing policy
117/120  fresh-seed frozen-policy validation
115/120  separate randomized integrated supervisor evaluation
```

The repository also retains supporting and negative experiments, including the M4 modification that reduced integrated performance to 113/120.

The exact experimental state immediately before paper/repository cleanup is preserved by the Git tag:

```text
experimental-freeze
```

The release-development branch is:

```text
crazyflie-v1.0
```

---

## Limitations

This repository does **not** claim:

- physical Crazyflie hardware validation,
- online motor-fault detection or isolation,
- robustness to unknown failed-motor identity,
- simultaneous multiple-motor failures,
- simultaneous multi-parameter plant mismatch,
- universal robustness outside the tested simulator and distributions,
- formal closed-loop safety guarantees,
- formal attainable-wrench feasibility,
- globally optimal residual allocation,
- a formal CBF-QP implementation,
- reinforcement-learning-based fault-tolerant control.

The experimental question is intentionally narrower:

> **Given known partial LoE of one motor, can fault-dependent control allocation improve safe emergency first-contact landing, and how sensitive is that conclusion to plant-model mismatch?**

---

## Manuscript

The associated manuscript is in preparation.

**Working title**

*Fault-Geometry-Aware Control Allocation for Emergency Quadrotor Landing under Single-Motor Loss of Effectiveness*

Citation information will be added when a public manuscript record is available.

---

## License

A release license will be specified before the public paper repository is finalized.
