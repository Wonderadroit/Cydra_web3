# CYDRA Web3 — Project Bible

## Mission

CYDRA Web3 is a personal, evidence-first research engine for identifying and validating one initial vulnerability class: missing or ineffective authorization on externally callable state-changing smart-contract operations. It is intended for targets the operator is explicitly permitted to test. It is not a general-purpose scanner and is not a commercial product.

The first milestone is not “support every EVM bug.” It is to reliably investigate this one class across unfamiliar Solidity/EVM projects without target-specific code patches for ordinary project differences.

## Non-negotiable doctrine

- Authorized scope and program rules constrain every campaign.
- LLMs propose. Deterministic tools test. Evidence decides.
- A source pattern or static-analysis alert is a hypothesis, never a finding.
- Never fabricate source, functions, roles, state, constructor values, transactions, impact, or evidence.
- Never treat a green workflow as proof of a security result.
- Distinguish NOT_PRESENT, NOT_SELECTED, BLOCKED, UNMEASURABLE, REJECTED, and CONFIRMED; do not collapse them into “safe” or “vulnerable.”
- Every hypothesis must link to exact source revision, source locations, modeled state effects, invariant, experiment, execution output, and conclusion.
- Positive controls must be paired with protected/negative controls.
- A finding requires a reproducible causal test and meaningful security impact, followed by human review before any external report.
- Historical public findings are benchmark material only, never new discoveries.
- Fix reusable capability gaps; do not add target-name/function-name special cases to make a benchmark pass.
- A failed experiment is evidence about the test or environment unless the target behavior itself was successfully observed.
- Keep the source repository intact; this repository is a curated migration, not a destructive move.

## Initial specialty

Authorization boundary failure: an arbitrary or insufficiently privileged caller can perform a state transition that should be restricted by the contract's actual security model.

The specialist must reason about semantics, not merely function names or modifier presence. A function can be protected indirectly; a modifier can be ineffective; a write can occur through a helper; and an unguarded function is not automatically a vulnerability. The contract's intended trust boundary and impact must be supported by evidence.

## Canonical investigation loop

1. Freeze authorization/scope record and exact target commit.
2. Resolve project environment: Solidity version, framework, source roots, imports/remappings, libraries, deployable contracts, constructor requirements, and blockers.
3. Build a provenance-linked model of externally callable functions, modifiers, internal call paths, state reads/writes, external calls, roles, and relevant assets.
4. Form authorization invariants and competing hypotheses from the target model.
5. Select the highest-information executable experiment whose preconditions are known.
6. Generate a faithful local test without inventing ABI values or bypassing setup requirements.
7. Execute the test and preserve raw output, tool versions, source revision, and environment snapshot.
8. If behavior suggests a violation, challenge the hypothesis with a protected control and a causal patch/differential.
9. Reproduce independently from a clean execution state.
10. Report confirmed findings or precise blockers. Never silently call incomplete coverage a pass.

## Completion contract

The specialist is ready for unfamiliar-target use only when a blind, frozen campaign can:
- identify candidate authorization boundaries without being told the vulnerable function;
- model direct and helper-mediated state effects;
- generate and execute meaningful experiments across multiple structurally different, previously unseen targets;
- detect deliberately vulnerable positive controls and reject protected negative controls;
- establish causal impact and independent reproduction for claimed findings;
- preserve exact evidence and clearly report all untested/blocked surfaces;
- replay all prior controls without regressions.

Passing unit tests, compiling source, or generating hypotheses alone does not satisfy this contract. A benchmark pass is bounded evidence, not a guarantee that every real target can be solved.

## Explicit out-of-scope for the first milestone

Reentrancy, arithmetic, signature replay, oracle manipulation, intent parity, general Web2 testing, broad autonomous live exploitation, and generic multi-class research loops. Preserve useful source/history as reference, but do not let these classes expand the first milestone.

## Operator responsibility

The operator verifies program eligibility, scope, permitted testing methods, target revision, and any external disclosure. Use local forks or controlled environments where possible. Do not send transactions or interact with live assets unless the program explicitly permits the exact activity.

## Mandatory hypothesis-generation rule

Hypotheses are questions, not conclusions. The generator must emit traceable provisional authorization hypothesis seeds from meaningful target observations without requiring exploit proof, complete deployment-state evidence, or complete extraction first. Missing facts belong in the seed's uncertainty/prerequisite fields and may block an experiment; they must not silently suppress the question.

Keep these stages explicit: facts → semantic observations → hypothesis seeds → prioritized hypotheses → executable experiments → evidence-based disposition. For example, a modeled lifecycle function that writes a privileged manager address should seed a question about whether an unauthorized caller can change that state in a reachable deployment. It must not be called vulnerable without testing, and it must not be discarded merely because initialization state is not yet known.

Every zero-hypothesis campaign must trigger a hypothesis-generation audit: review the actual relationships, constraints, state effects, guards, and provenance; map plausible observations to falsifiable questions; classify whether the signal was absent, not modeled, not converted to a seed, filtered, or unable to reach an executable experiment; and record evidence for that diagnosis. Fix a measured generic gap, add a regression, and replay controls. Do not default to another broad extraction rewrite.

See [Agent Instructions](../AGENTS.md) and [Hypothesis Generation Doctrine](docs/HYPOTHESIS_GENERATION_DOCTRINE.md) for the mandatory rules and report fields.
