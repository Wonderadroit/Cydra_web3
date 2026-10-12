from pathlib import Path

from scripts.run_authorization_scope_campaign import _in_scope_solidity_files, _stage_flags


def test_scope_enumeration_excludes_only_the_named_out_of_scope_file(tmp_path: Path):
    source = tmp_path / "src"
    (source / "facility").mkdir(parents=True)
    (source / "vaults").mkdir()
    excluded = source / "facility" / "IntentDescriptor.sol"
    allowed_facility = source / "facility" / "VaultAdapter.sol"
    nested = source / "vaults" / "Nested.sol"
    for path in (excluded, allowed_facility, nested):
        path.write_text("pragma solidity ^0.8.20;\n", encoding="utf-8")

    files = _in_scope_solidity_files(tmp_path, source)

    assert files == [allowed_facility, nested]
    assert excluded not in files


def test_stage_flags_distinguish_seeds_without_hypothesis():
    flags = _stage_flags({"hypothesis_seeds": [{"question": "Can unauthorized caller change state?"}], "hypotheses": []})

    assert flags == {
        "seeds": True,
        "hypothesis": False,
        "experiment_plan": False,
        "execution_attempted": False,
    }


def test_stage_flags_record_hypothesis_plan_and_execution():
    flags = _stage_flags({
        "hypothesis_seeds": [{"question": "Can caller change state?"}],
        "hypothesis": {"hypothesis_id": "H-AUTH-setManager"},
        "experiment": {"experiment_id": "E-AUTH-setManager"},
        "blind_execution": {"executed": True, "status": "FAIL"},
    })

    assert all(flags.values())
