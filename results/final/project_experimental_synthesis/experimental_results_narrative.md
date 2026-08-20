# Whole-Project Experimental Synthesis

## 1. Controller complementarity

The central development result is that allocator performance depends strongly on failed-motor geometry. At eta=0.496, PINV is strongest for M2, whereas the CEM-tuned residual allocator is strongest for M1, M3, and M4.

This motivates motor-conditioned controller selection rather than use of a single global allocator.

## 2. Frozen motor-conditioned policy

The development block selects M1->CEM, M2->PINV, M3->CEM, and M4->CEM, yielding 112/120 safe first-contact touchdowns on the development seeds. Because those same results were used to choose the routing policy, this 112/120 figure is in-sample selection evidence.

## 3. Fresh validation

With the routing frozen and evaluated on a new 30-seed block per motor, the policy achieves 117/120 safe touchdowns (97.5%).

A separate randomized-order integrated supervisor evaluation achieves 115/120 (95.8%). The failed-motor identity is supplied by the experiment, so this validates allocator selection and execution but not online fault diagnosis.

## 4. Plant-model sensitivity

The M2 PINV branch was then subjected to one-at-a-time +/-10% perturbations of mass, physical thrust coefficient, motor time constant, thrust-to-torque ratio, and arm length.

Mass and thrust coefficient dominate the ED50 sensitivity, while the remaining three parameters produce much smaller shifts over the tested range.

A separate fixed-eta PINV-versus-CEM check shows no tested plant state in which CEM has a higher safe-touchdown count than PINV for M2. However, adverse +10% mass and -10% thrust coefficient perturbations cause both tested controllers to fail all paired trials at eta=0.496.

## 5. Overall interpretation

The combined experiments support a motor-conditioned allocation strategy: the best controller depends on failed-motor geometry, and freezing that routing generalizes well to fresh seeds within the same simulator distribution.

At the same time, controller selection does not remove dependence on plant authority. Large mass or thrust-coefficient mismatch can shift the safety boundary enough that both candidate controllers fail at the nominal operating point.
