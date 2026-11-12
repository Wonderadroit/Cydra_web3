import os
from pathlib import Path

import pytest

from cydra.compiler_state import compile_state_effects


FIXTURE = Path(__file__).parents[1] / "fixtures" / "solc-direct" / "hardhat-layout"


def test_hardhat_layout_uses_direct_solc_and_propagates_two_hop_writes(tmp_path, monkeypatch):
    project = tmp_path / "project"
    import shutil
    shutil.copytree(FIXTURE, project)
    marker = tmp_path / "hardhat-config-executed"
    monkeypatch.setenv("CYDRA_HARDHAT_MARKER", str(marker))
    source = project / "contracts" / "Concrete.sol"

    result = compile_state_effects(project, source)

    assert not marker.exists(), "CYDRA executed target-controlled Hardhat configuration"
    assert result.status in {"success", "ast_present_no_supported_evidence"}
    assert result.source_ast_found
    assert result.source_dependency_count >= 2
    assert result.compiler_versions == ("0.8.26",)
    writes = {
        item.target for item in result.evidence
        if item.function == "addValidator" and item.relation == "writes"
    }
    assert writes == {"state_A", "state_B"}
    propagated = [
        item for item in result.evidence
        if item.function == "addValidator" and item.relation == "writes"
        and item.metadata and item.metadata.get("propagated_from_internal_call")
    ]
    assert {item.target for item in propagated} == {"state_A", "state_B"}
