# CYDRA Web3 — Status

**Updated:** 2026-10-17  
**Rule:** LLMs propose. Tools test. Evidence decides. This file is the current status; PR count is not a status signal.

## On `main`
- The repository has an authorization-focused pipeline, source-effect modeling, direct-solc/compiler-closure work, campaign artifact persistence, and paired differential fixtures.
- Historical DcntEth `setRouter` is a validated positive control; it is not a novel finding.
- Guarded/unguarded fixture controls score correctly in the frozen authorization corpus. A novel or held-out unfamiliar-target finding is **not yet demonstrated**.
- Do not treat a green Python regression or a completed workflow as proof that a target experiment ran or a finding exists.

## Open and active
- **Active validation:** Virtuals campaign run [#39044831809](https://github.com/Wonderadroit/Cydra_web3/actions/runs/39044831809), branch `verification/direct-solc-integration`, SHA `8fe00176ee004f2592e593e8bc78f4796b336f46`. Direct-solc dependency-ancestry preflight passed; dependencies installed from the pinned Yarn lockfile.
- **Active fix:** [Draft PR #86](https://github.com/Wonderadroit/Cydra_web3/pull/86) adds compiler-AST cross-source write binding, a regression fixture, compiler-status persistence, and `pytest -q -rs`. CI passes on the verification branch; the PR is not merged. The exact skip is `Foundry toolchain is not installed` in the Python-only workflow, a setup/platform skip; the authorization workflow with Foundry installed passes without a skip.
- **Regression:** Python tests passed on the active run's branch. The workflow used `pytest -q`, not `-rs`; the skipped test's reason remains unknown.

## Known gap — Virtuals is upstream of the getter matcher
Pinned target: `code-423n4/2025-04-virtuals-protocol@28e93273daec5a9c73c438e216dde04c084be452`, `contracts/virtualPersona/AgentNftV2.sol`.

Artifact: [campaign artifact](https://github.com/Wonderadroit/Cydra_web3/actions/runs/39044831809/artifacts/12105063911).
- `solc-input-keys.json` contains 48 source keys and `solc-errors.json` is empty. The campaign JSON does **not** expose `compiler.status`, so do not claim that field was verified.
- The `addValidator` seed has `observed_writes: []`; provenance says `isValidator:callee_effect_or_authorization_unclassified`.
- `hypothesis_class` is absent. The hypothesis is merely `proposed`; no experiment was rendered or executed (`UNMEASURABLE`, exit 2, tests run 0).
- The renderer's message says no matching public scalar getter, but the artifact does not establish the expected write set `[_validators, _validatorsMap, _baseValidatorScore]`. Therefore the getter-matcher fix is **not yet justified**: first establish why helper/read-path effects were not propagated into the seed/hypothesis. Do not build a mapping/array observer on an empty modeled write set.

## Next milestone
1. In parallel, expose pytest skip reasons by changing the workflow invocation to `python -m pytest -q -rs` (or run that command in the same revision). Record the exact skipped test and reason.
2. Trace the pinned `addValidator` path through `isValidator`, `_addValidator`, and `_initValidatorScore`; make the artifact show compiler status, effective modeled writes with provenance, and hypothesis class before selecting the next fix.
3. Only if those fields prove the expected writes and `unguarded_setter`, implement the bounded getter matcher: global public getter → view function called from the target body that reads the same state → `isX`/`getX` name pattern. Add the mapping-write/reader paired-control fixture.
4. One final Virtuals cycle only. If it renders and produces a verdict, score it; if it is unmeasurable for a new reason, score that layer; if it fails for a third new reason, record it and move to a different supported-class target.

**Definition of done:** the corpus records the failure layer; the selected target's experiment is actually executed; vulnerable and guarded controls discriminate; evidence is persisted. No finding claim without causal differential and independent reproduction.
