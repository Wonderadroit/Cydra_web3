from cydra.capabilities.nested_mapping_write import NestedMappingWrite


def identifier(name, declaration_id):
    return {
        "nodeType": "Identifier",
        "name": name,
        "referencedDeclaration": declaration_id,
    }


def index(base, key):
    return {
        "nodeType": "IndexAccess",
        "baseExpression": base,
        "indexExpression": key,
    }


def assignment(lhs, operator="="):
    return {
        "nodeType": "Assignment",
        "operator": operator,
        "leftHandSide": lhs,
        "rightHandSide": {"nodeType": "Literal", "value": "1"},
    }


def test_two_level_mapping_write_extracts_root():
    lhs = index(index(identifier("m", 10), identifier("a", 20)), identifier("b", 30))
    assert NestedMappingWrite({10: "m"}).extract_target(assignment(lhs)) == "m"


def test_single_level_mapping_write_extracts_root():
    lhs = index(identifier("m", 10), identifier("a", 20))
    assert NestedMappingWrite({10: "m"}).extract_target(assignment(lhs)) == "m"


def test_arbitrary_depth_mapping_write_extracts_root():
    lhs = index(
        index(index(identifier("m", 10), identifier("a", 20)), identifier("b", 30)),
        identifier("c", 40),
    )
    assert NestedMappingWrite({10: "m"}).extract_target(assignment(lhs)) == "m"


def test_compound_assignment_through_nested_mapping_extracts_root():
    lhs = index(index(identifier("m", 10), identifier("a", 20)), identifier("b", 30))
    form = NestedMappingWrite({10: "m"})
    node = assignment(lhs, "+=")
    assert form.matches(node)
    assert form.extract_target(node) == "m"


def test_local_struct_mapping_field_is_not_extracted_as_state_write():
    local_struct = {
        "nodeType": "MemberAccess",
        "memberName": "mappingField",
        "expression": identifier("localStruct", 50),
    }
    lhs = index(index(local_struct, identifier("a", 20)), identifier("b", 30))
    form = NestedMappingWrite({10: "m", 50: "localStruct"})
    assert not form.matches(assignment(lhs))
    assert form.extract_target(assignment(lhs)) is None
