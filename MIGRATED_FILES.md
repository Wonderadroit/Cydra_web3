# Migrated source manifest

Every file listed below was copied from Wonderadroit/Cydra_wonder at source commit 99f43987376a327c423ddde2877ce9995564d254 unless otherwise noted. The copied implementation is not evidence that the end-to-end specialist is complete; it is a curated initial dependency slice.

| Destination | Source path | Role |
|---|---|---|
| src/cydra/__init__.py | src/cydra/__init__.py | Package marker |
| src/cydra/models.py | src/cydra/models.py | Evidence, contract, hypothesis, and experiment data models |
| src/cydra/interface_resolver.py | src/cydra/interface_resolver.py | Interface/type resolution |
| src/cydra/solidity_model.py | src/cydra/solidity_model.py | Solidity source modeling |
| src/cydra/ast_dataflow.py | src/cydra/ast_dataflow.py | AST relationship evidence |
| src/cydra/semantic_state_effects.py | src/cydra/semantic_state_effects.py | State-effect index |
| src/cydra/structural_authorization.py | src/cydra/structural_authorization.py | Structural authorization hypotheses |
| src/cydra/reasoning.py | src/cydra/reasoning.py | Authorization invariant and hypothesis planning |
| src/cydra/experiment_planning.py | src/cydra/experiment_planning.py | Experiment model binding |
| src/cydra/experiment_inputs.py | src/cydra/experiment_inputs.py | Conservative parameter inputs |
| src/cydra/planned_call.py | src/cydra/planned_call.py | Planned call rendering |
| src/cydra/authorization_runtime.py | src/cydra/authorization_runtime.py | Execution classification |
| src/cydra/blind_authorization.py | src/cydra/blind_authorization.py | Blind Foundry test generation |
| src/cydra/compiler_state.py | src/cydra/compiler_state.py | Compiler-backed AST/state evidence |
| src/cydra/compiler_constraints.py | src/cydra/compiler_constraints.py | Compiler parameter constraints |
| src/cydra/foundry.py | src/cydra/foundry.py | Foundry test generation and execution helpers |
| src/cydra/initialization_shapes.py | src/cydra/initialization_shapes.py | Shared deployment/initialization shape helper |
| src/cydra/constraint_candidates.py | src/cydra/constraint_candidates.py | Constraint candidate helper |

## New files in Cydra_web3

- src/cydra/authorization_pipeline.py — narrow wrapper that runs only authorization hypothesis generation.
- scripts/run_authorization_campaign.py — adapted blind runner; imports the new authorization-only entry point instead of the broad multi-class pipeline.
- scripts/run_authorization_negative_control.py — adapted runner for the pinned protected control fixture.
- tests/test_authorization_pipeline.py — initial tests for hypothesis scope and explicit no-hypothesis outcomes.
- .github/workflows/python-regression.yml — fresh-repository Python regression.
- .github/workflows/authorization-specialist.yml — manual authorized-target campaign with required scope intake and explicit readiness gate.
- .github/workflows/authorization-positive-control.yml — local-only historical positive-control replay.
- .github/workflows/authorization-negative-control.yml — pinned protected negative-control replay.

## Deliberately not copied wholesale

The old pipeline imports numerous unrelated vulnerability classes. It was not copied wholesale because that would recreate the same mixed scope this repository is intended to remove. Remaining helper dependencies should be added only when a focused test demonstrates they are required.
