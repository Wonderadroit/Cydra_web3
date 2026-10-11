from cydra.ast_dataflow import extract_ast_relationships


def _identifier(node_id, name, ref):
    return {"nodeType": "Identifier", "id": node_id, "name": name, "referencedDeclaration": ref}


def test_constant_and_immutable_declarations_are_not_modeled_as_storage():
    ast = {
        "nodeType": "SourceUnit",
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "C", "nodes": [
                {"nodeType": "VariableDeclaration", "id": 2, "name": "LIMIT",
                 "stateVariable": True, "mutability": "constant"},
                {"nodeType": "VariableDeclaration", "id": 3, "name": "cached",
                 "stateVariable": True, "mutability": "immutable"},
                {"nodeType": "FunctionDefinition", "id": 4, "name": "readLimit",
                 "kind": "function", "scope": 1, "body": {"nodeType": "Block", "statements": [
                     {"nodeType": "ExpressionStatement", "expression": _identifier(5, "LIMIT", 2)}
                 ]}},
            ],
        }],
    }

    evidence = extract_ast_relationships(ast, "C.sol")

    assert not [item for item in evidence if item.target in {"LIMIT", "cached"}]


def test_mapping_key_reference_is_not_misclassified_as_storage_write():
    ast = {
        "nodeType": "SourceUnit",
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "C", "nodes": [
                {"nodeType": "VariableDeclaration", "id": 2, "name": "balances",
                 "stateVariable": True, "mutability": "mutable"},
                {"nodeType": "VariableDeclaration", "id": 3, "name": "account",
                 "stateVariable": True, "mutability": "mutable"},
                {"nodeType": "FunctionDefinition", "id": 4, "name": "setBalance",
                 "kind": "function", "scope": 1, "body": {"nodeType": "Block", "statements": [
                     {"nodeType": "ExpressionStatement", "expression": {
                         "nodeType": "Assignment", "id": 6, "operator": "=",
                         "leftHandSide": {
                             "nodeType": "IndexAccess", "id": 7,
                             "baseExpression": _identifier(8, "balances", 2),
                             "indexExpression": _identifier(9, "account", 3),
                         },
                         "rightHandSide": {"nodeType": "Literal", "id": 10, "value": "1"},
                     }}
                 ]}},
            ],
        }],
    }

    evidence = extract_ast_relationships(ast, "C.sol")
    roles = {item.target: item.metadata["semantic_relation"] for item in evidence if item.relation != "reference"}

    assert roles["balances"] == "write"
    assert roles["account"] == "read"


def test_yul_sstore_is_recorded_as_opaque_function_scoped_storage_write():
    ast = {
        "nodeType": "SourceUnit",
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "C", "nodes": [
                {"nodeType": "FunctionDefinition", "id": 2, "name": "setSolver",
                 "kind": "function", "scope": 1, "body": {"nodeType": "Block", "statements": [
                     {"nodeType": "InlineAssembly", "id": 3, "AST": {
                         "nodeType": "YulBlock", "statements": [{
                             "nodeType": "YulExpressionStatement", "expression": {
                                 "nodeType": "YulFunctionCall", "id": 4,
                                 "functionName": {"nodeType": "YulIdentifier", "name": "sstore"},
                                 "arguments": [
                                     {"nodeType": "YulIdentifier", "name": "slot"},
                                     {"nodeType": "YulIdentifier", "name": "value"},
                                 ],
                             },
                         }],
                     }},
                 ]}},
            ],
        }],
    }

    evidence = extract_ast_relationships(ast, "C.sol")
    writes = [item for item in evidence if item.relation == "writes" and item.metadata.get("storage_operation") == "sstore"]

    assert len(writes) == 1
    assert writes[0].target == "YUL_SLOT:setSolver:slot"
    assert writes[0].metadata["storage_slot_comparable"] is False
