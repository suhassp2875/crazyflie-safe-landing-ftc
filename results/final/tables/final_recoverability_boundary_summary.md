# Final Recoverability Boundary: Equal Healthy-Motor Residual FTC

Controller: max-brake landing with equal residual boost applied to all healthy motors.

Boost: 10000 PWM.

Touchdown safety limit: first-contact vertical speed <= 0.35 m/s.



| Motor | Eta | Mean Vz [m/s] | Std Vz | Safe Count / 3 | Classification |
|---:|---:|---:|---:|---:|---|
| 1 | 0.496 | 0.3556 | 0.0040 | 0/3 | Unsafe |
| 2 | 0.496 | 0.3932 | 0.0074 | 0/3 | Unsafe |
| 3 | 0.496 | 0.3610 | 0.0071 | 0/3 | Unsafe |
| 4 | 0.496 | 0.3761 | 0.0032 | 0/3 | Unsafe |
| 1 | 0.497 | 0.3215 | 0.0028 | 3/3 | Robust safe |
| 2 | 0.497 | 0.3587 | 0.0047 | 0/3 | Unsafe |
| 3 | 0.497 | 0.3195 | 0.0069 | 3/3 | Robust safe |
| 4 | 0.497 | 0.3337 | 0.0112 | 3/3 | Robust safe |
| 1 | 0.498 | 0.2818 | 0.0087 | 3/3 | Robust safe |
| 2 | 0.498 | 0.3158 | 0.0104 | 3/3 | Robust safe |
| 3 | 0.498 | 0.2844 | 0.0064 | 3/3 | Robust safe |
| 4 | 0.498 | 0.2984 | 0.0041 | 3/3 | Robust safe |


Conservative all-motor conclusion: eta=0.498 is robustly safe for all motors, eta=0.496 is unsafe for all motors, and eta=0.497 is mixed because motor 2 remains unsafe.
