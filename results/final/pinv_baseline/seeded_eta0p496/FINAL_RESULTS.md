# Final Results at eta = 0.496

## Retained integrated policy

The final retained supervisor is
`oracle_motor_conditioned_v1`:

- M1: CEM-tuned QP-lite
- M2: bounded weighted least-squares/PINV
- M3: CEM-tuned QP-lite
- M4: CEM-tuned QP-lite, selecting `opp_m2_12000`

The randomized 120-trial production result was:

- Safe first-contact touchdowns: **115/120**
- Safety rate: **95.8%**
- Wilson 95% interval:
  **[90.6%, 98.2%]**
- All unsafe outcomes violated only the vertical-speed criterion.

## Supervisor v2 negative replication

Supervisor v2 forced `opp_m2_14000` for M4.

- Safe first-contact touchdowns: **113/120**
- Safety rate: **94.2%**
- Wilson 95% interval:
  **[88.4%, 97.1%]**

Supervisor v2 did not improve the integrated result and is not retained.

## M4 policy conclusion

The exact-seed five-policy comparison showed:

- Fixed `opp_m2_12000`: **28/30**
- Fixed `opp_m2_14000`: **26/30**
- Guard 0.16 m/s: **24/30**
- Guard 0.18 m/s: **23/30**
- Guard 0.20 m/s: **23/30**

The guarded policies switched in every trial and underperformed
fixed `opp_m2_12000`. They are retained only as negative
experimental results.

## Regression verification

After restoring supervisor v1, one fresh routing trial per motor
was executed:

- M1 routed to CEM-tuned QP-lite
- M2 routed to bounded WLS/PINV
- M3 routed to CEM-tuned QP-lite
- M4 routed to CEM-tuned QP-lite
- M4 selected `opp_m2_12000` with residual `(0, 12000, 0, 0)`

All four regression trials reached safe first contact. This verifies
routing and integration; it is not an additional performance estimate.

## Scope and limitations

These findings apply to the current CrazySim/Gazebo setup, the
seeded simulator distribution, known failed-motor identity, and
fault effectiveness `eta = 0.496`.

The experiments do not validate:

- online fault diagnosis;
- unknown or time-varying fault effectiveness;
- hardware flight;
- transfer to different simulators or vehicle models;
- a formal safety guarantee.

The guard implementation remains available as an inactive
experimental feature and is not part of the retained supervisor.
