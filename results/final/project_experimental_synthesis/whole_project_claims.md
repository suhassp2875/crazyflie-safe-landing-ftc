# Defensible Whole-Project Experimental Claims

## Controller complementarity

At eta=0.496, no single tested allocator dominated across all four single-motor LoE geometries.

- M1 development: PINV 26/30, QP-lite 4/30, CEM-tuned 30/30.
- M2 development: PINV 30/30, QP-lite 6/30, CEM-tuned 3/30.
- M3 development: PINV 19/30, QP-lite 28/30, CEM-tuned 29/30.
- M4 development: PINV 0/30, QP-lite 5/30, CEM-tuned 23/30.

The resulting frozen motor-conditioned routing policy was M1->CEM, M2->PINV, M3->CEM, M4->CEM.

## Frozen-policy validation

- Development selected-policy total: 112/120 (93.3%).
- Fresh-seed holdout: 117/120 (97.5%), Wilson 95% CI [92.9%, 99.1%].
- Randomized-order supervisor v1: 115/120 (95.8%), Wilson 95% CI [90.6%, 98.2%].

The development result is policy-selection evidence and must not be presented as an independent validation result.

## Model sensitivity

For the M2 PINV branch, thrust coefficient and mass produced the largest ED50 shifts under the tested +/-10% OFAT perturbations.
- Thrust coefficient: max |Delta ED50| = 0.054946017.
- Mass: max |Delta ED50| = 0.049737662.
Motor time constant, arm length, and thrust-to-torque ratio produced much smaller ED50 shifts in the tested range.

At eta=0.496, PINV had a higher safe-touchdown count than frozen CEM in 9/11 nominal-plus-OFAT plant states, tied in 2/11, and CEM had the higher count in 0/11.

## Claim boundaries

- All reported results are simulation results from the tested CrazySim/Gazebo setup.
- Failed-motor identity is supplied by the experiment; online fault diagnosis is not validated.
- The fresh holdout uses new seeds but the same simulator and initial-condition distribution.
- The model-sensitivity experiment varies one plant parameter at a time; simultaneous multi-parameter mismatch is not tested.
- The M2 routing-stability comparison is made at eta=0.496 and is not a complete perturbed boundary comparison between controllers.
- These experiments do not establish transfer to physical Crazyflie hardware.
