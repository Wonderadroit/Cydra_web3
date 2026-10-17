from cydra.capabilities.mapping_getter_observation import MappingGetterObservation


def test_public_mapping_getter_reads_one_key():
    observation = MappingGetterObservation(
        "contract T { mapping(uint256 => address) public _x; }"
    )
    assert observation.resolve("_x") == ("_x", 1)
    assert observation.emit_probe("_x", ["key"]) == "target._x(key)"
    assert observation.read_state({"getters": {"_x": lambda key: "0xabc"}}, [7]) == "0xabc"
    assert observation.last_reason is None


def test_private_mapping_uses_source_backed_view_getter():
    source = """
    contract T {
        mapping(address => address) private _x;
        function getX(address key) public view returns (address) {
            return _x[key];
        }
    }
    """
    observation = MappingGetterObservation(source)
    assert observation.resolve("_x") == ("getX", 1)
    assert observation.emit_probe("_x", ["key"]) == "target.getX(key)"
    assert observation.read_state(
        {"getter_name": "getX", "getters": {"getX": lambda key: "0xdef"}}, ["alice"]
    ) == "0xdef"


def test_wrong_argument_count_fails_closed_with_stable_reason():
    observation = MappingGetterObservation(
        "contract T { mapping(uint256 => address) public _x; }"
    )
    assert observation.read_state({"getters": {"_x": lambda key: "0xabc"}}, []) is None
    assert observation.last_reason == "arg_arity_mismatch"
    assert observation.emit_probe("_x", []) == ""
    assert observation.last_reason == "arg_arity_mismatch"


def test_reverting_mapping_getter_fails_closed():
    def reverted(key):
        raise RuntimeError("revert")

    observation = MappingGetterObservation(
        "contract T { mapping(uint256 => address) public _x; }"
    )
    assert observation.read_state({"getters": {"_x": reverted}}, [1]) is None
    assert observation.last_reason == "call_reverted"


def test_missing_mapping_getter_defers_without_fallback():
    source = """
    contract T {
        mapping(address => mapping(address => bool)) private _validatorsMap;
        function isValidator(address virtualId, address validator) public view returns (bool) {
            return _validatorsMap[virtualId][validator];
        }
    }
    """
    observation = MappingGetterObservation(source)
    assert observation.resolve("_validatorsMap") is None
    assert observation.can_observe("_validatorsMap") is False
    assert observation.read_state({"getters": {"isValidator": lambda a, b: True}}, ["a", "b"]) is None
    assert observation.last_reason == "getter_not_found"
