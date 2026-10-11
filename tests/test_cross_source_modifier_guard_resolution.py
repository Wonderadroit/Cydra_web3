import json
from pathlib import Path

from cydra.compiler_state import extract_constraints_from_build_info


def test_modifier_guard_resolves_reverting_helper_in_another_source(tmp_path: Path):
    project = tmp_path / "project"
    source = project / "src" / "chains" / "Mainnet" / "Intent.sol"
    source.parent.mkdir(parents=True)
    source.write_text("contract Intent is Base {}", encoding="utf-8")
    modifier_ast = {
        "nodeType": "SourceUnit", "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "Base", "nodes": [{
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
            }],
        }],
    }
    helper_ast = {
        "nodeType": "SourceUnit", "nodes": [{
            "nodeType": "FunctionDefinition", "id": 11, "name": "revertConfusedDeputy",
            "kind": "function",
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
        }],
    }
    build_info = tmp_path / "build-info.json"
    build_info.write_text(json.dumps({"output": {"sources": {
        "src/chains/Mainnet/Intent.sol": {"id": 0, "ast": {"nodeType": "SourceUnit", "nodes": []}},
        "src/SettlerMetaTxn.sol": {"id": 1, "ast": modifier_ast},
        "src/core/SettlerErrors.sol": {"id": 2, "ast": helper_ast},
    }}}), encoding="utf-8")

    evidence = extract_constraints_from_build_info(build_info, source, project)

    guard = [item for item in evidence if item.context_kind == "modifier" and item.function == "metaTx"]
    assert len(guard) == 1
    assert guard[0].parameter == "msgSender"
    assert guard[0].predicate == "_operator() == msgSender"
    assert guard[0].source == "solc-json-ast:src/SettlerMetaTxn.sol"
