# Migration status

## Repository baseline
- Destination: Wonderadroit/Cydra_web3
- Source repository: Wonderadroit/Cydra_wonder
- Source commit inspected and pinned for migration/control: 99f43987376a327c423ddde2877ce9995564d254
- Main contains the curated authorization-specialist bootstrap and the generic helper-mediated state-effect fix.

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
  - Zero authorization hypotheses; the initial model failed to surface payable state/helper writes.
- Generic fix merged in PR #3: https://github.com/Wonderadroit/Cydra_web3/pull/3
  - Recognizes address payable state declarations.
  - Propagates writes through same-contract internal call edges with derived-effect evidence.
  - Regression passed: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124536823
- Post-fix Vaults Splitter replay: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124545350
  - The model now shows _changeFeeRecipient and changeFeeRecipient write feeRecipient; the public setter has onlyOwner.
  - Still no authorization hypothesis and no candidate experiment. This target may simply lack a missing-authorization issue.
- Blind OpenZeppelin ERC7786OpenBridge replay: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124629642
  - Official scope pins this asset to commit 0361935dc5edd233adbb9fbae5871ccbb8c739d8.
  - The model surfaced owner-protected admin methods but did not model addGateway/removeGateway writes through EnumerableSet library calls.
  - No hypothesis and no experiment; no vulnerability finding.

## Remaining blocker
The new repository has working positive and negative control loops, but has not yet demonstrated a hypothesis and executed experiment on a distinct unfamiliar target where the authorization failure actually exists. The latest target failures reveal that helper propagation is now improved, but storage mutations performed through library methods remain incompletely modeled. Do not force a candidate or loosen the finding gate to make a target pass.

## Next steps
1. Keep the migrated controls and regression green.
2. Improve generic modeling of storage-reference/library mutation (for example, EnumerableSet.add/remove), with source-linked provenance and negative controls.
3. Select another currently eligible target or held-out positive control with an authorization boundary, pin its exact source revision, and keep the expected function hidden.
4. If the candidate is not selected, inspect the model and source evidence before deciding whether the result is a correct negative or a capability gap.
5. Require a meaningful executed experiment, protected negative control, causal differential, independent reproduction, and impact evidence before declaring readiness.
