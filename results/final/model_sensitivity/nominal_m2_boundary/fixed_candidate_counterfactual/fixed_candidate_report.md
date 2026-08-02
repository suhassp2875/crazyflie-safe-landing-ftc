# Nominal M2 Fixed-Candidate Counterfactual

- Common eta: 0.499675
- Scheduled trials: 90
- Completed trials: 90
- Missing trials: 0

## Aggregate results

| Condition | Candidate | Present | Safe | Vertical fail | Angular fail |
|---|---|---:|---:|---:|---:|
| fixed_balanced1000 | balanced_1000_0_1000_12000 | 30/30 | 1 | 0 | 29 |
| fixed_opp_m4_11000 | opp_m4_11000 | 30/30 | 27 | 0 | 3 |
| fixed_opp_m4_10000 | opp_m4_10000 | 30/30 | 30 | 0 | 0 |

## Paired comparisons

| A | B | Paired n | A safe/B unsafe | A unsafe/B safe | McNemar p |
|---|---|---:|---:|---:|---:|
| fixed_balanced1000 | fixed_opp_m4_11000 | 30 | 0 | 26 | 2.9802322387695312e-08 |
| fixed_balanced1000 | fixed_opp_m4_10000 | 30 | 0 | 29 | 3.725290298461914e-09 |
| fixed_opp_m4_11000 | fixed_opp_m4_10000 | 30 | 0 | 3 | 0.25 |
