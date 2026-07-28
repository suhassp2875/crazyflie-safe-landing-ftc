# Randomized Oracle Motor-Conditioned Supervisor

- Run ID: `production120_v2`
- Trials: 120
- Fault effectiveness: `eta = 0.496`
- Motor order randomized before execution
- Failed-motor identity supplied by the experiment

| Motor | Policy | Safe | Rate | Wilson 95% CI | Mean vertical speed |
|---:|:---|---:|---:|---:|---:|
| M1 | cem_tuned_qplite | 29/30 | 96.7% | [83.3%, 99.4%] | 0.333612 m/s |
| M2 | pinv_bounded_wls | 30/30 | 100.0% | [88.6%, 100.0%] | 0.329766 m/s |
| M3 | cem_tuned_qplite | 30/30 | 100.0% | [88.6%, 100.0%] | 0.327198 m/s |
| M4 | manual_opp_m2_14000 | 24/30 | 80.0% | [62.7%, 90.5%] | 0.351681 m/s |

Overall: **113/120 (94.2%)**.

This validates integrated allocator selection using known failed-motor identity. It does not validate online fault diagnosis.
