from cydra.models import ContractModel, FunctionModel
from cydra.reasoning import initialization_surface_functions


def test_initializer_modifier_detects_named_initialization_surface():
    initializer = FunctionModel(
        name="initializeManager", visibility="external", modifiers=("initializer",),
        writes=("manager",), external_calls=(), line=10,
    )
    guarded_admin = FunctionModel(
        name="setManager", visibility="external", modifiers=("onlyManagerOrOwner",),
        writes=("manager",), external_calls=(), line=20,
    )
    contract = ContractModel(
        name="GPv2AllowListAuthentication", source="src/contracts/GPv2AllowListAuthentication.sol",
        functions=(initializer, guarded_admin),
    )

    surfaces = initialization_surface_functions(contract)

    assert [function.name for function in surfaces] == ["initializeManager"]
