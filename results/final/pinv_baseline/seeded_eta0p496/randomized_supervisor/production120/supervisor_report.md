# Randomized Oracle Motor-Conditioned Supervisor

- Run ID: `production120`
- Trials: 120
- Fault effectiveness: `eta = 0.496`
- Motor order randomized before execution
- Failed-motor identity supplied by the experiment

| Motor | Policy | Safe | Rate | Wilson 95% CI | Mean vertical speed |
|---:|:---|---:|---:|---:|---:|
| M1 | cem_tuned_qplite | 29/30 | 96.7% | [83.3%, 99.4%] | 0.331562 m/s |
| M2 | pinv_bounded_wls | 30/30 | 100.0% | [88.6%, 100.0%] | 0.329101 m/s |
| M3 | cem_tuned_qplite | 30/30 | 100.0% | [88.6%, 100.0%] | 0.322726 m/s |
| M4 | cem_tuned_qplite | 26/30 | 86.7% | [70.3%, 94.7%] | 0.340269 m/s |

Overall: **115/120 (95.8%)**.

This validates integrated allocator selection using known failed-motor identity. It does not validate online fault diagnosis.
