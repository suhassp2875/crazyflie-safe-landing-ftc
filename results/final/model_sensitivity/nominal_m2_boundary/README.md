# Nominal M2 Boundary Completion

The existing nominal seeded boundary study contains fitted QP-lite
and CEM curves for M1, M3, and M4, but not M2.

Existing M2 files were not reused because:

- RL-tuning tables contain candidate-selection predictions rather
  than seeded touchdown outcomes.
- Older recoverability tables contain only three unseeded trials
  per eta and use a legacy fixed-boost protocol.
- Legacy first-contact rechecks use a different scripted controller.

A fresh paired M2-only boundary experiment is therefore required.

## Coarse localization

PINV eta grid:

- 0.486
- 0.488
- 0.490
- 0.492
- 0.494
- 0.496

CEM-tuned QP-lite eta grid:

- 0.496
- 0.497
- 0.498
- 0.499
- 0.500
- 0.502

Each condition uses the same 12 logged seeds from the
`seeded_ic_v1` distribution.

The purpose of this stage is only to bracket the 50% transition.
A denser paired fine sweep will be run around each located midpoint.
