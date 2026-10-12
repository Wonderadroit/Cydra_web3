# TransferGuardFactory authorization boundary test

Date: 2026-10-12

## Pinned target

- Repository: `https://github.com/3FLabs/grunt`
- Commit: `96a18e376e8f95bbb243a774609945749d3a0b3e`
- Source: `src/guard/TransferGuardFactory.sol` and `src/guard/TransferGuard.sol`
- Execution: disposable checkout; local Foundry tests only; no live transactions; no target-repository changes.

## Test evidence

- Workflow: `https://github.com/Wonderadroit/Cydra_web3/actions/runs/38287311636`
- Compiler: Solidity 0.8.34
- Result: 4 passed, 0 failed, 0 skipped.

Boundary outcomes:

1. A creator can administer a guard when the creator is the declared owner.
2. When a guard is owned by Alice, both the creator and a separate unrelated caller are rejected from owner-only configuration; Alice succeeds.
3. An unrelated caller cannot upgrade the factory beacon; the configured beacon owner can.
4. Creating a second guard does not change the first guard's owner, token configuration, or address status.

## Verdict

**REJECTED — the original authorization assertion was not reproduced as a privilege-boundary violation.** The factory's public creation path and `_isTransferGuard[transferGuard] = true` registry write are consistent with permissionless creation of a fresh proxy. The caller does not gain authority over a guard owned by another actor or over the beacon's upgrade path.

This test supports rejection of this specific assertion; it is not a universal proof that the factory or all of its deployment configurations are secure. CYDRA's assertion logic is unchanged. The separate permissionless-factory negative control documents the remaining generic capability-modeling gap.
