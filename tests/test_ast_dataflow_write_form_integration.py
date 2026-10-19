from cydra.ast_dataflow import extract_ast_relationships


def test_production_ast_entrypoint_dispatches_nested_mapping_write_form():
    ast = {
        "nodeType": "SourceUnit",
        "nodes": [
            {
                "nodeType": "ContractDefinition",
                "id": 1,
                "name": "Agent",
                "nodes": [
                    {
                        "nodeType": "VariableDeclaration",
                        "id": 10,
                        "name": "_validatorsMap",
                        "stateVariable": True,
                        "mutability": "mutable",
                    },
                    {
                        "nodeType": "FunctionDefinition",
                        "id": 20,
                        "name": "addValidator",
                        "scope": 1,
                        "kind": "function",
                        "body": {
                            "nodeType": "Block",
                            "statements": [
                                {
                                    "nodeType": "ExpressionStatement",
                                    "expression": {
                                        "nodeType": "Assignment",
                                        "id": 30,
                                        "operator": "=",
                                        "leftHandSide": {
                                            "nodeType": "IndexAccess",
                                            "baseExpression": {
                                                "nodeType": "IndexAccess",
                                                "baseExpression": {
                                                    "nodeType": "Identifier",
                                                    "id": 31,
                                                    "name": "_validatorsMap",
                                                    "referencedDeclaration": 10,
                                                },
                                                "indexExpression": {
                                                    "nodeType": "Identifier",
                                                    "id": 32,
                                                    "name": "virtualId",
                                                    "referencedDeclaration": 40,
                                                },
                                            },
                                            "indexExpression": {
                                                "nodeType": "Identifier",
                                                "id": 33,
                                                "name": "validator",
                                                "referencedDeclaration": 41,
                                            },
                                        },
                                        "rightHandSide": {
                                            "nodeType": "Literal",
                                            "value": "true",
                                        },
                                    },
                                }
                            ],
                        },
                    },
                ],
            }
        ],
    }

    evidence = extract_ast_relationships(ast, "Agent.sol")
    write = next(
        item for item in evidence
        if item.function == "addValidator"
        and item.target == "_validatorsMap"
        and item.relation == "writes"
    )
    assert write.metadata["write_method"] == "NestedMappingWrite"
    assert write.metadata["write_args"] == ["virtualId", "validator"]
