# Randomized Supervisor Failure Diagnostics

## Summary

- Total production trials: 120
- Safe trials: 115
- Unsafe trials: 5
- All unsafe trials violated only the vertical-speed threshold.

## Unsafe first-contact outcomes

| Sequence | Motor | Seed | Candidate | Actual vertical speed | Excess over limit | Predicted vertical speed |
|---:|---:|---:|:---|---:|---:|---:|
| 18 | M4 | 45280005 | opp_m2_12000 | 0.371158 | +0.021158 | 0.347600 |
| 30 | M1 | 15280008 | opp_m3_12000 | 0.355181 | +0.005181 | 0.347600 |
| 71 | M4 | 45280021 | opp_m2_12000 | 0.356131 | +0.006131 | 0.347600 |
| 93 | M4 | 45280024 | opp_m2_12000 | 0.353684 | +0.003684 | 0.347600 |
| 109 | M4 | 45280028 | opp_m2_12000 | 0.398824 | +0.048824 | 0.347600 |

These diagnostics describe failures under the current seeded simulator distribution. They do not by themselves establish the causal source of the upper-tail vertical-speed errors.
