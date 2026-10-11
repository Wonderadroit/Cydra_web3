# Migration status

## Repository baseline
- Destination: Wonderadroit/Cydra_web3
- Migration branch: migration/authorization-specialist-bootstrap
- Source repository: Wonderadroit/Cydra_wonder
- Source commit inspected and pinned for migration/control: 99f43987376a327c423ddde2877ce9995564d254

## What is now in this branch
- Specialist doctrine, migration map, file-level provenance manifest, campaign protocol, and binary Definition of Done.
- Initial authorization-specific source modules copied from the source repository: models, interface resolver, Solidity parser/model, AST dataflow evidence, semantic state effects, authorization reasoning, experiment planning/input helpers, planned call rendering, authorization test generation/runtime classification, compiler-state evidence, compiler constraints, Foundry execution helpers, initialization-shape helpers, and constraint candidates.
- A narrow authorization-only investigation entry point in src/cydra/authorization_pipeline.py; it does not invoke the broad multi-class pipeline.
- An adapted blind authorization campaign runner with an explicit no-hypothesis failure path and optional causal/reproduction readiness gate.
- Unit tests and Python regression workflows.
- Local-only historical positive and protected negative control workflows.

## Verified evidence
- Clean-repository Python regression passed at run #38124081424: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124081424
- Historical public Decent Bridge positive control passed its benchmark gate at run #38124120474: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124120474
  - Blind test detected the known unguarded setRouter state mutation.
  - Adding the inferred onlyOwner control changed execution from FAIL to PASS.
  - Independent reproduction and patched reproduction matched; causal verification and reproduction were both true.
  - This is an existing public issue, not a novel bounty discovery.
- Protected negative control passed at run #38124212770: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124212770
  - The state-gated setWhitelist test executed and classified as not_confirmed.
- Fresh blind unfamiliar-target replay on Immunefi Vaults Splitter failed closed with zero authorization hypotheses: run #38124305839. The model listed five functions but surfaced no direct state writes and emitted no authorization invariant; no experiment ran. This is NOT_SELECTED / BLOCKED, not evidence of safety. Details: docs/campaigns/2026-10-11-vaults-splitter.md.
- The unfamiliar-target hypothesis-selection blocker therefore remains open; no novel finding has been established.

## Current limitations
- This is a curated migration, not a claim that every useful capability from the source repository has been moved.
- Positive and negative controls are demonstrated, but the unfamiliar-target hypothesis-selection blocker remains open.
- No novel, independently verified bounty finding has been established from this repository.
- The current Python regression and latest branch checks must remain green before merging.

## Next steps
1. Confirm the latest branch regression after the control runners were added.
2. Keep the positive and negative controls as mandatory regressions.
3. Run a fresh blind campaign on a pinned, eligible, unfamiliar target without supplying the expected function.
4. If it returns no hypothesis or no executed experiment, diagnose that exact stage and fix the reusable cause.
5. Re-run both controls and the unfamiliar target after each fix.
6. Do not declare the specialist ready until the Definition of Done is met.
