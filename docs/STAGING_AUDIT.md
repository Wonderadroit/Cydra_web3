# Isolated Foundry Staging Audit

Date: 2026-10-15  
Scope: `scripts/run_authorization_campaign.py`, especially target dependency preparation and `_prepare_isolated_foundry_project()`.

## Security invariant

Target package-manager lifecycle scripts must not execute in CI. Dependency installation always passes `--ignore-scripts`. The campaign only needs dependency source files for local compilation and test execution; it does not need target-defined install hooks. A failed or ambiguous install is recorded as `BLOCKED` and the campaign records `UNMEASURABLE`, never as a target verdict.

## Path-construction and dependency-assumption inventory

| Site | Assumption / risk | Audit disposition |
|---|---|---|
| Git clone, checkout, and `project = checkout / target_project` | Project path is repository-relative and source is resolved from the immutable checkout. | Keep; target intake validation runs before campaign. |
| `_materialize_target_dependencies(project)` | A manifest can declare packages absent from a fresh clone; multiple lockfile families can conflict; unpinned install is less reproducible. | Install based on lockfile; reject conflicting manager lockfiles; use manager-specific frozen/immutable flags; record manager, lockfile, command, output, and confidence. Without a lockfile, use `npm install --ignore-scripts` and explicitly mark lower confidence. |
| `source_root = next(source.parents ... src/contracts)` | Source-root detection assumes a conventional Solidity source directory. | Keep bounded and tested against root-level source files under `src/`; unusual source layouts remain a visible limitation rather than silently guessed. |
| `current.relative_to(source_root)` then `src_root / relative` | Files inside the selected source root are staged preserving relative structure. | Covered by the relative-import and nested-library fixtures. |
| Fallback `current.relative_to(target_root)` | Dependency files must belong to the pinned checkout; paths outside it must not be silently copied. | Keep strict `relative_to` failure; npm paths stage at isolated root, other checkout dependencies under isolated `src/`. |
| Relative import resolution `current.parent / imported` | Relative imports are resolved against the original source file, not the relocated staged path. | Covered by relative-import and nested-library fixtures. |
| `contracts/` imports resolved from `target_root` | Legacy project-root import prefix is repository-relative. | Keep; closure traversal copies only existing files and leaves unresolved imports for compiler evidence. |
| Import resolution | Use the ordered rule: importer-relative → explicit remapping (longest prefix) → `node_modules/<spec>` → `<project_root>/<spec>` → unresolved import key. | Each successful non-relative fallback creates a remapping to the staged location; ambiguous generated prefixes fail closed. |
| Generated `foundry.toml` remappings | npm destinations must not receive a second `node_modules/`; other target-root dependencies are staged under `src/`. | Covered by npm, mixed-layout, and no-remappings npm fixtures; assert duplicate prefix absent and fallback remapping is generated. |
| Generated `test/generated` and `test_path_for(...)` | Generated test path is isolated-project-relative and must not overwrite target source. | Keep; generated tests remain under isolated `test/generated`. |
| `source_relative = Path(source).relative_to(source_root)` | Causal-control patch path must match the staged source path. | Keep and cover source-root-relative staging layouts; failure remains an explicit unmeasurable outcome. |
| Legacy `--target-npm-dependency` and OpenZeppelin-only copy/remapping | Per-package override bypassed manifest/lockfile selection and added target-specific behavior. | Removed; all npm dependency staging is driven by the target manifest and lockfile. |

## Six integration layouts

1. **Local `lib/`** — remapped local submodule staged under `src/lib/`.
2. **Nested `lib/`** — nested dependency remapping and internal relative import.
3. **Relative imports** — source and sibling import preserve source-root-relative structure.
4. **npm package** — package declared in manifest, lockfile present, no initial `node_modules`; package-manager invocation is asserted to include `--ignore-scripts`.
5. **Mixed npm + `lib/`** — both dependency classes resolve in the same isolated project.\n6. **npm without remappings** — scoped package import resolves through `node_modules/<spec>` and receives an automatically generated remapping.

The integration test runs `forge build` for each fixture when Foundry is installed (CI installs Foundry). Package-manager invocation tests cover npm, pnpm, Yarn classic, Bun, and the no-lockfile npm fallback without network access.

## Remaining bounded limitations

- No-lockfile installation is inherently lower confidence; the artifact records this explicitly.
- Conflicting lockfiles are blocked rather than guessed.
- pnpm/Yarn/Bun lockfiles require their respective package manager (or Corepack for pnpm/Yarn) to be available; CYDRA does not silently switch managers.
- Dependency install is network-dependent and time-bounded. Package installation is not proof of target behavior.
- A successful build is not a finding. The pinned campaign still must execute at least one test and preserve its output before the candidate can be classified.
