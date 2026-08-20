# Scripts

This directory contains the experiment runners, analysis utilities, validation tools, and paper-level synthesis builders used during development of the Crazyflie emergency-landing study.

The repository intentionally keeps the historical script paths stable. Many experiment records were generated with these exact paths, so the release does **not** reorganize the directory purely for aesthetics.

For the paper/release workflow, start with the five entry points below.

---

## Core paper-facing entry points

### `fault_triggered_landing_qp_event_allocator.py`

Primary experiment runner for the final allocation experiments.

Used for the controller families reported in the paper, including:

- bounded WLS/PINV allocation,
- QP-lite residual allocation,
- frozen CEM-tuned QP-lite.

The runner is the main simulation-side entry point for the final single-motor LoE experiments.

---

### `seeded_trial_params.py`

Defines the seeded initial-condition protocol used for repeated and paired experiments.

The final seeded protocol randomizes quantities such as:

- spawn x,
- spawn y,
- hover altitude,
- fault time.

Spawn yaw is generated/logged but is not applied by the current launcher, so it should not be described as an applied randomized initial condition.

---

### `plant_ofat.py`

Manages reversible one-factor-at-a-time plant perturbations for the model-sensitivity study.

The supported final sensitivity parameters are:

- mass,
- thrust coefficient,
- motor time constant,
- thrust-to-torque ratio,
- arm length.

Use its verification command before rebuilding or rerunning sensitivity analyses to confirm that the CrazySim plant is restored to the nominal state.

---

### `build_model_sensitivity_synthesis.py`

Builds the curated paper-facing model-sensitivity package from the frozen experiment outputs.

It does **not** launch new simulation.

Primary output directory:

```text
results/final/model_sensitivity/ofat/synthesis/
```

This package contains the final ED50 sensitivity ranking, failure-mechanism summary, routing-stability summary, and paper-facing sensitivity narrative.

---

### `build_project_experimental_synthesis.py`

Builds the whole-project paper-facing synthesis from the authoritative final result files.

It does **not** launch new simulation.

Primary output directory:

```text
results/final/project_experimental_synthesis/
```

This package contains the controller-complementarity table, frozen-policy validation summary, stage summary, model-sensitivity ranking, claims, narrative, and provenance metadata.

---

## Recommended release workflow

For readers interested in the final paper results, the normal order is:

```text
1. Verify the nominal plant
   scripts/plant_ofat.py

2. Inspect or reproduce seeded trial settings
   scripts/seeded_trial_params.py

3. Run final controller experiments when full simulation reproduction is required
   scripts/fault_triggered_landing_qp_event_allocator.py

4. Rebuild the model-sensitivity synthesis
   scripts/build_model_sensitivity_synthesis.py

5. Rebuild the whole-project synthesis
   scripts/build_project_experimental_synthesis.py
```

For paper-level result inspection only, steps 4 and 5 are sufficient when the authoritative experiment outputs are already present.

---

## Supporting scripts

The remaining scripts support earlier or narrower parts of the experimental program, including:

- experiment batch orchestration,
- controller-specific sweeps,
- boundary localization,
- CEM candidate studies,
- M2 selector and phase validation,
- M4 authority tuning,
- supervisor experiments,
- statistical fitting,
- auditing,
- plotting,
- summarization,
- intermediate validation.

These scripts are retained for scientific provenance and to preserve the paths used by historical experiment records.

They are **not all required to reproduce the headline paper results**.

---

## Why the directory is not reorganized

The release deliberately avoids moving the historical scripts into new subdirectories such as `run/`, `analysis/`, or `legacy/`.

That choice is intentional:

1. existing experiment commands and records may refer to current paths;
2. moving files would create unnecessary path churn;
3. the paper-facing workflow only needs a small number of clearly identified entry points;
4. Git history and the `experimental-freeze` tag already preserve development provenance.

The release therefore prioritizes **path stability and reproducibility** over cosmetic reorganization.

---

## Related documentation

See:

```text
../README.md
../docs/REPRODUCIBILITY.md
```

for the scientific results, software revisions, firmware patch information, safety definition, frozen routing policy, and final result provenance.
