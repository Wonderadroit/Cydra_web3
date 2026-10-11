# Blind campaign protocol

## Before execution
1. Confirm the target's current program scope and rules manually.
2. Record program URL/reference, permitted test methods, exclusions, target repository, exact commit, source path, and timestamp.
3. Prefer a local fork or isolated test environment; never broadcast transactions to live assets by default.
4. Record compiler, Foundry, dependency versions, remappings, and environment setup.

## Blindness
The hypothesis engine may receive the target source, build metadata, and general authorization invariant. It must not receive the expected vulnerable function or a known finding's answer key during candidate generation. Expected outcomes belong in a separate evaluator.

## Controls
- Positive control: a deliberately vulnerable authorization fixture with a known expected behavior.
- Negative control: a semantically protected fixture with an equivalent operation.
- Environment control: known-good compile/deploy/test proves the harness works independently of the candidate.
- Causal control: a minimal, semantically justified authorization guard changes the test outcome.
- Reproduction: rerun from a clean state, not from cached mutated state.

## Results
For each target, record counts of discovered external functions, state-changing candidates, hypotheses, rendered experiments, executed experiments, blocked experiments, and verified outcomes. Zero is a result and must remain visible.

Never interpret missing hypotheses as proof of safety. Never interpret process exit code zero as a security pass when a no-hypothesis mode is enabled.
