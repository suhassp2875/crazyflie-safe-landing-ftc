# Fault-Geometry-Aware Control Allocation for Emergency Quadrotor Landing under Single-Motor Loss of Effectiveness

This repository contains the **paper-facing code, controller configuration, firmware patch, and final experimental evidence** for fault-tolerant emergency landing of a Crazyflie-class quadrotor under partial single-motor loss of effectiveness (LoE).

> **Main finding:** no single tested control-allocation strategy is best across all single-motor fault geometries.

A bounded weighted-least-squares allocator is strongest for the M2 failure geometry, while a CEM-tuned residual allocator is stronger for M1, M3, and M4. This motivates a fault-geometry-aware supervisor that routes to the appropriate allocator using the known failed-motor identity.

## Headline results

| Evaluation | Safe first-contact touchdowns |
|---|---:|
| Development-selected routing | 112/120 (93.3%) |
| **Fresh-seed frozen-policy holdout** | **117/120 (97.5%)** |
| **Randomized integrated supervisor** | **115/120 (95.8%)** |

The 112/120 result is **in-sample** because the same development block is used to select the routing map. The 117/120 result is the primary fresh-seed validation after the policy was frozen.

A subsequent plant-model sensitivity study shows that **mass and thrust coefficient dominate the M2/PINV safety-boundary shift**, and that model mismatch can change not only where the boundary lies but also **which safety constraint becomes active**.

> **Scope assumption:** failed-motor identity is supplied to the supervisor. This work studies fault-aware allocation and reconfiguration after the failed motor is known; it does not implement or validate online fault detection or isolation.

---

## Problem formulation

For faulted motor \(i\), remaining effectiveness is modeled as

\[
u_i^{\mathrm{effective}}=\eta u_i,
\]

where:

- \(\eta=1\) denotes a healthy motor,
- \(0<\eta<1\) denotes partial LoE,
- smaller \(\eta\) denotes a more severe fault.

The main controller-complementarity and supervisor experiments are performed at:

\[
\eta=0.496.
\]

The study considers one failed motor at a time: M1, M2, M3, or M4.

For this single-motor LoE setting, the failed-motor index identifies the corresponding actuator/control-authority geometry. The implemented supervisor therefore instantiates **fault-geometry awareness through discrete failed-motor identity**.

---

## First-contact safety definition

The official touchdown sample is the first post-fault row satisfying:

\[
z\le0.03\ \mathrm{m}.
\]

A touchdown is safe only if **all** criteria pass:

| Quantity | Limit |
|---|---:|
| Vertical speed | \(\le0.35\) m/s |
| Horizontal speed | \(\le0.25\) m/s |
| Roll/pitch magnitude | \(\le12^\circ\) |
| Angular rate | \(\le1.5\) rad/s |
| Horizontal drift | \(\le0.75\) m |
| Ground contact | Required |

Safety-criterion violations can overlap. Counts of violated criteria are therefore not mutually exclusive failure classes.

---

## Allocation methods

### Bounded WLS/PINV

The model-informed allocator performs bounded weighted least-squares allocation in the Crazyflie PWM-command domain.

Final weighting:

\[
w_T=w_R=w_P=1,\qquad w_Y=0.2
\]

with regularization:

\[
\lambda=10^{-6}.
\]

The allocator compensates for known motor effectiveness while respecting command bounds. It is a **PWM-domain command-effectiveness allocator**, not a complete physical force/wrench allocator.

### QP-lite

QP-lite evaluates a fixed empirical library of bounded motor-residual candidates using a quadratic state-dependent score.

It is **not a formal continuous CBF-QP**, and no formal CBF-QP safety guarantee is claimed.

### CEM-tuned QP-lite

The Cross-Entropy Method (CEM) is used **offline** to tune the QP-lite scoring weights.

At runtime:

- CEM is not executed,
- no reinforcement-learning policy is used,
- the candidate library is fixed,
- QP-lite selects candidates using frozen weights.

Frozen configuration:

```text
configs/allocator_weights/cem_tuned_boundary.json
```

---

## Result 1 — allocator complementarity

Matched 30-seed development results at \(\eta=0.496\):

| Failed motor | PINV | QP-lite | CEM-tuned | Selected |
|---|---:|---:|---:|---|
| M1 | 26/30 | 4/30 | **30/30** | CEM |
| M2 | **30/30** | 6/30 | 3/30 | PINV |
| M3 | 19/30 | 28/30 | **29/30** | CEM |
| M4 | 0/30 | 5/30 | **23/30** | CEM |

Frozen routing:

```text
M1 -> CEM
M2 -> PINV
M3 -> CEM
M4 -> CEM
```

The central observation is:

> **Allocator suitability depends on failed-motor geometry.**

M2 strongly favors PINV. M3 is the closest development comparison, with CEM at 29/30 and ordinary QP-lite at 28/30.

Paper-facing table:

```text
results/final/project_experimental_synthesis/controller_complementarity.csv
```

---

## Result 2 — frozen-policy fresh-seed validation

After the routing policy was frozen:

| Failed motor | Controller | Safe touchdowns |
|---|---|---:|
| M1 | CEM | 30/30 |
| M2 | PINV | 30/30 |
| M3 | CEM | 30/30 |
| M4 | CEM | 27/30 |
| **Overall** | — | **117/120** |

\[
\boxed{117/120=97.5\%}
\]

Wilson 95% confidence interval:

\[
[92.9\%,99.1\%].
\]

This is a fresh-seed validation under the same simulator and initial-condition distribution.

Authoritative results:

```text
results/final/pinv_baseline/seeded_eta0p496/motor_conditioned_holdout/
```

---

## Result 3 — integrated randomized supervisor

The frozen policy was evaluated as an integrated supervisor with randomized motor-case execution order:

| Failed motor | Controller | Safe touchdowns |
|---|---|---:|
| M1 | CEM | 29/30 |
| M2 | PINV | 30/30 |
| M3 | CEM | 30/30 |
| M4 | CEM | 26/30 |
| **Overall** | — | **115/120** |

\[
\boxed{115/120=95.8\%}.
\]

The failed-motor identity is supplied by the experiment. This validates allocation selection and execution under known fault identity, not online diagnosis.

Retained supervisor:

```text
results/final/pinv_baseline/seeded_eta0p496/randomized_supervisor/production120/
```

A later M4 modification achieved **113/120**, so the original supervisor was retained:

```text
results/final/pinv_baseline/seeded_eta0p496/randomized_supervisor/production120_v2/
```

---

## Result 4 — model mismatch changes the failure mode

The final sensitivity study perturbs five plant parameters independently by \(\pm10\%\):

- mass,
- thrust coefficient,
- motor time constant,
- thrust-to-torque ratio,
- arm length.

For the **mass -10%** condition, the fine-boundary sweep records:

| Violated criterion | Count |
|---|---:|
| Vertical speed | 0 |
| Horizontal speed | 72 |
| Tilt | 46 |
| Angular rate | **150** |
| Drift | 0 |

Angular rate is therefore the most frequent violated safety criterion under this perturbation.

The **thrust-coefficient +10%** condition also becomes angular-rate limited. Many other tested conditions remain primarily vertical-speed limited.

> **Model mismatch can change the active safety limitation, not merely translate a fixed vertical-impact-speed boundary.**

Violation counts overlap.

---

## Result 5 — nominal M2/PINV boundary

The nominal M2/PINV safety boundary is estimated using Firth bias-reduced logistic regression:

\[
\boxed{\eta_{50}\approx0.4956}
\]

with within-model paired-seed bootstrap 95% interval approximately:

\[
\boxed{[0.4955,0.4956]}.
\]

Because \(\eta\) denotes **remaining motor effectiveness**:

> **Lower ED50 means greater LoE tolerance.**

The narrow interval is a within-model repeated-trial result. It does not represent physical-model uncertainty.

Authoritative result family:

```text
results/final/model_sensitivity/nominal_m2_boundary/pinv_fine_boundary/
```

---

## Result 6 — plant-model sensitivity

Maximum absolute ED50 shifts under the \(\pm10\%\) OFAT perturbations are:

| Rank | Parameter | Max \(|\Delta\mathrm{ED50}|\) |
|---:|---|---:|
| 1 | **Thrust coefficient** | **0.05495** |
| 2 | **Mass** | **0.04974** |
| 3 | Motor time constant | 0.000404 |
| 4 | Arm length | 0.000262 |
| 5 | Thrust-to-torque ratio | 0.000262 |

Representative shifts:

| Perturbation | \(\Delta\mathrm{ED50}\) |
|---|---:|
| Mass -10% | -0.04714 |
| Mass +10% | +0.04974 |
| Thrust coefficient -10% | +0.05495 |
| Thrust coefficient +10% | -0.04538 |

The practical interpretation is:

> **The transition is sharply localizable within a fixed plant model, while plausible plant mismatch moves the boundary by roughly two orders of magnitude more. Practical boundary uncertainty is therefore dominated by model uncertainty rather than repeated-trial uncertainty in the nominal simulator.**

Final sensitivity outputs:

```text
results/final/model_sensitivity/ofat/synthesis/
```

Statistical inputs used by the synthesis:

```text
results/final/model_sensitivity/ofat/sensitivity_analysis/
```

---

## Result 7 — M2 routing stability under plant mismatch

At fixed:

\[
\eta=0.496,
\]

PINV and frozen CEM are compared under the nominal plant and all ten OFAT perturbations.

Across all 11 tested plant states:

| Outcome | States |
|---|---:|
| PINV higher safe count | **9/11** |
| Tie | **2/11** |
| CEM higher safe count | **0/11** |

Across the ten perturbed states only:

| Outcome | States |
|---|---:|
| PINV higher safe count | **8/10** |
| Tie | **2/10** |
| CEM higher safe count | **0/10** |

The two adverse ties are:

| Perturbation | PINV | CEM |
|---|---:|---:|
| Mass +10% | 0/30 | 0/30 |
| Thrust coefficient -10% | 0/30 | 0/30 |

No tested perturbation reverses the M2 routing direction in favor of CEM at the tested operating point.

However:

> **Stable controller ordering does not imply safety robustness.**

The two 0/30 ties are consistent with an available-control-authority limitation rather than merely a controller-selection limitation. No formal attainable-wrench-set proof is claimed.

Authoritative results:

```text
results/final/model_sensitivity/ofat/m2_routing_stability_eta0p496/
```

---

## Repository structure

```text
.
├── configs/
│   └── final controller configuration
│
├── docs/
│   └── REPRODUCIBILITY.md
│
├── patches/
│   └── Crazyflie firmware patch
│
├── results/
│   ├── README.md
│   └── final/
│       ├── cem_tuning/
│       ├── pinv_baseline/
│       ├── model_sensitivity/
│       └── project_experimental_synthesis/
│
├── scripts/
│   ├── README.md
│   └── paper/reproduction scripts
│
├── src/
│   └── project source modules
│
└── README.md
```

The paper-facing release intentionally omits obsolete development figures, old boundary studies, transient console logs, pre-fix data, and other exploratory artifacts. Those remain recoverable through Git history and the `experimental-freeze` tag.

---

## Core scripts

The release retains 33 scripts supporting the final experimental and analysis pipeline.

Primary entry points:

```text
scripts/fault_triggered_landing_qp_event_allocator.py
scripts/fault_triggered_landing_motor_supervisor.py
scripts/seeded_trial_params.py
scripts/plant_ofat.py
scripts/cem_tune_allocator_weights.py
scripts/build_model_sensitivity_synthesis.py
scripts/build_project_experimental_synthesis.py
```

See:

```text
scripts/README.md
```

for the curated script map.

---

## Simulation platform

Final experiments use:

- Ubuntu 22.04
- ROS 2 Humble
- Gazebo Sim 7.9.0
- CrazySim / Crazyflie SITL
- Python 3.10
- `cflib`
- custom single-motor LoE injection
- firmware-level residual hooks
- bounded fault-aware WLS allocation

The study is **simulation-only**.

### Pinned CrazySim revision

```text
3ec8b55da4bff887da542a9f314da825460e65be
```

### Pinned Crazyflie firmware base

```text
aa6571dc465f06f7d1f9aaf7b0b861fbcd1b3d67
```

### Firmware patch

```text
patches/fault_aware_bounded_allocator.patch
```

SHA-256:

```text
cab514533873039c75c0207cd7557f802047eddc5c6cee974ff168b9666ffe45
```

The patch was verified to match the active experimental firmware exactly and to apply cleanly to the pinned firmware base.

Full reproduction details are in:

```text
docs/REPRODUCIBILITY.md
```

---

## Paper-facing synthesis

Rebuild the final sensitivity synthesis:

```bash
python scripts/build_model_sensitivity_synthesis.py
```

Rebuild the final whole-project synthesis:

```bash
python scripts/build_project_experimental_synthesis.py
```

These builders do not launch new simulation. They derive the paper-facing outputs from the retained authoritative result files.

---

## Provenance

The release deliberately distinguishes:

```text
112/120  development-selected routing
117/120  fresh-seed frozen-policy validation
115/120  randomized integrated supervisor
113/120  negative supervisor-v2 follow-up
```

The experimental state before release cleanup is preserved by:

```text
experimental-freeze
```

Development history remains recoverable even though obsolete artifacts are removed from the paper-facing branch.

---

## Limitations

This repository does **not** claim:

- physical Crazyflie hardware validation,
- online motor-fault detection or isolation,
- robustness to unknown failed-motor identity,
- simultaneous multiple-motor failures,
- simultaneous multi-parameter model mismatch,
- universal robustness outside the tested simulator/domain,
- formal closed-loop safety guarantees,
- formal attainable-wrench feasibility,
- globally optimal residual allocation,
- formal CBF-QP control,
- reinforcement-learning-based fault tolerance.

The paper-level question is deliberately narrower:

> **Given known partial LoE of one motor, can fault-dependent control allocation improve safe emergency first-contact landing, and how sensitive is that conclusion to plant-model mismatch?**

---

## Manuscript

Working title:

> **Fault-Geometry-Aware Control Allocation for Emergency Quadrotor Landing under Single-Motor Loss of Effectiveness**

The manuscript is in preparation. Citation information will be added when a public manuscript record is available.

---

## License

A release license will be specified before the repository is made public.
