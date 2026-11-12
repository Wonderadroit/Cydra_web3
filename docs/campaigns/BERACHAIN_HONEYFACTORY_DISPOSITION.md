# Berachain HoneyFactory campaign disposition

## Decision

**Classification: `UNMEASURABLE` — `preconditions_not_established`.**

This is a review disposition for the experiment, not a finding against Berachain and not a claim that the on-chain contract is vulnerable or correctly protected.

## Pinned campaign

- Campaign run: [38708442661](https://github.com/Wonderadroit/Cydra_web3/actions/runs/38708442661)
- Job: [116333689596](https://github.com/Wonderadroit/Cydra_web3/actions/runs/38708442661/job/116333689596)
- CYDRA revision: `54a0a8131b22f6a2407a6ac6bcf3556fad4b6a67`
- Target repository: [berachain/contracts](https://github.com/berachain/contracts)
- Target revision: `70e392fc83deec6a34bd11613f2a446eb6266588`
- Source: [src/honey/HoneyFactory.sol at pinned revision](https://github.com/berachain/contracts/blob/70e392fc83deec6a34bd11613f2a446eb6266588/src/honey/HoneyFactory.sol)
- Candidate: `H-AUTH-setDepegOffsets`

## Why the experiment is unmeasurable

The workflow successfully materialized dependencies, compiled 40 Solidity files, and executed one Foundry test. The test passed, but the test result does not establish that the authorization property was exercised under valid target state.

At the pinned source:
- the implementation constructor calls `_disableInitializers()`;
- `setDepegOffsets` checks `MANAGER_ROLE`;
- it also requires the asset to be registered before writing the offsets.

The campaign harness deployed the contract directly and did not establish proxy initialization, the required manager role, or a registered asset through the target's legitimate setup path. Therefore the call may have reverted because the target was not initialized/configured, rather than because the intended unauthorized-caller guard was tested. A passing assertion under those conditions is not evidence of rejection.

Do not report this as `rejected`, `not_confirmed`, or `supported`. No vulnerability conclusion is justified.

## Artifact limitation

The historical run's artifact contained `target-intake.txt` and `authorization-campaign.log`, but not the generated Solidity test source. The run cannot be retroactively repaired from those files alone. The artifact-preservation change in the associated PR ensures future campaign artifacts include each generated test source alongside the structured JSON execution record and log.

## Follow-up boundary

The general target setup model is tracked separately in [Issue #68](https://github.com/Wonderadroit/Cydra_web3/issues/68). Do not implement a general precondition solver in this artifact-preservation cycle. For the next live campaign, select a target in the already-supported class: standalone deployment, direct caller-based authorization, a single privileged state-changing function, and no required proxy initialization, role setup, or asset registration. DcntEth remains a historical positive control, not a live bounty finding.
