# Migration status

## Repository baseline
- Destination: Wonderadroit/Cydra_web3
- Migration branch: migration/authorization-specialist-bootstrap
- Source repository: Wonderadroit/Cydra_wonder
- Source commit inspected: 99f43987376a327c423ddde2877ce9995564d254

## What is now in this branch
- Specialist doctrine and project instructions.
- Curated migration map, campaign protocol, and binary definition of done.
- Initial authorization-specific source modules copied from the source repository: models, interface resolver, Solidity parser/model, AST dataflow evidence, semantic state effects, authorization reasoning, experiment planning/input helpers, planned call rendering, authorization test generation/runtime classification, compiler-state evidence, compiler constraints, Foundry execution helpers, initialization-shape helpers, and constraint candidates.
- A new authorization-only investigation entry point in src/cydra/authorization_pipeline.py. It intentionally does not invoke the broad multi-class pipeline.
- Initial unit tests and a Python regression workflow.

## Verified capability and failure evidence
- Existing authorization regression passed in source repository run #38122838300.
- Historical Decent Bridge authorization positive control is a previously known issue, not a novel discovery.
- The latest unfamiliar campaign selected zero authorization hypotheses for its unfamiliar targets.
- The old blind runner's no-hypothesis mode can return process exit code zero while recording finding_gate=NOT_READY.

## Current limitations
- This is a partial code migration, not yet a complete runnable specialist.
- The new authorization-only entry point generates hypotheses and plans experiments, but it does not yet provide the full blind campaign execution and causal-proof loop in this repository.
- The newly added tests have not yet been verified by a completed GitHub Actions run.
- No unfamiliar-target campaign or new finding has been established from this repository.

## Next steps
1. Get the clean-repo regression green and repair only reproducible failures.
2. Port the blind experiment runner with explicit fail-closed readiness semantics.
3. Port and replay vulnerable and protected authorization controls.
4. Ensure zero hypotheses or zero executed experiments cannot satisfy the security-readiness gate.
5. Run a fresh blind campaign on a pinned, eligible, unfamiliar target.
6. Fix demonstrated reusable blockers, then replay all controls.
