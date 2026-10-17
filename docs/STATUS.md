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


## Week 1 Day 2 — complete
- PublicGetterObservation: scalar public-getter resolution extracted from _resolve_state_observer; missing/reverting reads fail closed with a recorded reason.
- ScalarWrite: direct and compound scalar assignments use constructor-injected compiler declaration IDs; local shadowing is rejected and struct-field writes remain deferred.
- Tests: 4 PublicGetterObservation tests and 5 ScalarWrite tests.
- Gate: full Python regression passed on the implementation-equivalent code at commit 88f5cee86d704368aa0675f7779c194bc69990e0 (run #39076655550). The only subsequent change in this commit is this status entry.


## Week 1 Day 3 — complete
- NestedMappingWrite: detects assignment and compound-assignment writes through one or more IndexAccess nodes, returning the compiler-identified state-variable root.
- Negative boundary: MemberAccess roots are rejected; local struct fields are not treated as contract-state mappings.
- Tests: 5 focused tests passed in the full regression.
- CI evidence: implementation commit e8010881698008943ac32d0ee4ba96c0fc20e077 passed Python Regression run [#39077235129](https://github.com/Wonderadroit/Cydra_web3/actions/runs/39077235129) and pull-request regression [#39077238528](https://github.com/Wonderadroit/Cydra_web3/actions/runs/39077238528). Authorization campaign job was skipped; no target experiment or finding is claimed.
- Observation interfaces unchanged. Day 4 implemented ArrayPushWrite as a separate capability.


## Week 1 Day 4 — complete
- ArrayPushWrite: recognizes FunctionCall nodes whose callee is a push/pop MemberAccess and whose receiver resolves through zero or more IndexAccess nodes to a compiler-identified state-variable Identifier.
- Root extraction is explicit: `_validators[virtualId].push(validator)` returns `_validators`; indexed entries are not treated as the write target.
- Tests: 5 focused tests passed in full regression, including mapping-entry push, direct state-array push, mapping-entry pop, local-array rejection by declaration identity, and base-root extraction for a mapping-entry array.
- CI evidence: implementation commit [67ad55935219ff4563bb42377f73783c4e3a9a3f](https://github.com/Wonderadroit/Cydra_web3/commit/67ad55935219ff4563bb42377f73783c4e3a9a3f) passed Python Regression run [#39077595226](https://github.com/Wonderadroit/Cydra_web3/actions/runs/39077595226). The authorization workflow's Python regression also passed in [#39077595229](https://github.com/Wonderadroit/Cydra_web3/actions/runs/39077595229); its blind authorization campaign job was skipped. No Virtuals campaign or finding is claimed.
- WriteForm and observation interfaces unchanged. Day 5 is MappingGetterObservation only; Day 6 is ExplicitViewReaderObservation. Virtuals remains open until a campaign artifact proves the expected write roots and observation path are wired.

## Week 1 Day 5 — MappingGetterObservation
- Extended ObservationMethod.emit_probe and read_state with optional argument lists. Existing one-argument call sites remain valid; this is an explicit interface extension for mapping observations.
- Added MappingGetterObservation for source-backed public mapping getters and conventional getX view readers. It fails closed with the shared reason vocabulary for missing getters, argument-arity mismatches, and reverting calls.
- Boundary test is deliberate: a private nested mapping read by isValidator is not claimed by MappingGetterObservation. It returns getter_not_found and leaves custom semantic readers to Day 6 ExplicitViewReaderObservation; no raw-storage or arbitrary-candidate fallback.
- The existing PublicGetterObservation implementation used different legacy missing/revert strings than the intended shared vocabulary, so those paths were normalized to getter_not_found and call_reverted; its tests were updated accordingly.
- Tests: five focused MappingGetterObservation tests plus the updated PublicGetterObservation regression passed in Python Regression run [#39077941503](https://github.com/Wonderadroit/Cydra_web3/actions/runs/39077941503) on implementation commit [c5c0291d1c96958c81fffa259fd5d1fc452fa4a1](https://github.com/Wonderadroit/Cydra_web3/commit/c5c0291d1c96958c81fffa259fd5d1fc452fa4a1). The blind authorization campaign job was skipped; no Virtuals campaign or finding is claimed.
- Next: Day 6 ExplicitViewReaderObservation, then one Virtuals campaign. Do not dispatch the campaign before Day 6.

