# Hypothesis Generation Doctrine

## Purpose

Prevent CYDRA from becoming an endlessly improving extractor that never asks security questions. Extraction is inherently incomplete. The engine must convert available facts and observations into explicit, testable authorization hypotheses while preserving uncertainty.

## The stage boundary

1. **Facts** — what the source parser/compiler or deterministic tool directly observed.
2. **Semantic observations** — relationships among callers, guards, signers, state reads/writes, inherited functions, helper calls, lifecycle transitions, and external effects.
3. **Hypothesis seeds** — plausible questions suggested by those observations.
4. **Prioritized hypotheses** — seeds selected for investigation using impact plausibility, information gain, and feasibility.
5. **Experiments** — executable tests designed to distinguish the hypothesis from competing explanations.
6. **Disposition** — supported, rejected, confirmed, blocked, or unmeasurable based on actual evidence.

No stage may impersonate another. A seed is not proof; missing proof is not a reason to suppress a seed.

## Core rule: questions do not require answers in advance

A hypothesis generator must not require exploit evidence, deployment-state evidence, or complete semantic closure before it emits a provisional question. It must require traceable reasons for asking, then represent unknowns as unknowns.

For example, if the model observes that an externally reachable lifecycle function writes a privileged manager address, it should be able to emit a seed such as:

> Could an unauthorized caller set or replace the manager address in a reachable deployment state?

The seed must include the exact source/model provenance, the proposed authorization invariant, attacker capability under consideration, expected state transition, uncertainty, and prerequisites. If initialization state or proxy configuration is unavailable, record those as experiment prerequisites and mark the experiment blocked until resolved. Do not silently convert the seed into a finding or discard it because the answer is not yet known.

Likewise, observing signer recovery may seed a question about signer binding or replay resistance only when relevant to the authorization boundary. It does not prove a signature flaw, and the first milestone remains authorization failures rather than general signature-replay research.

## Generic seed prompts

Use semantic signals as prompts for questions, not as vulnerability verdicts:

- Externally reachable operation writes a privileged address, role, owner, manager, gateway, configuration, or other trust-boundary state.
- A state-changing operation has no visible local guard, has a guard with uncertain reachability/polarity, or reaches writes through a helper, inherited function, library, proxy, or delegate context.
- A caller or role comparison controls a state transition; determine which identity is actually checked and whether it matches the intended trust boundary.
- A signature/signer/payer/forwarder check authorizes an operation; determine which action, chain/domain, nonce, caller, and state transition the authorization actually binds where those concepts apply.
- An initializer or lifecycle transition can be called in more than one state, or the deployed initialization state is unknown.
- A privileged operation delegates authority to another contract or external call; determine whether the relevant check protects the effective state transition.
- A guard appears after a relevant effect or only protects one path; establish whether the path is reachable and whether the ordering changes authorization.
- A target model contains constraints or relationships that conflict with an apparent guard or intended role boundary.

Agents must not invent absent semantics. If the model cannot tell whether a write is privileged or whether a caller is trusted, emit a lower-confidence seed only when the uncertainty and evidence are stated, or record the precise modeling gap that prevents even a meaningful question.

## Hypothesis record minimum

Each seed should record:

- stable hypothesis ID and status PROPOSED;
- exact repository, immutable commit, contract/function, and source locations;
- source/model evidence IDs supporting the observation;
- the observed behavior, distinct from interpretation;
- the candidate authorization invariant;
- attacker capability being tested, including any assumptions;
- the state transition and potential impact if the invariant is violated;
- alternative explanations and relevant protected paths;
- unknowns, experiment prerequisites, and blockers;
- candidate discriminating experiment or reason no experiment can yet be planned.

Use UNKNOWN rather than guessed deployment state, actor identity, ABI values, constructor arguments, role semantics, or impact.

## Zero-hypothesis audit

Whenever a campaign produces zero seeds, the run must not stop at “no supported hypothesis generated.” It must perform or explicitly schedule this audit:

1. Export the observed relationships, state effects, predicates, constraints, and provenance.
2. Inspect them against the generic seed prompts above.
3. Record a short diagnostic mapping: observation → plausible question → evidence needed → experiment idea.
4. Classify the failure as one of:
   - NO_RELEVANT_SIGNAL_OBSERVED;
   - SIGNAL_NOT_MODELED;
   - SIGNAL_MODELED_BUT_NO_SEED_RULE;
   - SEED_EMITTED_BUT_FILTERED;
   - SEED_SELECTED_BUT_EXPERIMENT_UNPLANNABLE;
   - EXPERIMENT_BLOCKED;
   - EXPERIMENT_EXECUTED_NO_VIOLATION.
5. Attach source/model evidence to the classification. Do not infer a category merely from a zero count.
6. Add a reusable rule and regression fixture only for a demonstrated generic gap. Replay positive and protected negative controls and at least one frozen target.
7. Keep the original campaign disposition accurate; a diagnostic or new seed does not retroactively mean an experiment ran.

Manual seed drafting is a diagnostic tool for locating gaps, not a replacement for the automated engine. The engine must eventually produce the same class of seed independently, without being given the vulnerable function name.

## Experiment and finding discipline

- Select experiments for information gain, plausible impact, known preconditions, and execution cost.
- A missing prerequisite blocks execution; it does not erase the hypothesis.
- A compile-only result, generated test file, static alert, or unexecuted plan is not an experiment result.
- An execution failure caused by setup/environment is BLOCKED or UNMEASURABLE, not a rejection.
- A hypothesis is REJECTED only when an executed, relevant experiment provides evidence against it under documented preconditions.
- CONFIRMED requires reproducible security-relevant unauthorized impact, a protected negative control, a causal differential, clean independent reproduction, bounded impact, and human review.
- Preserve scope boundaries. Only test targets and methods the operator is authorized to test; use local controlled environments where possible.

## Agent decision rule

Before changing extraction, ask: **Which concrete hypothesis or experiment could this missing fact enable, and what evidence demonstrates the gap?**

Before changing hypothesis logic, ask: **Which observed semantic pattern should produce which falsifiable question, and how will a regression prove that the seed is emitted without falsely confirming it?**

Before declaring progress, state which stage moved and show its evidence. If only compilation or extraction improved, say so plainly. The next action must target the measured stage boundary, not “more completeness” in the abstract.