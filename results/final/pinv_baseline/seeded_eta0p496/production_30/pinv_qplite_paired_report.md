# Paired PINV versus QP-lite Comparison

## Design

- Fault effectiveness: `eta = 0.496`
- Pairing key: identical motor and `trial_seed`
- Paired motors: M1, M2, M3, and M4
- Pairs per motor: 30
- Total paired trials: 120
- CEM excluded from paired inference because pairing metadata is incomplete

## Results

| Motor | PINV safe | QP-lite safe | PINV only | QP-lite only | McNemar p | Mean speed difference |
|---:|---:|---:|---:|---:|---:|---:|
| M1 | 26/30 | 4/30 | 22 | 0 | 4.76837e-07 | -0.020015 m/s |
| M2 | 30/30 | 6/30 | 24 | 0 | 1.19209e-07 | -0.040318 m/s |
| M3 | 19/30 | 28/30 | 2 | 11 | 0.0224609 | -0.034486 m/s |
| M4 | 0/30 | 5/30 | 0 | 5 | 0.0625 | +0.014731 m/s |

A negative touchdown-speed difference favors PINV; a positive difference favors QP-lite.

McNemar tests use only discordant paired safety outcomes. Each motor is treated as a separate primary comparison.

The comparison is paired through the identical seeded runner inputs. Spatial spawn metadata should not be interpreted as verified physical simulator perturbation unless independently confirmed by the launcher.
