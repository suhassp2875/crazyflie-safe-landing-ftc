# M4 Residual-Authority Fresh-Seed Holdout

- Baseline: `opp_m2_12000`
- Development-selected candidate: `opp_m2_14000`
- Thirty identical fresh seeds per candidate
- Fault effectiveness: `eta = 0.496`

The 14000 candidate was selected using a separate development seed block. This experiment evaluates it against the existing 12000 candidate on fresh paired seeds.

| Strength | Safe | Rate | Mean vertical speed | Q90 | Q95 | Maximum |
|---:|---:|---:|---:|---:|---:|---:|
| 12000 | 23/30 | 76.7% | 0.339638 | 0.354389 | 0.355598 | 0.393911 |
| 14000 | 24/30 | 80.0% | 0.351681 | 0.353749 | 0.364278 | 0.559673 |

Discordant pairs: baseline-only `5`, tuned-only `6`.

Exact McNemar p-value: `1.00000000`.

Paired touchdown-speed difference is computed as `14000 - 12000`; negative values favor 14000.

Mean paired difference: `+0.012042 m/s`.

Bootstrap 95% interval: `[-0.000180, +0.029781] m/s`.
