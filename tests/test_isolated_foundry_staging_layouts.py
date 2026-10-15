from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.run_authorization_campaign import (
    _materialize_target_dependencies,
    _prepare_isolated_foundry_project,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


LAYOUTS = [
    pytest.param(
        "local-lib",
        'import "forge-std/Test.sol";',
        "forge-std/=lib/forge-std/src/\n",
        {
            "lib/forge-std/src/Test.sol":
                "pragma solidity ^0.8.20; library Test { function value() internal pure returns (uint256) { return 1; } }",
        },
        ["src/lib/forge-std/src/Test.sol"],
        id="local-lib",
    ),
    pytest.param(
        "nested-lib",
        'import "nested/Child.sol";',
        "nested/=lib/vendor/nested/src/\n",
        {
            "lib/vendor/nested/src/Child.sol":
                'pragma solidity ^0.8.20; import "./Base.sol"; contract Child is Base {}',
            "lib/vendor/nested/src/Base.sol":
                "pragma solidity ^0.8.20; contract Base { function value() public pure returns (uint256) { return 2; } }",
        },
        ["src/lib/vendor/nested/src/Child.sol", "src/lib/vendor/nested/src/Base.sol"],
        id="nested-lib",
    ),
    pytest.param(
        "relative-imports",
        'import "./Sibling.sol";',
        "",
        {
            "src/module/Sibling.sol":
                "pragma solidity ^0.8.20; contract Sibling { function value() public pure returns (uint256) { return 3; } }",
        },
        ["src/module/Sibling.sol"],
        id="relative-imports",
    ),
    pytest.param(
        "npm-package",
        'import "@openzeppelin/contracts/access/AccessControl.sol";',
        "@openzeppelin/=node_modules/@openzeppelin/\n",
        {
            "node_modules/@openzeppelin/contracts/access/AccessControl.sol":
                "pragma solidity ^0.8.20; contract AccessControl {}",
        },
        ["node_modules/@openzeppelin/contracts/access/AccessControl.sol"],
        id="npm-package",
    ),
    pytest.param(
        "mixed-npm-and-lib",
        'import "forge-std/Test.sol"; import "@openzeppelin/contracts/access/AccessControl.sol";',
        "forge-std/=lib/forge-std/src/\n@openzeppelin/=node_modules/@openzeppelin/\n",
        {
            "lib/forge-std/src/Test.sol":
                "pragma solidity ^0.8.20; library Test { function value() internal pure returns (uint256) { return 4; } }",
            "node_modules/@openzeppelin/contracts/access/AccessControl.sol":
                "pragma solidity ^0.8.20; contract AccessControl {}",
        },
        [
            "src/lib/forge-std/src/Test.sol",
            "node_modules/@openzeppelin/contracts/access/AccessControl.sol",
        ],
        id="mixed-npm-and-lib",
    ),
]


@pytest.mark.parametrize(
    ("layout", "imports", "remappings", "dependencies", "expected_paths"),
    LAYOUTS,
)
def test_isolated_foundry_staging_supports_five_dependency_layouts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    layout: str,
    imports: str,
    remappings: str,
    dependencies: dict[str, str],
    expected_paths: list[str],
) -> None:
    target = tmp_path / layout
    source_relative = Path("src/module/Entry.sol") if layout == "relative-imports" else Path("src/Entry.sol")
    source = target / source_relative
    _write(
        source,
        "pragma solidity ^0.8.20; "
        + imports
        + " contract Entry { function value() external pure returns (uint256) { return 1; } }",
    )
    _write(target / "remappings.txt", remappings)
    for relative, content in dependencies.items():
        # npm files must be absent until the simulated lockfile install runs.
        if relative.startswith("node_modules/") and layout in {"npm-package", "mixed-npm-and-lib"}:
            continue
        _write(target / relative, content)

    if layout in {"npm-package", "mixed-npm-and-lib"}:
        # The important regression: the pinned checkout has a manifest and
        # lockfile but no node_modules directory. Simulate the package manager
        # resolving package contents; do not perform network I/O in unit tests.
        _write(
            target / "package.json",
            json.dumps({"name": "staging-fixture", "dependencies": {"@openzeppelin/contracts": "5.1.0"}}),
        )
        _write(
            target / "package-lock.json",
            json.dumps({"name": "staging-fixture", "lockfileVersion": 3, "requires": True, "packages": {}}),
        )
        assert not (target / "node_modules").exists()
        original_run = subprocess.run
        observed_commands: list[list[str]] = []

        def fake_run(command, *args, **kwargs):
            command_list = [str(item) for item in command]
            if command_list and command_list[0].endswith("npm") and "ci" in command_list:
                observed_commands.append(command_list)
                assert "--ignore-scripts" in command_list
                _write(
                    target / "node_modules/@openzeppelin/contracts/access/AccessControl.sol",
                    "pragma solidity ^0.8.20; contract AccessControl {}",
                )
                return subprocess.CompletedProcess(command_list, 0, "installed fixture", "")
            return original_run(command, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", fake_run)
        materialized = _materialize_target_dependencies(target)
        assert materialized["status"] == "INSTALLED"
        assert materialized["package_manager"] == "npm"
        assert materialized["lockfile"] == "package-lock.json"
        assert materialized["confidence"] == "lockfile_pinned"
        assert materialized["lifecycle_scripts_disabled"] is True
        assert observed_commands and observed_commands[0][1:3] == ["ci", "--ignore-scripts"]
        monkeypatch.setattr(subprocess, "run", original_run)

    isolated = tmp_path / f"{layout}-isolated"
    _prepare_isolated_foundry_project(target, source, isolated)

    for relative in expected_paths:
        assert (isolated / relative).is_file(), f"{layout}: missing staged dependency {relative}"

    foundry_config = (isolated / "foundry.toml").read_text(encoding="utf-8")
    assert "node_modules/node_modules/" not in foundry_config
    if "node_modules/@openzeppelin/" in remappings:
        assert "@openzeppelin/=node_modules/@openzeppelin/" in foundry_config
        assert "@openzeppelin/=node_modules/node_modules/" not in foundry_config

    # CI installs Foundry for the regression job. Local Python-only runs still
    # validate paths and dependency preparation without requiring Foundry.
    if shutil.which("forge"):
        completed = subprocess.run(
            ["forge", "build"],
            cwd=isolated,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, (
            f"{layout} isolated project failed forge build\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )


@pytest.mark.parametrize(
    ("lockfile", "manager", "expected_fragment", "confidence"),
    [
        ("package-lock.json", "npm", ["ci", "--ignore-scripts"], "lockfile_pinned"),
        ("pnpm-lock.yaml", "pnpm", ["install", "--ignore-scripts", "--frozen-lockfile"], "lockfile_pinned"),
        ("yarn.lock", "yarn", ["install", "--ignore-scripts", "--frozen-lockfile"], "lockfile_pinned"),
        ("bun.lock", "bun", ["install", "--ignore-scripts", "--frozen-lockfile"], "lockfile_pinned"),
        (None, "npm", ["install", "--ignore-scripts"], "manifest_unlocked_lower_confidence"),
    ],
    ids=["npm-ci", "pnpm-frozen", "yarn-classic-frozen", "bun-frozen", "no-lockfile-lower-confidence"],
)
def test_dependency_materialization_is_lockfile_aware_and_disables_scripts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lockfile: str | None,
    manager: str,
    expected_fragment: list[str],
    confidence: str,
) -> None:
    project = tmp_path / manager
    project.mkdir()
    _write(
        project / "package.json",
        json.dumps({"name": "fixture", "dependencies": {"example-solidity-package": "1.2.3"}}),
    )
    if lockfile:
        _write(project / lockfile, "fixture lockfile\n")

    real_which = shutil.which

    def fake_which(name: str):
        if name in {"npm", "pnpm", "yarn", "bun", "corepack"}:
            return f"/usr/bin/{name}"
        return real_which(name)

    monkeypatch.setattr(shutil, "which", fake_which)
    observed: list[list[str]] = []

    def fake_run(command, *args, **kwargs):
        command_list = [str(item) for item in command]
        if command_list[-1:] == ["--version"]:
            return subprocess.CompletedProcess(command_list, 0, "1.22.22\n", "")
        observed.append(command_list)
        return subprocess.CompletedProcess(command_list, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _materialize_target_dependencies(project)

    assert result["status"] == "INSTALLED"
    assert result["package_manager"] == manager
    assert result["confidence"] == confidence
    assert result["lifecycle_scripts_disabled"] is True
    assert "--ignore-scripts" in result["command"]
    assert any(all(part in command for part in expected_fragment) for command in observed)
    if lockfile:
        assert result["lockfile"] == lockfile
    else:
        assert result["lockfile"] is None
