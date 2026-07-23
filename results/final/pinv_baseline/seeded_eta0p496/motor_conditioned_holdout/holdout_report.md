# Motor-Conditioned Allocator Fresh-Seed Holdout

## Fixed policy

- M1: CEM-tuned QP-lite
- M2: bounded weighted least squares/PINV
- M3: CEM-tuned QP-lite
- M4: CEM-tuned QP-lite

The policy was selected using the previous matched development seed block and evaluated here on a fresh 30-seed block per motor.

## Holdout outcomes

| Motor | Configuration | Safe | Rate | Wilson 95% CI | Mean vertical speed |
|---:|:---|---:|---:|---:|---:|
| M1 | cem_tuned | 30/30 | 100.0% | [88.6%, 100.0%] | 0.328511 m/s |
| M2 | pinv | 30/30 | 100.0% | [88.6%, 100.0%] | 0.329233 m/s |
| M3 | cem_tuned | 30/30 | 100.0% | [88.6%, 100.0%] | 0.325385 m/s |
| M4 | cem_tuned | 27/30 | 90.0% | [74.4%, 96.5%] | 0.340405 m/s |

Overall holdout performance: **117/120 (97.5%)**.

Overall Wilson 95% interval: **[92.9%, 99.1%]**.

Development selected-policy result: **112/120 (93.3%)**.

This is a fresh-seed validation under the same simulator and initial-condition distribution. It is not evidence of transfer to hardware or to a different fault distribution.
