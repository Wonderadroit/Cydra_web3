# Curated migration map

Source of truth inspected: Wonderadroit/Cydra_wonder, main, commit 99f43987376a327c423ddde2877ce9995564d254.

This document is a migration ledger, not a claim that all code has already been copied. The source repository remains unchanged.

## Keep in the first Web3 specialist

| Capability | Source candidates | Migration rule |
|---|---|---|
| Core models and evidence provenance | src/cydra/models.py, src/cydra/interface_resolver.py | Keep only types required by the authorization path, with provenance intact |
| Solidity project understanding | src/cydra/solidity_model.py, compiler/environment helpers | Keep deterministic parsing and target-environment resolution |
| Authorization hypothesis reasoning | src/cydra/reasoning.py, src/cydra/structural_authorization.py, src/cydra/semantic_state_effects.py | Retain the authorization invariant and helper-mediated writes; avoid importing unrelated vulnerability classes |
| Compiler-backed state effects | src/cydra/compiler_state.py, src/cydra/ast_dataflow.py, src/cydra/compiler_constraints.py | Preserve compiler evidence and source locations |
| Experiment generation/execution | src/cydra/blind_authorization.py, src/cydra/authorization_runtime.py, src/cydra/foundry.py, related call/parameter/interface helpers | Preserve fail-closed behavior and explicit precondition failures |
| Blind runner | scripts/run_benchmark_006_blind_auth.py | Use as a starting point; isolate authorization-only orchestration |
| Positive and negative controls | scripts/run_benchmark_001.py, scripts/run_benchmark_001_negative_control.py, scripts/run_benchmark_006_blind_auth_negative.py, selected frozen benchmark fixtures | Keep expected outcomes explicit and avoid treating old public findings as new discoveries |
| Existing specialist workflow | .github/workflows/web3-authorization-specialist.yml, .github/workflows/web3-unfamiliar-authorization-gate.yml | Rebuild with explicit inputs, pinned targets, and separate engineering/security gates |
| Engineering doctrine | PROJECT_BIBLE.md, AGENTS.md, relevant benchmark reports | Rewrite for this single specialty; don't copy the entire old project bible unchanged |

## Preserve as reference, do not put in the initial execution path

- Other vulnerability classes and their structural/planning modules.
- Web2 discovery workflows and Aurory-specific artifacts.
- Open-ended research loops and broad multi-finding campaigns.
- Duplicate historical workflows, abandoned branches, and target-specific workarounds.
- Any benchmark whose setup or result is not reproducible from its recorded evidence.

## Migration acceptance checklist

- [ ] Each imported module has a recorded source path and source commit.
- [ ] Dependency closure is understood; no accidental dependency on unrelated vulnerability classes.
- [ ] Fresh-repo install and unit tests pass.
- [ ] Positive and negative authorization controls pass.
- [ ] The two latest unfamiliar-target failures are represented as regression cases for the correct reason: zero authorization hypotheses, not “target is safe.”
- [ ] Unfamiliar-target gate cannot be green solely because --allow-no-hypothesis returned exit code zero.
- [ ] All test/campaign results distinguish engineering pass from security readiness.
- [ ] A blind campaign on a pinned, eligible, unfamiliar target executes at least one meaningful experiment.
- [ ] No claim of full migration until this checklist and file-level provenance are verified.

## Known starting blocker

In source commit 99f4398..., scripts/run_benchmark_006_blind_auth.py selects only INV-AUTH-001. The latest unfamiliar campaign returned NO_AUTH_HYPOTHESIS on its targets; one path had a callback/state-order hypothesis and another an intent-parity hypothesis. These are not authorization findings. The next work should isolate the authorization-specific reasoning path and ensure campaign readiness is not inferred from process exit status alone.
