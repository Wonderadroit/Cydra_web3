from cydra.capabilities.scalar_write import ScalarWrite


def assignment(operator="=", declaration_id=10, *, lhs_type="Identifier"):
    if lhs_type == "MemberAccess":
        lhs = {
            "nodeType": "MemberAccess",
            "memberName": "field",
            "expression": {
                "nodeType": "Identifier",
                "name": "x",
                "referencedDeclaration": declaration_id,
            },
        }
    else:
        lhs = {
            "nodeType": "Identifier",
            "name": "x",
            "referencedDeclaration": declaration_id,
        }
    return {
        "nodeType": "Assignment",
        "operator": operator,
        "leftHandSide": lhs,
        "rightHandSide": {"nodeType": "Literal", "value": "1"},
    }


def test_direct_scalar_assignment_extracts_state_target():
    form = ScalarWrite({10: "x"})
    node = assignment("=")
    assert form.matches(node)
    assert form.extract_target(node) == "x"


def test_compound_assignment_extracts_state_target():
    form = ScalarWrite({10: "x"})
    node = assignment("+=")
    assert form.matches(node)
    assert form.extract_target(node) == "x"


def test_local_variable_assignment_is_not_extracted_as_state_write():
    form = ScalarWrite({10: "x"})
    node = assignment("=", declaration_id=20)
    assert not form.matches(node)
    assert form.extract_target(node) is None


def test_struct_field_assignment_is_left_to_future_write_form():
    form = ScalarWrite({10: "x"})
    node = assignment("=", lhs_type="MemberAccess")
    assert not form.matches(node)
    assert form.extract_target(node) is None


def test_local_shadowing_state_variable_uses_declaration_identity():
    form = ScalarWrite({10: "x"})
    local_write = assignment("=", declaration_id=20)
    state_write = assignment("=", declaration_id=10)
    assert form.extract_target(local_write) is None
    assert form.extract_target(state_write) == "x"
