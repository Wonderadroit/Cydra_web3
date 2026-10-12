# Assertion-layer requirement: capability delta, not storage delta

Status: **next milestone; requirement recorded, implementation intentionally deferred**.

## Calibration case

`PermissionlessFactory.create()` deploys a fresh child and writes `_isChild[child] = true`. The registry entry is factory storage, but its key is the newly created child and the write records that creation. A successful call plus a storage write is not, by itself, evidence that the caller gained a privilege.

The current generated assertion treats a successful call to a function without a public primitive state getter as a security violation. The permissionless-factory negative-control regression reproduces that behavior and is expected to fail until the assertion model is upgraded.

## Required assertion semantics

Before a candidate can be promoted to a supported authorization judgment, the assertion layer must model and compare:

1. **Actor capability before the call** — what operations/resources the actor could control before execution.
2. **Actor capability after the call** — what operations/resources the actor can control after execution.
3. **Resource identity and existence** — whether the affected resource existed before the call or was created by the call.
4. **Authority delta** — whether the actor gained an unauthorized capability over a pre-existing resource, or another independently established protected boundary was crossed.

A registry write keyed by a fresh resource created during the same call must not count as a privilege gain unless separate evidence demonstrates an unauthorized capability change. Do not infer trust boundaries from names, storage writes, public visibility, or successful execution alone.

## Required regression behavior

- The permissionless factory fixture must not receive a supported/confirmed authorization judgment merely because `create()` succeeds and appends its fresh child to the registry.
- A real unauthorized capability gain against a pre-existing resource must remain detectable; this negative control must not become a blanket rule that factories are safe.
- Keep assertion logic unchanged in the current calibration cycle. First retain the failing negative control as evidence of the gap; implement capability-delta modeling as a separate, measured milestone.
