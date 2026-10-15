# Authorization specialist — Definition of Done

The first specialty is not complete until every gate below has evidence.

## Gate A — Target integrity
- Target is explicitly authorized and in scope.
- Repository URL, exact commit, source path, compiler/framework, and campaign configuration are frozen.
- No target-specific function name is supplied to the hypothesis engine.

## Gate B — Target model
- Externally callable state-changing surface is enumerated.
- Direct and helper-mediated state effects have source-linked provenance.
- Modifiers, inherited checks, role checks, proxy/delegate behavior, and relevant cross-contract calls are represented when supported.
- Unknown or unresolved surfaces are reported as blockers, not omitted silently.

## Gate C — Hypothesis quality
- Authorization hypotheses follow from observed target behavior and security boundaries.
- Each hypothesis identifies the caller capability, operation/state transition, invariant, and reason it may violate the invariant.
- Protected functions and alternative explanations are considered.
- No function-name-only heuristic is sufficient to promote a hypothesis.

## Gate D — Executable experiment
- Test preconditions and constructor arguments are grounded in the target's actual ABI/project model.
- A local execution occurs; compile-only and generated-but-not-run tests do not count.
- The test has a meaningful unauthorized caller and observes a security-relevant state transition.
- Failed setup is classified as BLOCKED or UNMEASURABLE, not as evidence that authorization is correct or absent.

## Gate E — Causal proof
- A vulnerable positive control is detected.
- A protected negative control is rejected.
- For a candidate real issue, a minimal causal authorization control changes the outcome as expected.
- A clean independent reproduction produces the same differential.
- Impact is demonstrated and bounded; no unsupported economic or asset-loss claims.

## Gate F — Unfamiliar-target robustness
- Multiple structurally different targets are tested blind at pinned revisions.
- At least one target is not selected from a known vulnerable function list.
- The same generic engine runs without repository/function-name patches.
- Previously passing controls replay without regressions.
- Every untested surface and failure is disclosed.

## Reporting

The campaign report must include separate fields for engineering job status, hypothesis selection status, experiment execution status, causal verification status, independent reproduction status, final finding gate, blockers, and coverage limits.

A run is not ready if it compiles but executes zero meaningful experiments, produces zero hypotheses, or cannot verify impact. A completed measurement is not the same as a completed security investigation.


## Campaign artifact doctrine — mandatory

Every campaign artifact must preserve both:
- the exact generated Solidity test source that was passed to Foundry; and
- the structured execution/campaign record (including target pin, hypothesis/experiment, execution status, classification, evidence, and blockers).

Also retain the target-intake record and human-readable execution log. Artifact preservation is part of the experiment's reproducibility contract, not optional debugging output. If a generated test cannot be rendered, record that fact and the specific reason in the structured record; never imply a test ran when no generated source was executed.

## Preconditions before interpreting authorization results

A passing assertion is not evidence of correct authorization unless the experiment established the target's required operating preconditions. If deployment topology, initialization, roles, registrations, or required state are not established, classify the experiment as `UNMEASURABLE` with a specific blocker (for example, `preconditions_not_established`), not rejected/not-confirmed. Do not fabricate target state or silently expand the generic harness to support a new setup model.
