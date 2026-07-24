# M4 Residual-Authority Fresh-Seed Holdout

- Baseline: `opp_m2_12000`
- Development-selected candidate: `opp_m2_14000`
- Thirty identical fresh seeds per candidate
- Fault effectiveness: `eta = 0.496`

The 14000 candidate was selected using a separate development seed block. This experiment evaluates it against the existing 12000 candidate on fresh paired seeds.

| Strength | Safe | Rate | Mean vertical speed | Q90 | Q95 | Maximum |
|---:|---:|---:|---:|---:|---:|---:|
| 12000 | 26/30 | 86.7% | 0.340045 | 0.352416 | 0.358404 | 0.359014 |
| 14000 | 28/30 | 93.3% | 0.340933 | 0.348749 | 0.354610 | 0.356223 |

Discordant pairs: baseline-only `2`, tuned-only `4`.

Exact McNemar p-value: `0.68750000`.

Paired touchdown-speed difference is computed as `14000 - 12000`; negative values favor 14000.

Mean paired difference: `+0.000888 m/s`.

Bootstrap 95% interval: `[-0.003559, +0.006307] m/s`.
