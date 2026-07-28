# M4 Residual-Authority Fresh-Seed Holdout

- Baseline: `opp_m2_12000`
- Development-selected candidate: `opp_m2_14000`
- Thirty identical fresh seeds per candidate
- Fault effectiveness: `eta = 0.496`

The 14000 candidate was selected using a separate development seed block. This experiment evaluates it against the existing 12000 candidate on fresh paired seeds.

| Strength | Safe | Rate | Mean vertical speed | Q90 | Q95 | Maximum |
|---:|---:|---:|---:|---:|---:|---:|
| 12000 | 28/30 | 93.3% | 0.338164 | 0.348733 | 0.352200 | 0.359622 |
| 14000 | 26/30 | 86.7% | 0.338434 | 0.350120 | 0.359485 | 0.383382 |

Discordant pairs: baseline-only `4`, tuned-only `2`.

Exact McNemar p-value: `0.68750000`.

Paired touchdown-speed difference is computed as `14000 - 12000`; negative values favor 14000.

Mean paired difference: `+0.000271 m/s`.

Bootstrap 95% interval: `[-0.010081, +0.010749] m/s`.
