# Randomized Oracle Motor-Conditioned Supervisor

- Run ID: `pilot8_v2`
- Trials: 8
- Fault effectiveness: `eta = 0.496`
- Motor order randomized before execution
- Failed-motor identity supplied by the experiment

| Motor | Policy | Safe | Rate | Wilson 95% CI | Mean vertical speed |
|---:|:---|---:|---:|---:|---:|
| M1 | cem_tuned_qplite | 2/2 | 100.0% | [34.2%, 100.0%] | 0.334212 m/s |
| M2 | pinv_bounded_wls | 2/2 | 100.0% | [34.2%, 100.0%] | 0.335485 m/s |
| M3 | cem_tuned_qplite | 2/2 | 100.0% | [34.2%, 100.0%] | 0.319889 m/s |
| M4 | manual_opp_m2_14000 | 2/2 | 100.0% | [34.2%, 100.0%] | 0.340536 m/s |

Overall: **8/8 (100.0%)**.

This validates integrated allocator selection using known failed-motor identity. It does not validate online fault diagnosis.
