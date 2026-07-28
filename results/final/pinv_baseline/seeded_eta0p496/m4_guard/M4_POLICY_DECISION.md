# M4 Policy Decision at eta = 0.496

## Decision

Retain the original CEM-tuned QP-lite policy for M4, which selected
`opp_m2_12000` in the integrated supervisor-v1 experiment.

The fixed `opp_m2_14000` policy and the guarded
`14000 -> 12000` policies are rejected as canonical replacements.

## Exact-seed five-policy comparison

All five policies were evaluated on the same 30 seeds,
`45780001-45780030`.

| Policy | Safe | Mean vertical speed | Maximum vertical speed |
|---|---:|---:|---:|
| fixed `opp_m2_12000` | 28/30 | 0.338164 m/s | 0.359622 m/s |
| fixed `opp_m2_14000` | 26/30 | 0.338434 m/s | 0.383382 m/s |
| guard 0.16 m/s | 24/30 | 0.343284 m/s | 0.368174 m/s |
| guard 0.18 m/s | 23/30 | 0.345242 m/s | 0.394771 m/s |
| guard 0.20 m/s | 23/30 | 0.343155 m/s | 0.371620 m/s |

## Paired outcomes versus fixed 12000

| Comparison | Both safe | Fixed-only safe | Comparison-only safe | Both unsafe |
|---|---:|---:|---:|---:|
| fixed 14000 | 24 | 4 | 2 | 0 |
| guard 0.16 | 23 | 5 | 1 | 1 |
| guard 0.18 | 21 | 7 | 2 | 0 |
| guard 0.20 | 22 | 6 | 1 | 1 |

None of the paired binary comparisons was statistically significant
at this sample size. However, the safety counts, paired directions,
mean touchdown speeds, and upper-tail outcomes consistently fail to
support replacing fixed 12000.

## Mechanistic interpretation

The guarded policies switched in 30/30 trials. They therefore acted
as near-immediate transient policies rather than selective runaway
detectors. Although the guard recovered one previously catastrophic
seed, that single-seed result did not generalize to the fresh paired
30-seed experiment.

## Integrated supervisor conclusion

The primary integrated result remains supervisor v1:

- M1: CEM-tuned QP-lite
- M2: bounded weighted least-squares/PINV
- M3: CEM-tuned QP-lite
- M4: CEM-tuned QP-lite, selecting `opp_m2_12000`

Supervisor v1 achieved 115/120 safe first-contact touchdowns at
eta = 0.496.

Supervisor v2, which forced `opp_m2_14000` for M4, achieved 113/120
and is retained only as a negative replication.

The guard code remains available as an inactive experimental feature.
It is not part of the final supervisor policy.
