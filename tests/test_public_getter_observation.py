from cydra.capabilities.public_getter_observation import PublicGetterObservation


def test_exact_public_scalar_getter_name_is_resolved_and_read():
    observation = PublicGetterObservation(
        "contract T { uint256 public total; }",
        getter_name="total",
    )
    assert observation.resolve("total") == ("total", "uint256")
    assert observation.emit_probe("total") == "target.total()"
    assert observation.read_state(
        {"getters": {"other": lambda: 999, "total": lambda: 42}}
    ) == 42
    assert observation.last_reason is None


def test_missing_getter_fails_closed_with_none():
    observation = PublicGetterObservation("contract T { uint256 public total; }")
    assert observation.resolve("missing") is None
    assert observation.can_observe("missing") is False
    assert observation.read_state({}) is None
    assert observation.last_reason == "getter_not_found"


def test_reverting_getter_fails_closed_and_records_reason():
    def reverted():
        raise RuntimeError("staticcall reverted")

    observation = PublicGetterObservation(getter_name="total")
    assert observation.read_state({"getters": {"total": reverted}}) is None
    assert observation.last_reason == "call_reverted"


def test_candidate_getter_choice_is_deterministic():
    observation = PublicGetterObservation()
    result = observation.read_state(
        {"getters": {"zeta": lambda: "z", "alpha": lambda: "a"}}
    )
    assert result == "a"
    assert observation.last_reason is None
