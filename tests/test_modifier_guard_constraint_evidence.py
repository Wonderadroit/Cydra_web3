from cydra.compiler_constraints import extract_parameter_constraints


def test_modifier_parameter_guard_resolves_helper_that_reverts_in_yul():
    ast = {
        "nodeType": "SourceUnit",
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "C", "nodes": [
                {
                    "nodeType": "ModifierDefinition", "id": 2, "name": "metaTx", "scope": 1,
                    "parameters": {"parameters": [{
                        "nodeType": "VariableDeclaration", "id": 3, "name": "msgSender",
                    }]},
                    "body": {"nodeType": "Block", "statements": [{
                        "nodeType": "IfStatement", "id": 4,
                        "condition": {
                            "nodeType": "BinaryOperation", "id": 5, "operator": "==",
                            "leftExpression": {"nodeType": "FunctionCall", "id": 6,
                                "expression": {"nodeType": "Identifier", "id": 7, "name": "_operator"},
                                "arguments": []},
                            "rightExpression": {"nodeType": "Identifier", "id": 8,
                                "name": "msgSender", "referencedDeclaration": 3},
                        },
                        "trueBody": {"nodeType": "Block", "statements": [{
                            "nodeType": "ExpressionStatement", "expression": {
                                "nodeType": "FunctionCall", "id": 9,
                                "expression": {"nodeType": "Identifier", "id": 10,
                                    "name": "revertConfusedDeputy", "referencedDeclaration": 11},
                                "arguments": [],
                            },
                        }]},
                        "falseBody": {"nodeType": "Block", "statements": []},
                    }]},
                },
                {
                    "nodeType": "FunctionDefinition", "id": 11, "name": "revertConfusedDeputy",
                    "kind": "function", "scope": 1,
                    "body": {"nodeType": "Block", "statements": [{
                        "nodeType": "InlineAssembly", "id": 12, "AST": {
                            "nodeType": "YulBlock", "statements": [{
                                "nodeType": "YulExpressionStatement", "expression": {
                                    "nodeType": "YulFunctionCall", "id": 13,
                                    "functionName": {"nodeType": "YulIdentifier", "name": "revert"},
                                    "arguments": [],
                                },
                            }],
                        },
                    }]},
                },
            ],
        }],
    }

    evidence = extract_parameter_constraints(ast, "C.sol")

    assert len(evidence) == 1
    assert evidence[0].function == "metaTx"
    assert evidence[0].context_kind == "modifier"
    assert evidence[0].kind == "revert_guard"
    assert evidence[0].parameter == "msgSender"
    assert evidence[0].predicate == "_operator() == msgSender"
