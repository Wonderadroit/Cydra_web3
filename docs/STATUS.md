# Migration status

## Repository baseline
- Destination: Wonderadroit/Cydra_web3
- Initial default branch contained only a minimal README.
- Migration branch: migration/authorization-specialist-bootstrap
- Source repository: Wonderadroit/Cydra_wonder
- Source commit inspected: 99f43987376a327c423ddde2877ce9995564d254

## Verified capability and failure evidence
- Existing authorization regression passed in source repository run #38122838300.
- Historical Decent Bridge authorization positive control is a previously known issue, not a novel discovery.
- The latest unfamiliar campaign selected zero authorization hypotheses for its unfamiliar targets.
- The blind runner's no-hypothesis mode can return process exit code zero while recording finding_gate=NOT_READY.

## What this branch currently contains
This branch establishes the specialty doctrine, migration map, campaign protocol, and binary definition of done. It is not yet a complete code migration. The next migration step is to port the authorization-specific implementation and its minimal dependency closure, then run it in this repository.

## Immediate implementation order
1. Extract the minimal authorization path from the source dependency graph; do not import the broad multi-class pipeline wholesale.
2. Port model/parser/compiler evidence and authorization hypothesis generation.
3. Port experiment rendering/execution with fail-closed preconditions.
4. Port positive/negative fixtures and regression tests.
5. Build a clean authorization-only workflow whose security gate fails or stays not-ready if no meaningful experiment executes.
6. Run a fresh blind campaign on a pinned, eligible, unfamiliar target.
7. Fix only demonstrated reusable blockers, then replay all controls.
