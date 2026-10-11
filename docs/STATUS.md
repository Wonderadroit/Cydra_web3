# Migration status

## Repository baseline
- Destination: Wonderadroit/Cydra_web3
- Source repository: Wonderadroit/Cydra_wonder
- Source commit inspected and pinned for migration/control: 99f43987376a327c423ddde2877ce9995564d254
- Current main includes the curated authorization-specialist bootstrap and the helper-mediated state-effect fix.

## Migrated specialist
- Authorization-only doctrine, migration map, file-level provenance manifest, campaign protocol, and binary Definition of Done.
- Core model/parser/compiler-evidence/authorization-reasoning/experiment-generation/Foundry modules.
- Narrow authorization-only investigation entry point and blind campaign runner.
- Positive and protected negative control runners/workflows.
- Manual unfamiliar-target workflow requiring explicit program scope, repository, immutable ref, source path, and causal/reproduction gate.

## Verified evidence
- Initial clean-repository regression: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124081424
- Historical public Decent Bridge positive control: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124120474
  - Known public unguarded setRouter mutation reproduced.
  - Causal guard differential and independent reproduction verified.
  - This is a historical public issue, not a novel discovery.
- Protected negative control: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124212770
  - Executed and classified not_confirmed.
- First blind unfamiliar-target replay: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124305839
  - Zero authorization hypotheses; model failed to surface payable state/helper writes.
- Generic fix merged in PR #3: https://github.com/Wonderadroit/Cydra_web3/pull/3
  - Recognizes address payable state declarations.
  - Propagates writes through same-contract internal call edges with derived-effect evidence.
  - Regression passed: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124536823
- Post-fix blind replay: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124545350
  - Model now shows _changeFeeRecipient and changeFeeRecipient write feeRecipient; the public setter has onlyOwner.
  - Still no authorization hypothesis and no candidate experiment. This is not evidence of safety or a finding; the selected target may simply lack a missing-authorization issue.

## Remaining blocker
The new repository has working positive and negative control loops, but has not yet demonstrated an authorization hypothesis and executed experiment on a distinct unfamiliar target where the authorization failure actually exists. Do not force a candidate or loosen the finding gate to make this target pass.

## Next steps
1. Keep the migrated controls and regression green.
2. Select another currently eligible target or held-out positive control with a real authorization boundary, pin its exact source revision, and keep the expected function hidden.
3. If the candidate is not selected, inspect the model and source evidence before deciding whether the result is a correct negative or a capability gap.
4. Require a meaningful executed experiment, protected negative control, causal differential, independent reproduction, and impact evidence before declaring readiness.


## Additional unfamiliar-target replay — OpenZeppelin ERC7786OpenBridge

- Official scope: https://immunefi.com/bug-bounty/openzeppelin/scope/
- Exact in-scope commit: 0361935dc5edd233adbb9fbae5871ccbb8c739d8
- Campaign: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124629642
- The run selected zero authorization hypotheses and executed zero candidate experiments.
- The model recognized owner-protected administrative methods but missed addGateway/removeGateway writes through EnumerableSet library calls.
- This is NOT_SELECTED / BLOCKED, not a finding and not proof of safety. Full report: docs/campaigns/2026-10-11-openzeppelin-openbridge.md.

The library-mediated storage gap has a generic regression fix in PR #6: qualified state types and common collection mutators are now represented as candidate state effects. The fix is covered by a regression fixture and passed Python regression on run #38124766980.
