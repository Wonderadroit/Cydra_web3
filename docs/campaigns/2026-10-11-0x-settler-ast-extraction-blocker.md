# 2026-10-11 — Held-out 0x Settler AST extraction blocker

- Workflow: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38145498436
- Artifact: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38145498436/artifacts/11704965659
- Campaign branch: `campaigns/held-out-0x-settler-ast-status`
- Target repository: https://github.com/0xProject/0x-settler
- Pinned source revision: `872b0e4cc83cce6a75eb4a1705f5bfd06e21a6c5`
- Entry source: `src/chains/Mainnet/Intent.sol`

## Result

The replay completed successfully and the new compiler diagnostics resolved the previous ambiguity:

- Compiler ran successfully with solc `0.8.33`.
- One build-info file was produced.
- One matching source entry was found.
- The matching source has an AST.
- Status: `ast_present_no_supported_evidence`.
- Extracted semantic relationships: `0`.
- Extracted parameter constraints: `0`.
- Authorization hypotheses: `0`.
- Candidate experiments: `0`.
- Classification: `NO_AUTH_HYPOTHESIS`.
- Disposition: `BLOCKED`.
- Finding gate: `NOT_READY`.

The artifact also retains inherited authorization provenance: `executeMetaTxn` has effective modifiers `onlySolver` and `metaTx` through inherited super dispatch, and inherited `setSolver` is marked `onlyOwner`. These are model observations, not proof that the full authorization path is correct or vulnerable.

## Stage assessment

The AST-presence diagnostic milestone is complete. The next blocker is not missing compiler output: CYDRA has a matching compiler AST but its current extractors recognize no supported semantic relationships or parameter constraints in this source. This is an extraction/model-coverage gap and must be investigated before adding a hypothesis generator.

The Settler entry path is primarily a meta-transaction signature/caller/witness/action-dispatch boundary. A useful next milestone is to model that boundary explicitly and execute paired valid-signature versus invalid-signature/witness controls locally against the pinned source. The harness must preserve caller, signer, payer, witness/digest and action-dispatch provenance. It must not fabricate signature inputs or turn a failed precondition into a finding.

## Definition of done for the next step

1. Add a small deterministic fixture from the target's actual Solidity AST and demonstrate which node types/relationships the current extractor misses.
2. Extend extraction generically, with unit tests for supported node types and a no-evidence fixture that remains explicit.
3. Re-run the held-out pinned campaign and inspect the artifact.
4. Only then build the paired signature/witness execution harness; finding readiness requires a reproducible unauthorized behavior, a causal authorization-control differential, and independent reproduction.

No vulnerability is claimed. Successful CI proves the campaign executed and recorded its blocker; it does not establish that the target is secure.
