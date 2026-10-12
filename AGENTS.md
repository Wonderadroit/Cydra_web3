# Agent Instructions — CYDRA Web3

Read `PROJECT_BIBLE.md`, `docs/DEFINITION_OF_DONE.md`, and `docs/HYPOTHESIS_GENERATION_DOCTRINE.md` before making changes.

## Mission and scope

CYDRA Web3 is an authorization-specialist research engine. The first milestone investigates missing or ineffective authorization on externally callable state-changing Solidity/EVM operations in targets the operator is explicitly permitted to test. Do not expand the vulnerability class without an explicit scope decision.

## Required workflow

1. State the specific authorization-specialist capability being changed and cite the failure evidence that motivates it.
2. Trace the relevant implementation, data flow, artifacts, and tests before editing.
3. Make the smallest reusable change that addresses the measured root cause.
4. Add a regression test for the failure and preserve relevant positive and protected negative controls.
5. Run targeted tests, then the complete available regression suite.
6. For target campaigns, pin the exact source commit and preserve scope record, command, environment, raw output, and result artifacts.
7. Report engineering/test status separately from hypothesis, experiment, and security-discovery status.
8. If the campaign has zero hypotheses or experiments, report that as a first-class result and investigate the model-to-hypothesis transition before doing unrelated extraction work.

## Hypothesis-generation rules — mandatory for every agent

- **A hypothesis is a question, not a conclusion.** Emit a provisional, explicitly unconfirmed hypothesis when a target observation gives a plausible authorization boundary to test. Do not require exploit proof, runtime state, or complete deployment evidence before recording the question.
- Keep the stages separate: **facts → observations → hypothesis seeds → prioritized hypotheses → experiments → evidence-based disposition**. Never silently skip from facts to a finding.
- A hypothesis seed may have missing prerequisites. Record each prerequisite as an experiment requirement or blocker; do not use missing evidence as a reason to suppress the seed.
- Separate **hypothesis existence** from **hypothesis support**. Source/model evidence may justify asking a question; only deterministic testing can support, reject, or confirm the claim.
- Every seed must be traceable to evidence that actually exists: target commit, source path/line or model artifact, observed behavior, proposed invariant, attacker capability, possible state transition/impact, and uncertainty. Mark missing fields unknown; never fabricate them.
- Generate seeds from generic semantic patterns, not only function names. Examples include: externally reachable writes to privileged state; authorization checks and their polarity/order; signer recovery and signer binding; caller/role comparisons; inherited/helper-mediated state changes; initialization and upgrade lifecycle; cross-contract calls that carry authority; and state changes whose guards may be bypassed on a reachable path. These are question prompts, not vulnerability verdicts.
- For each seed, consider competing explanations: inherited modifiers, role checks, proxy/delegate context, constructor/initializer constraints, trusted forwarders, signature/domain/nonce binding, helper checks, and program-defined trust boundaries when evidence indicates they may apply.
- Do not label every unguarded function vulnerable. Do not assume a function is sensitive from its name alone. A hypothesis is eligible for prioritization when the modeled transition and plausible security invariant are stated, even if some facts remain unknown.
- Prioritize experiments by expected information gain, impact plausibility, executable preconditions, and cost. If preconditions are missing, keep the hypothesis and mark the experiment BLOCKED or UNMEASURABLE with the exact missing capability.
- A campaign with zero hypotheses must trigger a **hypothesis-generation audit**: inspect extracted facts/relationships/constraints, list plausible seeds manually for diagnosis, identify which semantic feature should have triggered each seed, and add only evidence-backed generic rules plus regression fixtures. Do not automatically conclude that extraction is the root cause.
- Keep proposed, supported, rejected, and confirmed distinct. A generated seed is not a finding; an unexecuted experiment is not a negative result; a blocked campaign is not proof of safety.
- Never lower the finding gate to make a benchmark pass. Confirmed findings still require executed reproduction, security-relevant impact, protected negative controls, causal verification, independent reproduction, and human review.

## Bounded authorization-seed analysis

- Analysis budget for provisional authorization seeds: direct call sites and at most one inheritance level. Do not build a recursive/interprocedural resolver or resolve cross-contract implementations in this milestone.
- A direct call site is unresolved when the model cannot classify its callee's security-relevant effects or authorization behavior within that budget. Either unknown is sufficient to produce a blocked seed.
- An externally callable function with a state write, lifecycle-sensitive behavior, or an unresolved security-relevant execution path must not be silently omitted. An unresolved path produces a blocked seed and records the call site as provenance.
- Inherited declarations are context only unless their bodies are in the selected analysis scope. Record out-of-scope inherited bodies explicitly; do not load/resolve their implementations just to avoid a blocked seed.
- Every seed records invariant_source as derived (supported by target model evidence) or generic (doctrine-level invariant used because target-specific semantics are not established). Never phrase a generic invariant as a target-derived fact.
- A resolved call alone is not a reason to seed. Preserve negative controls so classified calls do not create noise.
- View/pure functions that may disclose security-sensitive state or influence external decisions are out of scope for this authorization state-transition milestone; do not silently treat this exclusion as a security guarantee.
- Seeds are questions, not findings. Seed coverage acceptance does not establish exploitability or a bounty-worthy vulnerability.

## Do not

- Claim a vulnerability from a hypothesis, compilation result, static alert, generated-but-unexecuted test, or green CI alone.
- Relax the finding gate merely to make a workflow green.
- Make target-specific exceptions based on repository, contract, or function names.
- Silently fabricate constructor inputs, role identities, ABI values, state, authorization intent, deployment facts, or evidence.
- Use historical benchmark findings as novel discoveries.
- Delete or overwrite the source repository as part of migration.
- Add another vulnerability class to the first milestone without an explicit scope decision.
- Treat incomplete extraction as a reason to stop asking hypotheses; instead, emit bounded seeds and record the missing prerequisites.

## Required status vocabulary

Use precise outcomes: `CONFIRMED`, `REJECTED`, `NOT_SELECTED`, `BLOCKED`, `UNMEASURABLE`, and `NOT_RUN`. Also distinguish hypothesis status (`PROPOSED` / `SUPPORTED` / `REJECTED` / `CONFIRMED`) from experiment status. A workflow can pass as a measurement job while its security gate remains not ready; state both outcomes explicitly.

## Required report fields

Every campaign report must state:
- exact target and immutable source revision;
- scope/authorization basis and coverage limits;
- extracted facts and semantic observations with provenance;
- hypothesis seeds emitted, selected, deferred, rejected, or blocked and why;
- experiment preconditions and whether execution actually occurred;
- raw evidence and tool/environment details;
- negative-control, causal-differential, and independent-reproduction results;
- separate engineering status and security-discovery disposition;
- next action tied to a measured gap, not a generic promise to improve extraction.
