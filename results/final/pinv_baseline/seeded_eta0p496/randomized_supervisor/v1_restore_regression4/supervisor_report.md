# Randomized Oracle Motor-Conditioned Supervisor

- Run ID: `v1_restore_regression4`
- Trials: 4
- Fault effectiveness: `eta = 0.496`
- Motor order randomized before execution
- Failed-motor identity supplied by the experiment

| Motor | Policy | Safe | Rate | Wilson 95% CI | Mean vertical speed |
|---:|:---|---:|---:|---:|---:|
| M1 | cem_tuned_qplite | 1/1 | 100.0% | [20.7%, 100.0%] | 0.330321 m/s |
| M2 | pinv_bounded_wls | 1/1 | 100.0% | [20.7%, 100.0%] | 0.322216 m/s |
| M3 | cem_tuned_qplite | 1/1 | 100.0% | [20.7%, 100.0%] | 0.319378 m/s |
| M4 | cem_tuned_qplite | 1/1 | 100.0% | [20.7%, 100.0%] | 0.313563 m/s |

Overall: **4/4 (100.0%)**.

This validates integrated allocator selection using known failed-motor identity. It does not validate online fault diagnosis.
