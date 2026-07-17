# Bounded Weighted-Least-Squares Deterministic Landing Test

## Protocol

- Controller: firmware bounded weighted least-squares allocator
- Fault effectiveness: `eta = 0.496`
- Weights: `[1.0, 1.0, 1.0, 0.2]`
- Regularization: `1e-6`
- Landing protocol: `adaptive_ramp_v1`
- First contact: first post-fault row with `z <= 0.03 m`
- Vertical-speed safety limit: `0.35 m/s`

## Results

| Motor | Contact speed (m/s) | Margin (m/s) | Result |
|---:|---:|---:|:---|
| M1 | 0.343520 | +0.006480 | Safe |
| M2 | 0.331394 | +0.018606 | Safe |
| M3 | 0.359227 | -0.009227 | Unsafe |
| M4 | 0.378017 | -0.028017 | Unsafe |

Deterministic safe count: **2/4**.

All four trials reached first contact. The only failed safety criterion for M3 and M4 was vertical touchdown speed.

These four nominal trials establish deterministic classification only. They do not estimate success probabilities.
