# Blind authorization campaign — Immunefi Vaults Splitter

## Intake

- Program: Immunefi
- Official scope: https://immunefi.com/bug-bounty/immunefi/scope/
- Official resources: https://immunefi.com/bug-bounty/immunefi/resources/
- Codebase resource: https://github.com/immunefi-team/vaults-splitter
- Target revision: 6f64c3f0557967eee9b14482ffa62187101c79ef
- Source: src/Splitter.sol
- Run: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124305839
- Artifact: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124305839/artifacts/11696288221
- Mode: local-only source/compiler/Foundry testing; no live transactions.

## Outcome

The campaign failed closed because it selected zero authorization hypotheses. The runner returned a non-zero exit status rather than treating zero hypotheses as a successful security investigation.

The model listed five functions:
- _changeFeeRecipient — internal
- changeFeeRecipient — public, onlyOwner
- payWhitehat — external, nonReentrant
- _payWhitehatNative — internal
- _refundCaller — internal

The source model reported no direct state writes for these functions, and no authorization invariant was emitted. No experiment was executed against this unfamiliar target. No vulnerability was found or ruled out.

## Interpretation

This is a **NOT_SELECTED / BLOCKED** measurement, not evidence that the target is secure and not a vulnerability finding. The only obvious administrative setter in the model, changeFeeRecipient, carries onlyOwner. This target therefore may be a poor positive example for a missing-authorization specialist, but the model's lack of surfaced state writes also warrants investigation of helper-mediated state-effect propagation at the authorization candidate-selection boundary.

Do not add a Splitter-specific exception or hardcode a function name. The next step is to test the state-effect model independently, then select another currently eligible target or a held-out control with a genuine authorization boundary. Keep the expected function hidden from the hypothesis engine.


## Follow-up after generic state-effect fix

- Fix PR: https://github.com/Wonderadroit/Cydra_web3/pull/3 (merged)
- Regression: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124536823 (passed)
- Post-fix replay: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124545350
- Post-fix artifact: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124545350/artifacts/11696084113

The parser now recognizes the mutable payable state variable, and the authorization model propagates the internal helper write to the externally callable wrapper. The replay log shows:

- _changeFeeRecipient writes feeRecipient.
- changeFeeRecipient writes feeRecipient via the helper.
- changeFeeRecipient has onlyOwner.
- payWhitehat has nonReentrant but no modeled storage write.
- The run still selects no authorization hypothesis and executes no candidate experiment.

This post-fix result changes the interpretation: the earlier missing-write model gap is fixed, but this target does not present an obvious missing-authorization candidate in the modeled surface. The no-hypothesis outcome is therefore still NOT_SELECTED / BLOCKED for coverage purposes, not proof that the target is secure and not a finding. The next test must use a distinct, currently eligible target or held-out positive control with an authorization boundary, while keeping the expected function hidden.
