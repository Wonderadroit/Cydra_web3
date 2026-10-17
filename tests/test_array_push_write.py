from cydra.capabilities.array_push_write import ArrayPushWrite


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


def call(receiver, member, *args):
    return {
        "nodeType": "FunctionCall",
        "expression": {
            "nodeType": "MemberAccess",
            "memberName": member,
            "expression": receiver,
        },
        "arguments": list(args),
    }


def test_mapping_entry_array_push_extracts_base_state_variable():
    # Virtuals shape: _validators[virtualId].push(validator).
    receiver = index(identifier("_validators", 10), identifier("virtualId", 20))
    node = call(receiver, "push", identifier("validator", 30))
    form = ArrayPushWrite({10: "_validators"})
    assert form.matches(node)
    assert form.extract_target(node) == "_validators"


def test_direct_state_array_push_extracts_state_variable():
    node = call(identifier("_validators", 10), "push", identifier("validator", 30))
    form = ArrayPushWrite({10: "_validators"})
    assert form.matches(node)
    assert form.extract_target(node) == "_validators"


def test_mapping_entry_array_pop_extracts_base_state_variable():
    receiver = index(identifier("_validators", 10), identifier("virtualId", 20))
    node = call(receiver, "pop")
    form = ArrayPushWrite({10: "_validators"})
    assert form.matches(node)
    assert form.extract_target(node) == "_validators"


def test_local_array_push_is_rejected_by_declaration_identity():
    node = call(identifier("someArray", 50), "push", identifier("value", 60))
    form = ArrayPushWrite({10: "_validators"})
    assert not form.matches(node)
    assert form.extract_target(node) is None


def test_mapping_entry_array_root_not_mapping_index_or_local_is_returned():
    # The base declaration is the write target; the mapping key is irrelevant.
    receiver = index(identifier("_someMapping", 10), identifier("addr", 20))
    node = call(receiver, "push", identifier("value", 30))
    form = ArrayPushWrite({10: "_someMapping"})
    assert form.extract_target(node) == "_someMapping"
