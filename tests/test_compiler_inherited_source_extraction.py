import json
from pathlib import Path

from cydra.compiler_state import (
    extract_constraints_from_build_info,
    extract_state_effects_from_build_info,
)


def _ast_with_inherited_setter():
    return {
        "nodeType": "SourceUnit",
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 1, "name": "Base", "nodes": [
                {
                    "nodeType": "VariableDeclaration", "id": 2,
                    "name": "solverList", "stateVariable": True,
                },
                {
                    "nodeType": "FunctionDefinition", "id": 3, "name": "setSolver",
                    "kind": "function", "scope": 1,
                    "parameters": {"parameters": [{
                        "nodeType": "VariableDeclaration", "id": 8, "name": "solver",
                    }]},
                    "body": {"nodeType": "Block", "statements": [
                        {"nodeType": "ExpressionStatement", "expression": {
                            "nodeType": "FunctionCall", "id": 9,
                            "expression": {"nodeType": "Identifier", "id": 10, "name": "require"},
                            "arguments": [{
                                "nodeType": "BinaryOperation", "id": 11, "operator": "!=",
                                "leftExpression": {
                                    "nodeType": "Identifier", "id": 12, "name": "solver",
                                    "referencedDeclaration": 8,
                                },
                                "rightExpression": {"nodeType": "Literal", "id": 13, "value": "0"},
                            }],
                        }},
                        {"nodeType": "ExpressionStatement", "expression": {
                            "nodeType": "Assignment", "id": 14, "operator": "=",
                            "leftHandSide": {
                                "nodeType": "Identifier", "id": 15, "name": "solverList",
                                "referencedDeclaration": 2,
                            },
                            "rightHandSide": {"nodeType": "Literal", "id": 16, "value": "1"},
                        }},
                    ]},
                },
            ],
        }],
    }


def _write_build_info(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "project"
    source = project / "src" / "chains" / "Mainnet" / "Intent.sol"
    source.parent.mkdir(parents=True)
    source.write_text("contract Intent is Base {}", encoding="utf-8")
    build_info = tmp_path / "build-info.json"
    build_info.write_text(json.dumps({"output": {"sources": {
        "src/chains/Mainnet/Intent.sol": {
            "id": 0, "ast": {"nodeType": "SourceUnit", "nodes": []}
        },
        "src/SettlerIntent.sol": {"id": 1, "ast": _ast_with_inherited_setter()},
    }}}), encoding="utf-8")
    return build_info, source, project


def test_state_effects_are_extracted_from_imported_inherited_contract_ast(tmp_path: Path):
    build_info, source, project = _write_build_info(tmp_path)

    evidence = extract_state_effects_from_build_info(build_info, source, project)

    writes = [item for item in evidence if item.function == "setSolver" and item.relation == "writes"]
    assert len(writes) == 1
    assert writes[0].target == "solverList"
    assert writes[0].source == "solc-json-ast:src/SettlerIntent.sol"


def test_parameter_constraints_are_extracted_from_imported_contract_ast(tmp_path: Path):
    build_info, source, project = _write_build_info(tmp_path)

    evidence = extract_constraints_from_build_info(build_info, source, project)

    assert len(evidence) == 1
    assert evidence[0].function == "setSolver"
    assert evidence[0].parameter == "solver"
    assert evidence[0].predicate == "solver != 0"
