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


## OpenBridge replay after library-state fix
- Run: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124905344
- After PR #6, the model surfaced addGateway/removeGateway writes to _gateways and retained the existing _threshold/_remotes writes.
- The administrative functions were owner-protected, so the run still selected no authorization hypothesis and executed no candidate experiment.
- This is an expected no-candidate result for the visible administrative surface, not a finding and not proof of full target safety.
- Report: docs/campaigns/2026-10-11-openbridge-after-library-effects.md.

## Current readiness
The parser now models direct writes, same-contract helper-mediated writes, payable state declarations, and common collection mutators on qualified state types. Positive and negative controls pass. The specialist still has not demonstrated a novel or held-out unfamiliar-target authorization finding; the next milestone is a held-out positive control or a currently eligible target with a genuine authorization boundary failure, tested blind.


## Campaign intake hardening — 2026-10-11

- PR #10 merged: https://github.com/Wonderadroit/Cydra_web3/pull/10
- Main commit: 40908f806392aece517d7228e66ade028aae84ed
- Python Regression passed on PR head: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38126024438
- Authorization Specialist workflow's Python regression passed: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38126024415
- Added input-format checks for HTTPS URLs, canonical GitHub owner/repository URLs, full 40-character commit SHAs, and safe relative paths.
- The manual campaign workflow now runs this validation before target analysis.
- Scope caveat is explicit: syntax validation does not independently establish that a repository, source path, or deployed revision is covered by a bounty program.

## Held-out 0x Settler campaign — measured, blocked

- Workflow: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38126115013
- Report: docs/campaigns/2026-10-11-0x-settler-heldout.md
- The workflow completed and uploaded an artifact. It selected zero authorization hypotheses and executed zero candidate experiments.
- Disposition is BLOCKED / NOT_READY, not a finding and not a security pass.
- The model only evidenced the entry contract's local functions; inherited meta-transaction execution and downstream external-effect authorization were not validated.
- The pinned commit was observed in a public Settler GitCommit event, but the current eligible deployed revision must be verified before bounty reporting.
- Next capability closure: trace inherited function and caller/signer authorization through the meta-transaction path, with local positive/negative signature controls.


## Inherited-super authorization modeling and Settler replay — 2026-10-11

- PR #13 merged: https://github.com/Wonderadroit/Cydra_web3/pull/13
- Merge commit: `fe405c3974936aa58c0a3f3456c59d5321374586`
- Python Regression passed: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38144206754
- Authorization Specialist regression passed: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38144206779
- Added paired tests for inherited modifiers on explicit `super.<function>(...)` dispatch and for an unguarded override that does not dispatch to `super`.
- Post-change held-out Settler replay: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38144275019
- Replay artifact: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38144275019/artifacts/11704470406
- The replay still produced zero authorization hypotheses and zero candidate experiments; disposition remains BLOCKED / NOT_READY. The target-level campaign artifact does not yet expose effective inherited modifier provenance or the downstream Permit2 witness/signature path.
- Source-path review indicates `executeMetaTxn` dispatches through inherited meta-transaction logic and a witness-aware Permit2 action. This is static context only, not an independently executed security proof.
- Full report: `docs/campaigns/2026-10-11-0x-settler-post-super.md`.
- Next capability closure: inherited provenance in artifacts; end-to-end signer/payer/witness call-path modeling; paired valid/invalid signature execution controls. No finding or security pass is claimed.


## Campaign artifact inheritance provenance — 2026-10-11

- PR #15 merged: https://github.com/Wonderadroit/Cydra_web3/pull/15
- Merge commit: `c7137fc74542a7d6c80d67ff722826b5ca822858`
- Python Regression passed on the merged change's head: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38144670120
- Authorization Specialist regression passed on the merged change's head: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38144670119
- Campaign artifacts now include inherited public/external function coverage, declaring-source paths, and declared versus effective modifier provenance. A regression verifies that explicit super dispatch can expose inherited modifier evidence without fabricating a hypothesis.
- Post-change held-out replay is running: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38144714579
- The prior replay remained BLOCKED / NOT_READY with zero hypotheses and zero candidate experiments. The provenance replay must be inspected before claiming this gap is closed.


## Settler inherited-provenance replay completed — 2026-10-11

- Replay workflow completed successfully: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38144714579
- Artifact: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38144714579/artifacts/11703689549
- The artifact now shows `executeMetaTxn` with effective modifiers `onlySolver` and `metaTx`, declared modifiers empty, and inherited provenance. It also exposes inherited `setSolver` protected by `onlyOwner`.
- Campaign result remains `NO_AUTH_HYPOTHESIS`, `BLOCKED`, `NOT_READY`; zero semantic state effects, zero hypotheses, and zero candidate experiments.
- This is an observability improvement, not a security pass or vulnerability finding. The compiler status remains ambiguous (`no_ast_for_source`), and no paired signature/witness execution has been run.
- Full report: `docs/campaigns/2026-10-11-0x-settler-inherited-provenance.md`.
- Next: clarify compiler/AST status and add local paired valid/invalid signature-witness execution tests before trying to claim the inherited meta-transaction authorization boundary is covered.


## Symbiotic isolated-staging validation — 2026-10-13

- Pull request: https://github.com/Wonderadroit/Cydra_web3/pull/46
- Pinned target: `sherlock-audit/2025-06-symbiotic-relay@435a21fd81bcd588439feef3108580f535b9e5eb`
- Source: `middleware-sdk/lib/core/src/contracts/vault/Vault.sol`
- Workflow run: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38371729717
- Artifact: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38371729717/artifacts/11799875469
- Result: target checkout and nested submodules were staged; Foundry compilation succeeded; the generated test executed (1 passed, 0 failed); the harness emitted `CYDRA_VERDICT 4` with `no_authority_getter`; campaign exited 2 because the result was unmeasurable/not ready and `REQUIRE_READY=true`.
- Artifact audit: the uploaded ZIP contains `authorization-campaign.log` and `target-intake.txt`; it does **not** contain `authorization-campaign.json`. The log independently records compilation/execution and the unmeasurable verdict, but the structured JSON output was not included in the uploaded artifact. Treat that as an artifact-packaging/observability gap, not evidence that the staging fix failed.
- Candidate binding remains a separate issue: the run generated `H-AUTH-claim`, not the requested `X-H-AUTH-setSlasher`. Track only in Issue #47: https://github.com/Wonderadroit/Cydra_web3/issues/47. Do not change candidate selection in the staging-fix cycle.
- `no_authority_getter` is not diagnostic evidence about `setSlasher`, because the executed candidate was `claim`. Defer that interpretation until the candidate-binding defect is fixed and the intended function is tested.
- No finding, security pass, or authorization-bypass reproduction is claimed.
