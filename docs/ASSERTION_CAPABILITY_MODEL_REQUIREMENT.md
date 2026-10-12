# Assertion-layer requirement: capability delta, not storage delta

Status: **capability-delta implementation milestone; assertion logic is not yet upgraded**.

Tracking regression: [PR #42 — permissionless factory false-positive control](https://github.com/Wonderadroit/Cydra_web3/pull/42).

## Calibration cases

### Negative control: permissionless factory

`PermissionlessFactory.create()` deploys a fresh child and writes `_isChild[child] = true`. The registry entry is factory storage, but its key is the newly created child and the write records that creation. A successful call plus a storage write is not, by itself, evidence that the caller gained authority.

The existing generator emits a security assertion when it cannot find a matching public primitive state getter. That fallback incorrectly treats a successful permissionless factory call as a violation. The regression is marked `pytest.mark.xfail(strict=True)`: the known gap is visible as XFAIL, while an unexpected XPASS fails CI. Remove the marker only after the capability-delta implementation makes this regression pass normally.

### Positive control: unauthorized authority gain

Add a miniature fixture with an already-existing protected resource and a source-grounded access-control relationship. An unrelated caller invokes an unguarded `setTarget`-like operation that grants that caller withdrawal/admin authority over the pre-existing resource. The test must observe that the caller lacked the relevant membership before the call and has it afterward.

The positive control must use a supported authority read, not infer privilege from the call result or arbitrary storage changes. For the first implementation, supported on-chain reads are deliberately limited to:
- Ownable-style `owner()` reads.
- OpenZeppelin AccessControl-style `hasRole(bytes32,address)` reads.

Custom role systems and unsupported access-control surfaces are **unmeasurable/NOT_READY**, not safe by default. Do not pretend the supported interface list is exhaustive.

## Required assertion semantics

A generated experiment must have three explicit phases:

1. **Setup:** deploy/initialize the target and establish any required pre-state.
2. **Baseline observation:** query supported, source-grounded authority relationships for the actor and resource before the call.
3. **Call and post-observation:** execute the planned call, then query the same authority relationships and compare the results.

For the first iteration, the narrow null hypothesis is:

> An unrelated caller that did not hold a supported authority membership before the experiment should not gain that membership over a pre-existing resource as a side effect of the experiment.

This is an observable calibration invariant, not a claim that CYDRA has inferred developer intent or proved every unauthorized access-control change is a vulnerability. Full source-derived invariant discovery remains a separate milestone.

Authority means membership in a resource's access-control relationships, not merely the ability to call a function. Examples include ownership, a recognized role, or another explicitly supported delegation/approval relation. Each observation must identify:
- the actor address;
- the resource address and whether it existed before the call;
- the authority interface and role/relationship being queried;
- the before and after values;
- the call result and any revert data.

The initial implementation supports only the on-chain read interfaces listed above. Reads must be made against the same execution state/block context used by the experiment. If the relevant resource, role identifier, or read interface cannot be established, return an explicit unmeasurable/NOT_READY outcome rather than assuming no authority exists.

## Resource identity and factory boundary

A registry write keyed by a fresh child created during the same call is not itself a privilege gain. The negative control must stay silent because it creates a child and records its address without changing the caller's authority over a pre-existing resource.

Do **not** implement a rule that says new resources are always safe. A factory can create a resource with a dangerous authority configuration, or alter a beacon/implementation's ownership relationship. Those cases require the resource and authority relationship to be observed and assessed; they must not be silently filtered out as safe. The first null-hypothesis control in this milestone specifically measures authority membership changes over pre-existing resources, so authority effects on newly created resources that cannot be classified by the supported model must remain explicit candidates/unmeasurable—not a clean security verdict.

Do not infer trust boundaries from names, storage writes, public visibility, or successful execution alone.

## Required regression behavior

- The permissionless factory negative control passes without a security assertion after capability-delta support lands.
- The positive control detects the caller's new supported authority membership over the pre-existing resource.
- A successful call alone never proves unauthorized privilege gain.
- Unknown/custom authority surfaces fail closed as unmeasurable/NOT_READY, not as safe.
- No blanket factory/new-resource suppression rule is allowed.
- Until both controls pass with execution evidence, do not claim the assertion-layer false positive is fixed.
