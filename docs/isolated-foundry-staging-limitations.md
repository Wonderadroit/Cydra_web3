# Isolated Foundry staging: known limitations

This inventory is evidence-scoped. `untested` means the available campaign artifacts do not establish either success or failure.

| Behavior | Grunt | Symbiotic pinned target | Disposition |
| --- | --- | --- | --- |
| Preserve source-relative imports after staging | Untested | Fail in pre-fix staging | Fixed in PR #46; regression pending |
| Resolve nested-project remappings | Untested | Failure observed / root-config lookup was insufficient | Fixed in PR #46; regression pending |
| Stage required OpenZeppelin package trees | Untested | OpenZeppelin imports unresolved in pre-fix compiler trace | Contracts and contracts-upgradeable paths handled in PR #46; regression pending |
| Validate the full import closure before Foundry | Untested | Diagnostic gap observed | Fail-closed diagnostic added in PR #46; regression pending |
| Emit a structured `STAGING_UNSUPPORTED` disposition | Untested | Diagnostic gap observed | Added in PR #46; regression pending |
| Preserve all original compiler settings beyond remappings | Untested | Not established by this trace | Not in scope |
| Generalize to other monorepo layouts | Untested | Not established by this trace | Not in scope |

The prior Grunt artifacts cited in this audit show a separate abstract-contract `creationCode` failure. They do not establish that the current staging path failed on Grunt, nor do they prove the current implementation stages Grunt correctly. Therefore, all Grunt staging behavior remains `untested`.

Miniature runtime-verdict fixtures are not treated as real-project dependency-layout evidence and are omitted from this matrix.

## Acceptance gate

Run only the pinned Symbiotic target after the PR's regressions pass. Success means `X-H-AUTH-setSlasher` compiles and executes, producing a runtime verdict instead of `UNMEASURABLE`. The verdict may support or reject the hypothesis; neither outcome alone is a bounty finding.
