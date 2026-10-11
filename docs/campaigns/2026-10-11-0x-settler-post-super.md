# Held-out 0x Settler replay after inherited-super authorization modeling

- Program scope: https://immunefi.com/bug-bounty/0x/scope/
- Public source: https://github.com/0xProject/0x-settler
- Pinned source commit: `872b0e4cc83cce6a75eb4a1705f5bfd06e21a6c5`
- Entry source: `src/chains/Mainnet/Intent.sol`
- Workflow: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38144275019
- Artifact: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38144275019/artifacts/11704470406
- Workflow commit: `ef96c00d895bd8fc4777e93cd334f4c342604973`
- Execution: pinned source checkout and isolated local analysis only; no on-chain transactions were sent.

## Result

The replay completed successfully as a workflow, but the security campaign remains **BLOCKED / NOT_READY**:
- Compiler: executed; version `0.8.33`; reported `no_ast_for_source`.
- The entry contract was modeled with 13 locally declared functions.
- `executeMetaTxn` was modeled as public with no local modeled writes or modifiers.
- Zero authorization hypotheses and zero candidate experiments were generated.
- Classification: `NO_AUTH_HYPOTHESIS`; blocker: `NO_SUPPORTED_HYPOTHESIS`.
- This is not a vulnerability finding, not a negative control, and not evidence that the target is secure.

## What changed

PR #13 added a narrow rule for inherited modifier reasoning: an overriding function may inherit the base implementation's modifier evidence only when its body explicitly dispatches to the same function through `super`. The paired synthetic regression passes both the protected super-dispatch path and an unguarded override path. PR: https://github.com/Wonderadroit/Cydra_web3/pull/13

The held-out replay did **not** improve its target-level classification. The campaign artifact still exposes only the entry contract's local function model and does not evidence the effective inherited modifier or the downstream authorization chain. Therefore, the generic rule is a verified narrow improvement, not closure of the Settler capability gap.

## Source-path review (static evidence, not a finding)

At the pinned revision:
- `MainnetSettlerIntent.executeMetaTxn` calls `super.executeMetaTxn(...)`.
- The inherited implementation in `src/SettlerMetaTxn.sol` uses the `metaTx(msgSender, witness)` modifier.
- The `Permit2PaymentMetaTxn` implementation of that modifier rejects forwarded calls, rejects a confused-deputy condition, records a witness and payer in transient storage, executes the body, then clears the payer and checks that the witness was spent.
- The inherited meta-transaction execution path requires the first action to be a witness-aware action; signature and witness enforcement then depends on the Permit2/action call path.

This source review does not prove the complete runtime security invariant. CYDRA has not yet generated and executed paired valid-signature versus unauthorized-signature experiments for this target. No claim of a vulnerability or security pass is made.

## Remaining capability closure

1. Preserve inherited function/modifier provenance in the campaign artifact, not only in internal reasoning.
2. Trace the `executeMetaTxn -> _executeMetaTxn -> _dispatchVIP -> Permit2` path, including witness creation/consumption and signer/payer identity.
3. Add local positive and negative controls: a validly signed witness-aware action must succeed; an invalid signer/signature or unspent witness must fail.
4. Verify the currently eligible deployed revision through the official deployment/registry process before any bounty report.
5. Replay blind and require execution evidence, causal differential, independent reproduction, and impact evidence before declaring readiness.
