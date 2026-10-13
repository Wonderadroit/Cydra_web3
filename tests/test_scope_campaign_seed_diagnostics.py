from scripts.run_authorization_scope_campaign import _seed_diagnostics


def test_blocked_seed_reasons_are_preserved_without_promoting_seeds():
    payload = {
        "hypothesis_seeds": [
            {
                "seed_id": "SEED-AUTH-C-f-10",
                "target_contract": "C",
                "target_function": "f",
                "source": "src/C.sol",
                "source_line": 10,
                "status": "blocked",
                "invariant_source": "generic",
                "observed_writes": [],
                "preconditions_needed": ["resolve_recorded_execution_path"],
                "uncertainty": [
                    "security-relevant effects and/or authorization along the recorded path are not established within the analysis budget"
                ],
                "provenance": ["unresolved_path:model_call:helper:callee_effect_or_authorization_unclassified"],
                "analysis_budget": "direct-call-sites; one-inheritance-level; no-cross-contract-resolution",
            },
            {
                "seed_id": "SEED-AUTH-C-g-11",
                "target_contract": "C",
                "target_function": "g",
                "status": "seed",
                "uncertainty": [],
                "provenance": [],
                "observed_writes": ["_roles"],
            },
        ]
    }

    result = _seed_diagnostics(payload)

    assert result["seed_status_counts"] == {"blocked": 1, "seed": 1}
    assert result["blocked_seed_count"] == 1
    assert result["blocked_seed_reason_counts"] == {
        "security-relevant effects and/or authorization along the recorded path are not established within the analysis budget": 1
    }
    blocked = result["blocked_seeds"][0]
    assert blocked["function"] == "f"
    assert blocked["preconditions_needed"] == ["resolve_recorded_execution_path"]
    assert blocked["provenance"] == [
        "unresolved_path:model_call:helper:callee_effect_or_authorization_unclassified"
    ]
    assert blocked["observed_writes"] == []
    assert blocked["invariant_source"] == "generic"
