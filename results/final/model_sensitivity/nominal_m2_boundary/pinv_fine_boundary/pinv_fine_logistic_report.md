# Nominal M2 PINV Logistic Boundary

## Dataset audit

- Trials: 210
- Paired seeds: 30
- Eta conditions: 7
- Valid pre-fault states: 210/210
- First contacts found: 210/210
- Safe touchdowns: 83/210
- Unsafe touchdowns: 127
- Unsafe failure mechanism: vertical speed only

## Logistic model

$\operatorname{logit}(p_{\mathrm{safe}}) = \beta_0 + \beta_1[(\eta-0.49550)\times10^4]$

- Intercept: -0.998956420
- Slope per eta increase of 0.0001: 1.334686455
- Odds ratio per eta increase of 0.0001: 3.798805

## Fault-tolerance thresholds

| Threshold | Estimate | Paired-seed bootstrap 95% CI |
|---|---:|---:|
| ED10 | 0.495410221 | [0.495376377, 0.495453364] |
| ED50 | 0.495574846 | [0.495537009, 0.495613964] |
| ED90 | 0.495739471 | [0.495675780, 0.495794809] |

Lower eta represents a more severe loss-of-effectiveness fault. Therefore, a lower ED50 indicates stronger fault tolerance.

## Diagnostics

- Deviance: 7.775397 on 5 df
- McFadden pseudo-R²: 0.500959
- Brier score: 0.109562
- Empirical safe-rate monotonicity violations: 0
- Valid paired-seed bootstrap replicates: 5000/5000
