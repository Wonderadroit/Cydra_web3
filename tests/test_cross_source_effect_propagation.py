from cydra.ast_dataflow import extract_compilation_relationships


def _id(node_id, name, ref):
    return {"nodeType": "Identifier", "id": node_id, "name": name,
            "referencedDeclaration": ref}


def _assignment(node_id, state_id, state_name, value_id):
    return {
        "nodeType": "Assignment", "id": node_id, "operator": "=",
        "leftHandSide": _id(node_id + 1, state_name, state_id),
        "rightHandSide": {"nodeType": "Literal", "id": value_id, "value": "1"},
    }


def _source(contract_id, contract_name, state_decls, functions):
    return {"nodeType": "SourceUnit", "nodes": [{
        "nodeType": "ContractDefinition", "id": contract_id, "name": contract_name,
        "nodes": state_decls + functions,
    }]}


def test_cross_source_internal_helper_effects_reach_public_caller():
    # These AST fragments mirror solc's globally unique declaration IDs across
    # the two checked-in Solidity fixture files. Separate AST inputs reproduce
    # the compiler_state per-source extraction boundary.
    parent = _source(1, "AbstractParent", [
        {"nodeType": "VariableDeclaration", "id": 2, "name": "_map",
         "stateVariable": True, "mutability": "mutable"},
        {"nodeType": "VariableDeclaration", "id": 3, "name": "_list",
         "stateVariable": True, "mutability": "mutable"},
        {"nodeType": "VariableDeclaration", "id": 4, "name": "_score",
         "stateVariable": True, "mutability": "mutable"},
    ], [
        {"nodeType": "FunctionDefinition", "id": 20, "name": "_add",
         "kind": "function", "scope": 1, "body": {"nodeType": "Block", "statements": [
             {"nodeType": "ExpressionStatement", "expression": _assignment(30, 2, "_map", 32)},
             {"nodeType": "ExpressionStatement", "expression": _assignment(40, 3, "_list", 42)},
         ]}},
        {"nodeType": "FunctionDefinition", "id": 21, "name": "_init",
         "kind": "function", "scope": 1, "body": {"nodeType": "Block", "statements": [
             {"nodeType": "ExpressionStatement", "expression": _assignment(50, 4, "_score", 52)},
         ]}},
    ])
    concrete = _source(10, "Concrete", [], [
        {"nodeType": "FunctionDefinition", "id": 60, "name": "addValidator",
         "kind": "function", "scope": 10, "body": {"nodeType": "Block", "statements": [
             {"nodeType": "ExpressionStatement", "expression": {
                 "nodeType": "FunctionCall", "id": 61,
                 "expression": _id(62, "_add", 20), "arguments": []}},
             {"nodeType": "ExpressionStatement", "expression": {
                 "nodeType": "FunctionCall", "id": 63,
                 "expression": _id(64, "_init", 21), "arguments": []}},
         ]}},
    ])

    evidence = extract_compilation_relationships([
        ("AbstractParent.sol", parent),
        ("Concrete.sol", concrete),
    ])

    def writes(evidence, contract, function):
        return {item.target for item in evidence
                if item.contract == contract and item.function == function
                and item.relation == "writes"}

    assert writes(evidence, "AbstractParent", "_add") == {"_map", "_list"}
    assert writes(evidence, "AbstractParent", "_init") == {"_score"}
    assert writes(evidence, "Concrete", "addValidator") == {
        "_map", "_list", "_score"
    }
