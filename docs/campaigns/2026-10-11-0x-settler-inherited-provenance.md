# Held-out 0x Settler replay with inherited provenance

- Workflow: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38144714579
- Artifact: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38144714579/artifacts/11703689549
- Workflow head: `b50745c3b94a58d18b18bc07e1413ca90fe2a4a1`
- Target: `https://github.com/0xProject/0x-settler`
- Pinned source: `872b0e4cc83cce6a75eb4a1705f5bfd06e21a6c5`
- Entry source: `src/chains/Mainnet/Intent.sol`
- Execution was local source analysis only; no on-chain transactions were sent.

## Outcome

Workflow completed successfully. The security campaign did **not** reach finding readiness:
- Compiler status: `no_ast_for_source`, version `0.8.33`.
- The artifact now records `executeMetaTxn` with effective modifiers `onlySolver` and `metaTx`, while declared modifiers are empty.
- Its modifier provenance is recorded as `inherited_super_dispatch`.
- Inherited function coverage includes `setSolver` with `onlyOwner`, plus the base declarations of `executeMetaTxn`.
- Semantic state effects: 0.
- Authorization hypotheses: 0.
- Candidate experiments: 0.
- Classification: `NO_AUTH_HYPOTHESIS`; disposition: `BLOCKED`; finding gate: `NOT_READY`; blocker: `NO_SUPPORTED_HYPOTHESIS`.

This result demonstrates that the newly added artifact fields expose useful inherited modifier/source evidence. It does **not** prove the complete signature/witness chain, validate runtime authorization, establish the target is secure, or constitute a vulnerability finding. The target's `executeMetaTxn` path is primarily signature/caller/witness/action authorization, while this specialist's current finding logic is centered on modeled privileged state writes. Zero hypotheses here is a capability mismatch, not a negative security verdict.

## Next capability closure

1. Stop treating `no_ast_for_source` as a sufficient compiler diagnostic; distinguish absent AST from a successful parse with no supported extracted relations.
2. Add an execution-capable local test harness for the inherited meta-transaction boundary, with paired valid-signature and invalid-signature/witness cases.
3. Preserve caller, declared signer, effective payer, witness digest, and action-dispatch provenance in experiment evidence.
4. Only generate a security hypothesis when the source-derived call path and a testable authorization invariant are supported.
5. Confirm the current eligible deployment/revision before any program report.

No finding is claimed. The successful workflow only proves the analysis ran and produced an explicit NOT_READY result.
