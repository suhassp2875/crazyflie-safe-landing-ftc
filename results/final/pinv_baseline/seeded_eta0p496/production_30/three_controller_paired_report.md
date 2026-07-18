# Exact Matched Three-Controller Comparison

## Design

- Fault effectiveness: `eta = 0.496`
- Four failed-motor geometries
- 30 identical seeds per motor and configuration
- Total: 360 controller-trial observations
- PINV: bounded weighted least-squares allocator
- QP-lite: baseline event allocator
- CEM-tuned: QP-lite runtime allocator using weights tuned offline by cross-entropy method

## Motor-level outcomes

| Motor | PINV | QP-lite | CEM-tuned | Cochran Q p |
|---:|---:|---:|---:|---:|
| M1 | 26/30 | 4/30 | 30/30 | 1.50752e-10 |
| M2 | 30/30 | 6/30 | 3/30 | 3.08284e-10 |
| M3 | 19/30 | 28/30 | 29/30 | 0.00150344 |
| M4 | 0/30 | 5/30 | 23/30 | 5.13618e-09 |

Pairwise safety comparisons use exact two-sided McNemar tests. `mcnemar_holm12_p` adjusts across all 12 motor-comparison tests.

Touchdown-speed differences are paired as `first - second`; negative values favor the first configuration.
