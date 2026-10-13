from pathlib import Path

import pytest

from scripts.run_authorization_campaign import _prepare_isolated_foundry_project, _staged_source_import


def test_nested_project_preserves_original_relative_import_layout(tmp_path: Path) -> None:
    project = tmp_path / "target" / "middleware-sdk"
    source = project / "lib" / "core" / "src" / "contracts" / "vault" / "Vault.sol"
    interface = project / "lib" / "core" / "src" / "interfaces" / "common" / "IMigratableEntity.sol"
    source.parent.mkdir(parents=True)
    interface.parent.mkdir(parents=True)
    source.write_text(
        'pragma solidity ^0.8.20; import {IMigratableEntity} from "../../interfaces/common/IMigratableEntity.sol"; contract Vault {}',
        encoding="utf-8",
    )
    interface.write_text("pragma solidity ^0.8.20; interface IMigratableEntity {}\n", encoding="utf-8")
    (project / "foundry.toml").write_text(
        '[profile.default]\n'
        'remappings = ["@core/=lib/core/"]\n'
        'fs_permissions = [{ access = "read-write", path = "./"}]\n'
        'rpc_endpoints = { mainnet = "${RPC}" }\n',
        encoding="utf-8",
    )

    isolated = tmp_path / "isolated"
    _prepare_isolated_foundry_project(project, source, isolated)

    assert (isolated / "lib/core/src/contracts/vault/Vault.sol").is_file()
    assert (isolated / "lib/core/src/interfaces/common/IMigratableEntity.sol").is_file()
    extracted = (isolated / "remappings.txt").read_text(encoding="utf-8").splitlines()
    assert extracted == ["@core/=lib/core/"]


def test_missing_import_fails_closed_with_staging_diagnostic(tmp_path: Path) -> None:
    project = tmp_path / "target"
    source = project / "lib/core/src/contracts/Vault.sol"
    source.parent.mkdir(parents=True)
    source.write_text(
        'pragma solidity ^0.8.20; import "./Missing.sol"; contract Vault {}',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="staging_unsupported: unresolved import closure"):
        _prepare_isolated_foundry_project(project, source, tmp_path / "isolated")


def test_generated_import_resolves_inside_isolated_project(tmp_path: Path) -> None:
    isolated = tmp_path / "isolated"
    source_relative = Path("lib/core/src/contracts/vault/Vault.sol")
    staged_source = isolated / source_relative
    staged_source.parent.mkdir(parents=True)
    staged_source.write_text("pragma solidity ^0.8.20; contract Vault {}\\n", encoding="utf-8")
    test_parent = isolated / "test" / "generated"

    import_path = _staged_source_import(isolated, source_relative, test_parent)

    assert (test_parent / import_path).resolve() == staged_source.resolve()
