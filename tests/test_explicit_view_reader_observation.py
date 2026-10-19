from cydra.capabilities.explicit_view_reader_observation import ExplicitViewReaderObservation


VIRTUALS_SOURCE = """
contract AgentNftV2 {
    mapping(address => mapping(address => bool)) private _validatorsMap;

    function isValidator(address virtualId, address validator) public view returns (bool) {
        return _validatorsMap[virtualId][validator];
    }
}
"""


def test_nested_mapping_uses_explicit_is_validator_reader():
    observation = ExplicitViewReaderObservation(VIRTUALS_SOURCE)
    assert observation.resolve("_validatorsMap") == ("isValidator", 2, "bool")
    assert observation.emit_probe("_validatorsMap", ["virtualId", "validator"]) == (
        "target.isValidator(virtualId, validator)"
    )
    assert observation.read_state(
        {"getter_names": ["isValidator"], "getters": {"isValidator": lambda a, b: True}},
        ["id", "alice"],
    ) is True
    assert observation.last_reason is None


def test_private_mapping_without_reader_fails_closed():
    observation = ExplicitViewReaderObservation(
        "contract T { mapping(address => bool) private _x; }"
    )
    assert observation.resolve("_x") is None
    assert observation.can_observe("_x") is False
    assert observation.read_state({"getter_names": [], "getters": {}}, ["a"]) is None
    assert observation.last_reason == "getter_not_found"


def test_wrong_argument_count_reports_arity_mismatch():
    observation = ExplicitViewReaderObservation(VIRTUALS_SOURCE)
    assert observation.emit_probe("_validatorsMap", ["onlyOne"]) == ""
    assert observation.last_reason == "arg_arity_mismatch"
    assert observation.read_state(
        {"getter_names": ["isValidator"], "getters": {"isValidator": lambda a, b: True}},
        ["onlyOne"],
    ) is None
    assert observation.last_reason == "arg_arity_mismatch"


def test_reverting_reader_reports_call_reverted():
    def reverted(a, b):
        raise RuntimeError("revert")

    observation = ExplicitViewReaderObservation(VIRTUALS_SOURCE, getter_name="isValidator")
    assert observation.read_state(
        {"getter_names": ["isValidator"], "getters": {"isValidator": reverted}},
        ["id", "alice"],
    ) is None
    assert observation.last_reason == "call_reverted"


def test_multiple_readers_choose_alphabetically():
    source = """
    contract T {
        mapping(address => mapping(address => bool)) private _validatorsMap;
        function isValidator(address id, address who) public view returns (bool) {
            return _validatorsMap[id][who];
        }
        function getValidatorInfo(address id, address who) external view returns (bool) {
            return _validatorsMap[id][who];
        }
    }
    """
    observation = ExplicitViewReaderObservation(source)
    assert observation.resolve("_validatorsMap") == ("getValidatorInfo", 2, "bool")
    assert observation.emit_probe("_validatorsMap", ["id", "who"]) == (
        "target.getValidatorInfo(id, who)"
    )
    assert observation.read_state(
        {
            "getter_names": ["isValidator", "getValidatorInfo"],
            "getters": {
                "isValidator": lambda a, b: "is",
                "getValidatorInfo": lambda a, b: "info",
            },
        },
        ["id", "who"],
    ) == "info"
