from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cydra.experiment_planning import bind_experiment
from cydra.models import Experiment, Hypothesis
from scripts.run_authorization_campaign import (
    _campaign_collection_payload,
    _parse_candidate_identity,
    _select_hypotheses,
    _write_campaign_collection,
)


def _hypothesis(
    hypothesis_id: str = "H-AUTH-setSlasher",
    *,
    source_path: str = "/checkout/middleware-sdk/lib/core/src/contracts/vault/Vault.sol",
    contract: str = "Vault",
    function: str = "setSlasher",
    line: int = 354,
) -> Hypothesis:
    return Hypothesis(
        hypothesis_id=hypothesis_id,
        claim="untrusted caller can change slasher",
        invariant_id="INV-AUTH-001",
        target_function=function,
        attacker_capability="arbitrary caller",
        expected_impact="unauthorized state change",
        source_path=source_path,
        declaring_contract=contract,
        source_line=line,
    )


def test_requested_candidate_selects_by_full_source_identity():
    target = _hypothesis()
    other = _hypothesis(
        "H-AUTH-claimBatch",
        function="claimBatch",
        line=410,
    )

    selected = _select_hypotheses(
        (other, target),
        "middleware-sdk/lib/core/src/contracts/vault/Vault.sol::Vault::setSlasher::354",
        target_path="middleware-sdk/lib/core/src/contracts/vault/Vault.sol",
    )

    assert selected == (target,)


def test_short_source_filename_is_scoped_to_pinned_target_path():
    target = _hypothesis()

    selected = _select_hypotheses(
        (target,),
        "Vault.sol::Vault::setSlasher::354",
        target_path="middleware-sdk/lib/core/src/contracts/vault/Vault.sol",
    )

    assert selected == (target,)


def test_requested_candidate_missing_fails_closed():
    with pytest.raises(SystemExit, match="candidate-missing"):
        _select_hypotheses(
            (_hypothesis(),),
            "middleware-sdk/lib/core/src/contracts/vault/Vault.sol::Vault::claimBatch::410",
            target_path="middleware-sdk/lib/core/src/contracts/vault/Vault.sol",
        )


def test_duplicate_full_source_identity_fails_closed_as_ambiguous():
    duplicate_a = _hypothesis("H-AUTH-duplicate-a")
    duplicate_b = _hypothesis("H-AUTH-duplicate-b")

    with pytest.raises(SystemExit, match="candidate-ambiguous"):
        _select_hypotheses(
            (duplicate_a, duplicate_b),
            "middleware-sdk/lib/core/src/contracts/vault/Vault.sol::Vault::setSlasher::354",
            target_path="middleware-sdk/lib/core/src/contracts/vault/Vault.sol",
        )


@pytest.mark.parametrize(
    "value",
    [
        "Vault.sol::Vault::setSlasher",
        "Vault.sol::Vault::setSlasher::0",
        "Vault.sol::Vault::setSlasher::line",
        "::Vault::setSlasher::354",
    ],
)
def test_requested_candidate_rejects_incomplete_or_invalid_identity(value: str):
    with pytest.raises(ValueError):
        _parse_candidate_identity(value)


def test_experiment_binding_preserves_hypothesis_and_target_function():
    hypothesis = _hypothesis()
    planned = Experiment(
        experiment_id="X-H-AUTH-setSlasher",
        hypothesis_id=hypothesis.hypothesis_id,
        action="call setSlasher from an unrelated account",
        discriminates=("authorized", "unauthorized"),
        cost=1.0,
    )

    bound = bind_experiment(
        hypothesis,
        planned,
        target_function=hypothesis.target_function,
    )

    assert bound.hypothesis_id == hypothesis.hypothesis_id
    assert bound.target_function == "setSlasher"


def test_blind_collection_retains_every_candidate_and_has_no_targeted_final():
    hypotheses = (_hypothesis(), _hypothesis("H-AUTH-claimBatch", function="claimBatch", line=410))
    results = [
        {"hypothesis": {"hypothesis_id": item.hypothesis_id}, "classification": "UNMEASURABLE"}
        for item in hypotheses
    ]

    payload = _campaign_collection_payload(
        target="symbiotic@pinned:Vault.sol",
        campaign_mode="blind",
        requested_candidate=None,
        hypotheses=hypotheses,
        candidate_results=results,
    )

    assert payload["candidate_count"] == 2
    assert payload["candidate_order"] == ["H-AUTH-setSlasher", "H-AUTH-claimBatch"]
    assert payload["candidate_results"] == results
    assert payload["final_result"] is None


def test_targeted_collection_exposes_only_the_selected_final_result():
    hypothesis = _hypothesis()
    result = {
        "hypothesis": {"hypothesis_id": hypothesis.hypothesis_id},
        "classification": "UNMEASURABLE",
    }

    payload = _campaign_collection_payload(
        target="symbiotic@pinned:Vault.sol",
        campaign_mode="targeted",
        requested_candidate="Vault.sol::Vault::setSlasher::354",
        hypotheses=(hypothesis,),
        candidate_results=(result,),
    )

    assert payload["candidate_count"] == 1
    assert payload["final_result"] == result
    assert payload["classification"] == "UNMEASURABLE"


def test_cli_rejects_requested_candidate_in_explicit_blind_mode():
    repository_root = Path(__file__).resolve().parents[1]
    script = repository_root / "scripts" / "run_authorization_campaign.py"
    command = [
        sys.executable,
        str(script),
        "--target-repo", "https://github.com/example/target",
        "--target-ref", "deadbeef",
        "--target-path", "Vault.sol",
        "--target-project", ".",
        "--mode", "blind",
        "--requested-candidate", "Vault.sol::Vault::setSlasher::354",
    ]
    result = subprocess.run(
        command,
        cwd=repository_root,
        env={**__import__("os").environ, "PYTHONPATH": str(repository_root / "src")},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "--requested-candidate is forbidden in blind mode" in result.stderr



def test_campaign_collection_writer_emits_valid_json(tmp_path: Path):
    output = tmp_path / "campaign.json"
    payload = {
        "campaign_mode": "blind",
        "candidate_results": [{"classification": "UNMEASURABLE"}],
    }

    _write_campaign_collection(output, payload)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
