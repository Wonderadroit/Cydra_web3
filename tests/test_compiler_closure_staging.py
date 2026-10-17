from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.run_authorization_campaign import _prepare_isolated_foundry_project


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_compiler_closure_stages_nested_package_and_generated_test(tmp_path: Path) -> None:
    target = tmp_path / "target"
    entry = target / "src" / "Entry.sol"
    access = target / "node_modules" / "@openzeppelin" / "contracts" / "access" / "AccessControl.sol"
    _write(
        entry,
        'pragma solidity ^0.8.20; import "@openzeppelin/contracts/access/AccessControl.sol"; contract Entry is AccessControl {}',
    )
    _write(access, "pragma solidity ^0.8.20; abstract contract AccessControl {}")
    # Deliberately no remappings.txt: the compiler has already resolved the
    # source-unit keys and their physical paths.
    closure = {
        "src/Entry.sol": entry,
        "@openzeppelin/contracts/access/AccessControl.sol": access,
    }
    isolated = tmp_path / "isolated"
    test_root = _prepare_isolated_foundry_project(
        target, closure, isolated, required_keys=("src/Entry.sol",)
    )

    # 1. Every compiler-closure file is copied at its exact source-unit key.
    assert (isolated / "src/Entry.sol").is_file()
    assert (isolated / "@openzeppelin/contracts/access/AccessControl.sol").is_file()

    # 2. Any generated remapping resolves to a path present in the isolated root.
    remappings = (isolated / "remappings.txt").read_text(encoding="utf-8").splitlines()
    for line in remappings:
        prefix, destination = line.split("=", 1)
        assert any(
            path.is_file()
            for path in isolated.glob(destination.rstrip("/") + "/**/*")
        ) or (isolated / destination.rstrip("/")).is_file(), (prefix, destination)

    # The generated test imports the staged target using its exact staged path.
    _write(
        test_root / "ClosureStaging.t.sol",
        'pragma solidity ^0.8.20; import "../../src/Entry.sol"; contract ClosureStagingTest is Entry {}',
    )
    # 3. CI installs Foundry; require it there and compile the generated test.
    if not shutil.which("forge"):
        pytest.skip("Foundry is installed in the CI regression job")
    completed = subprocess.run(
        ["forge", "build"], cwd=isolated, text=True, capture_output=True, check=False
    )
    assert completed.returncode == 0, (
        f"Foundry failed to compile closure staging fixture\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )


def test_missing_required_closure_key_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "target"
    entry = target / "src" / "Entry.sol"
    _write(entry, "pragma solidity ^0.8.20; contract Entry {}")
    with pytest.raises(RuntimeError, match=r"missing_from_closure:src/Missing.sol"):
        _prepare_isolated_foundry_project(
            target,
            {"src/Entry.sol": entry},
            tmp_path / "isolated",
            required_keys=("src/Entry.sol", "src/Missing.sol"),
        )
