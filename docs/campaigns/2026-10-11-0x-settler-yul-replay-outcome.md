# 2026-10-11 — Held-out 0x Settler replay after inherited AST and Yul extraction

## Revisions and workflow evidence

- Target repository: https://github.com/0xProject/0x-settler
- Pinned target revision: `872b0e4cc83cce6a75eb4a1705f5bfd06e21a6c5`
- Entry source: `src/chains/Mainnet/Intent.sol`
- Inherited-source AST extraction merged in PR #20: https://github.com/Wonderadroit/Cydra_web3/pull/20
- Lvalue/constant/Yul extraction fix merged in PR #21: https://github.com/Wonderadroit/Cydra_web3/pull/21
- Held-out replay: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38147300726
- Replay artifact: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38147300726/artifacts/11704809176

## Verified campaign result

- Compiler executed successfully; compiler version `0.8.33`.
- One build-info file; the requested source was matched and had an AST.
- 22 semantic relationships extracted.
- 8 parameter constraints extracted.
- The emitted semantic state effects comprise 14 Yul storage reads and 8 Yul storage writes.
- Each Yul effect preserves its source path, function, operation, source location and slot expression. Slot expressions are explicitly marked non-comparable because the current extractor does not resolve their runtime storage-slot equivalence.
- Authorization hypotheses: 0.
- Candidate experiments: 0.
- Classification: `NO_AUTH_HYPOTHESIS`.
- Disposition: `BLOCKED`.
- Finding gate: `NOT_READY`.

The replay proves that inherited AST extraction and basic Yul storage-operation extraction now execute against the pinned source. It does not prove the target is secure. Zero hypotheses remains a capability gap until the relevant authorization boundary is modeled and tested.

## Regression controls

- Historical Decent Bridge positive control, pinned at `7f90fd4489551b69c20d11eeecb17a3f564afb18`: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38147414434
  - The previously reported `setRouter` authorization defect remains detected.
  - The unpatched execution fails the security assertion, the causal authorization-control patch passes, and independent reproduction reproduces the same differential.
  - Classification is `confirmed` and finding gate `READY`, but this is a known historical public issue—not a novel bounty finding.
- Protected negative control: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38147419820
  - `setWhitelist` remains `not_confirmed`; the control passed.
- Python Regression and Authorization Specialist CI passed after the Yul/lvalue change: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38147243716 and https://github.com/Wonderadroit/Cydra_web3/actions/runs/38147243664.

## Next milestone: authorization boundary execution

The Settler entry point delegates into inherited `executeMetaTxn` behavior. Its relevant boundary includes the effective `onlySolver` and `metaTx` modifiers, the signer/payer context, the Permit2 witness binding, and the requirement that the witness is consumed by the first witness-aware action.

The next campaign must test this boundary with deterministic local paired controls:

1. A valid signer/witness/action tuple must execute as expected.
2. A modified signature or witness must revert before the protected action has an effect.
3. An unapproved solver/caller must be rejected independently of signer validity.
4. A replayed witness must fail after the first successful use.
5. Any suspected bypass must be reproduced on the unpatched pinned source, disappear under a minimal causal control, and be independently reproduced.

This should use the target's pinned local test fixtures or equivalent deterministic fixtures, not invented signatures, guessed state, or live transactions. Until those tests are run and artifacts inspected, no Settler vulnerability is claimed.
