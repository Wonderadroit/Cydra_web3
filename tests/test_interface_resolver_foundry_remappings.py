from pathlib import Path

from cydra.interface_resolver import resolve_import


def test_foundry_import_resolution_supports_remappings_and_library_inference(tmp_path: Path) -> None:
    project = tmp_path / "project"
    importer = project / "src" / "Vault.sol"
    package = project / "lib" / "openzeppelin-contracts" / "contracts" / "token"
    importer.parent.mkdir(parents=True)
    package.mkdir(parents=True)
    importer.write_text('import "@openzeppelin/contracts/token/IERC20.sol";\n', encoding="utf-8")
    dependency_file = package / "IERC20.sol"
    dependency_file.write_text("interface IERC20 {}\n", encoding="utf-8")

    # Explicit remappings.txt is applied before filesystem fallbacks.
    (project / "remappings.txt").write_text(
        "@openzeppelin/=lib/openzeppelin-contracts/\n", encoding="utf-8"
    )
    resolved = resolve_import(
        project, importer, "@openzeppelin/contracts/token/IERC20.sol"
    )
    assert resolved == (dependency_file, "remapping")

    # foundry.toml remappings work when remappings.txt is absent.
    (project / "remappings.txt").unlink()
    (project / "foundry.toml").write_text(
        '[profile.default]\nremappings = ["@openzeppelin/=lib/openzeppelin-contracts/"]\n',
        encoding="utf-8",
    )
    resolved = resolve_import(
        project, importer, "@openzeppelin/contracts/token/IERC20.sol"
    )
    assert resolved == (dependency_file, "remapping")

    # Foundry's common library layout is a final fallback when no explicit map exists.
    (project / "foundry.toml").unlink()
    resolved = resolve_import(
        project, importer, "@openzeppelin/contracts/token/IERC20.sol"
    )
    assert resolved == (dependency_file, "foundry_library_inference")
