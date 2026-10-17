from cydra.blind_authorization import _resolve_state_observer
from cydra.models import FunctionModel, ParameterModel


def test_production_observer_resolver_records_mapping_capability():
    source = """
    contract Agent {
        mapping(address virtualId => mapping(address validator => bool)) public _validatorsMap;
    }
    """
    function = FunctionModel(
        name="addValidator",
        visibility="public",
        modifiers=(),
        writes=("_validatorsMap",),
        external_calls=(),
        line=1,
        parameters=(
            ParameterModel(name="virtualId", type="address"),
            ParameterModel(name="validator", type="address"),
        ),
    )

    result = _resolve_state_observer(source, function, "_validatorsMap")

    assert result is not None
    callable_name, return_type, indexes = result
    assert (callable_name, return_type, indexes) == (
        "_validatorsMap", "bool", [0, 1]
    )
    assert result.method_used == "MappingGetterObservation"
