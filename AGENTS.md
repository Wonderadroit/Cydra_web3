# Agent Instructions — CYDRA Web3

Read PROJECT_BIBLE.md before making changes.

## Required workflow

1. State the specific authorization-specialist capability being changed and the failure evidence that motivates it.
2. Trace the relevant implementation and tests before editing.
3. Make the smallest reusable change that addresses the root cause.
4. Add a regression test for the failure and preserve relevant positive and negative controls.
5. Run targeted tests, then the complete available regression suite.
6. For target campaigns, pin source commit and preserve command, environment, raw output, and result artifacts.
7. Report code/test status separately from security-discovery status.

## Bounded authorization-seed analysis

- Analysis budget for provisional authorization seeds: direct call sites and at most one inheritance level. Do not build a recursive/interprocedural resolver or resolve cross-contract implementations in this milestone.
- A direct call site is unresolved when the model cannot classify its callee's security-relevant effects or authorization behavior within that budget. Either unknown is sufficient to produce a blocked seed.
- An externally callable function with a state write, lifecycle-sensitive behavior, or an unresolved security-relevant execution path must not be silently omitted. An unresolved path produces a blocked seed and records the call site as provenance.
- Every seed records invariant_source as derived (supported by target model evidence) or generic (doctrine-level invariant used because target-specific semantics are not established). Never phrase a generic invariant as a target-derived fact.
- A resolved call alone is not a reason to seed. Preserve negative controls so classified calls do not create noise.
- View/pure functions that may disclose security-sensitive state or influence external decisions are out of scope for this authorization state-transition milestone; do not silently treat this exclusion as a security guarantee.
- Seeds are questions, not findings. Seed coverage acceptance does not establish exploitability or a bounty-worthy vulnerability.

## Do not

- Claim a vulnerability from a hypothesis, compilation result, static alert, or green CI alone.
- Relax the finding gate merely to make a workflow green.
- Make target-specific exceptions based on repository, contract, or function names.
- Silently fabricate constructor inputs, role identities, ABI values, state, or authorization intent.
- Use historical benchmark findings as novel discoveries.
- Delete or overwrite the source repository as part of migration.
- Add another vulnerability class to the first milestone without an explicit scope decision.

## Required status vocabulary

Use precise outcomes: CONFIRMED, REJECTED, NOT_SELECTED, BLOCKED, UNMEASURABLE, and NOT_RUN. A workflow can pass as a measurement job while its security gate remains not ready; state both outcomes explicitly.
