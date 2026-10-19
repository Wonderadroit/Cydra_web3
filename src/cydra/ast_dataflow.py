from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from .capabilities.scalar_write import ScalarWrite
from .capabilities.nested_mapping_write import NestedMappingWrite
from .capabilities.array_push_write import ArrayPushWrite


@dataclass(frozen=True)
class SemanticRelationshipEvidence:
    """A compiler-AST-backed relationship; never inferred from co-occurrence."""
    contract: str
    function: str
    relation: str
    target: str
    confidence: float
    source: str
    ast_node_id: int | None = None
    source_location: tuple[int, int, int] | None = None
    function_ast_node_id: int | None = None
    target_ast_node_id: int | None = None
    metadata: dict[str, Any] | None = None


def _walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        if isinstance(node.get("nodeType"), str):
            yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _location(node: dict[str, Any]) -> tuple[int, int, int] | None:
    src = node.get("src")
    if not isinstance(src, str):
        return None
    parts = src.split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _node_id(node: Any) -> int | None:
    value = node.get("id") if isinstance(node, dict) else None
    return value if isinstance(value, int) else None


def _state_refs(node: Any, states: dict[int, str]) -> list[dict[str, Any]]:
    return [item for item in _walk(node)
            if item.get("nodeType") == "Identifier"
            and isinstance(item.get("referencedDeclaration"), int)
            and item["referencedDeclaration"] in states]


def _lvalue_state_roots(node: Any, states: dict[int, str]) -> list[dict[str, Any]]:
    """Resolve only the storage root of an lvalue, never an index/key expression."""
    if not isinstance(node, dict):
        return []
    kind = node.get("nodeType")
    if kind == "Identifier":
        ref = node.get("referencedDeclaration")
        return [node] if isinstance(ref, int) and ref in states else []
    if kind in {"IndexAccess", "IndexRangeAccess"}:
        return _lvalue_state_roots(node.get("baseExpression"), states)
    if kind == "MemberAccess":
        return _lvalue_state_roots(node.get("expression"), states)
    if kind == "TupleExpression":
        result: list[dict[str, Any]] = []
        components = node.get("components")
        if isinstance(components, list):
            for component in components:
                result.extend(_lvalue_state_roots(component, states))
        return result
    return []


def _mark_lvalue_roles(node: Any, states: dict[int, str], roles: dict[int, str], role: str) -> None:
    """Mark storage-root state references; state variables used as keys remain reads."""
    roots = _lvalue_state_roots(node, states)
    root_ids = {_node_id(item) for item in roots if _node_id(item) is not None}
    for root_id in root_ids:
        roles[root_id] = role
    for ref in _state_refs(node, states):
        ref_id = _node_id(ref)
        if ref_id is not None and ref_id not in root_ids and ref_id not in roles:
            roles[ref_id] = "read"


def _yul_expression(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    kind = node.get("nodeType")
    if kind in {"YulIdentifier", "YulLiteral"}:
        value = node.get("name") if kind == "YulIdentifier" else node.get("value")
        return str(value) if value is not None else ""
    if kind == "YulFunctionCall":
        function = node.get("functionName")
        name = function.get("name") if isinstance(function, dict) else None
        args = node.get("arguments", [])
        rendered = [_yul_expression(item) for item in args] if isinstance(args, list) else []
        if isinstance(name, str) and all(rendered):
            return f"{name}({', '.join(rendered)})"
        return str(name) if isinstance(name, str) else ""
    if kind == "YulBinaryOperation":
        op = node.get("operator")
        left = _yul_expression(node.get("leftExpression"))
        right = _yul_expression(node.get("rightExpression"))
        if isinstance(op, str) and left and right:
            return f"{op}({left}, {right})"
    return ""


def _operator_contexts(body: dict[str, Any], states: dict[int, str]) -> dict[int, str]:
    roles: dict[int, str] = {}
    for node in _walk(body):
        if node.get("nodeType") == "Assignment":
            operator = node.get("operator")
            if operator == "=":
                _mark_lvalue_roles(node.get("leftHandSide"), states, roles, "write")
            elif isinstance(operator, str):
                _mark_lvalue_roles(node.get("leftHandSide"), states, roles, "read_write")
        elif node.get("nodeType") == "UnaryOperation" and node.get("operator") in {"++", "--", "delete"}:
            _mark_lvalue_roles(node.get("subExpression"), states, roles,
                                "read_write" if node.get("operator") in {"++", "--"} else "write")
    return roles


def _extract_direct(ast: dict[str, Any], file: str, global_function_nodes: dict[int, dict[str, Any]]) -> tuple[list[SemanticRelationshipEvidence], dict[int, set[int]]]:
    """Extract compiler-linked state reads/writes from AST operator context.

    Declaration IDs are authoritative. Canonical SystemModel relation names are used
    for projection: ``reads``, ``writes`` and ``transition_expression``. The precise
    semantic role is also retained in edge metadata, so read/write context is never lost.
    """
    declarations: dict[int, dict[str, Any]] = {}
    states: dict[int, str] = {}
    for node in _walk(ast):
        node_id = node.get("id")
        if isinstance(node_id, int):
            declarations[node_id] = node
        if (
            node.get("nodeType") == "VariableDeclaration"
            and node.get("stateVariable") is True
            and node.get("mutability", "mutable") not in {"constant", "immutable"}
        ):
            if isinstance(node.get("name"), str) and isinstance(node_id, int):
                states[node_id] = node["name"]

    evidence: list[SemanticRelationshipEvidence] = []
    for node in _walk(ast):
        if node.get("nodeType") != "FunctionDefinition" or not isinstance(node.get("id"), int):
            continue
        function_id = node["id"]
        kind = node.get("kind")
        function_name = (node.get("name") if isinstance(node.get("name"), str) and node.get("name")
                         else kind if kind in {"constructor", "receive", "fallback"} else "anonymous")
        scope = node.get("scope")
        contract = declarations.get(scope, {}).get("name", "unknown") if isinstance(scope, int) else "unknown"
        body = node.get("body")
        if not isinstance(body, dict):
            continue
        roles = _operator_contexts(body, states)
        # Dispatch state mutations through the write-form capability list. Keep
        # extract_target() string-compatible and preserve indexed keys separately.
        write_method_by_identifier: dict[int, str] = {}
        write_args_by_identifier: dict[int, list[str]] = {}
        write_forms = (
            ScalarWrite(states),
            NestedMappingWrite(states),
            ArrayPushWrite(states),
        )

        def storage_root(node: Any) -> dict[str, Any] | None:
            current = node
            while isinstance(current, dict) and current.get("nodeType") == "IndexAccess":
                current = current.get("baseExpression")
            return current if isinstance(current, dict) and current.get("nodeType") == "Identifier" else None

        for candidate in _walk(body):
            for form in write_forms:
                if not form.matches(candidate):
                    continue
                target_name = form.extract_target(candidate)
                if not target_name:
                    continue
                if candidate.get("nodeType") == "Assignment":
                    root = storage_root(candidate.get("leftHandSide"))
                    operator = candidate.get("operator")
                    if operator != "=" and root is not None:
                        roles[_node_id(root)] = "read_write" if _node_id(root) is not None else roles.get(_node_id(root), "read")
                    elif root is not None and _node_id(root) is not None:
                        roles[_node_id(root)] = "write"
                else:
                    callee = candidate.get("expression")
                    receiver = callee.get("expression") if isinstance(callee, dict) else None
                    root = storage_root(receiver)
                    if root is not None and _node_id(root) is not None:
                        roles[_node_id(root)] = "write"
                if root is not None and _node_id(root) is not None:
                    write_method_by_identifier[_node_id(root)] = type(form).__name__
                    write_args_by_identifier[_node_id(root)] = form.extract_args(candidate)
                break
        # Yul storage operations are not represented as Solidity VariableDeclaration
        # references. Record them as opaque, function-scoped effects; never equate
        # unrelated dynamic slot expressions or promote them directly to findings.
        for yul_call in _walk(body):
            if yul_call.get("nodeType") != "YulFunctionCall":
                continue
            function_node = yul_call.get("functionName")
            operation = function_node.get("name") if isinstance(function_node, dict) else None
            if operation not in {"sstore", "sload", "tstore", "tload"}:
                continue
            args = yul_call.get("arguments", [])
            rendered = [_yul_expression(arg) for arg in args] if isinstance(args, list) else []
            slot_expression = rendered[0] if rendered else "unknown"
            relation = "writes" if operation in {"sstore", "tstore"} else "reads"
            evidence.append(SemanticRelationshipEvidence(
                contract=str(contract), function=str(function_name), relation=relation,
                target=f"YUL_SLOT:{function_name}:{slot_expression}",
                confidence=0.75, source=f"solc-json-ast-yul:{file}",
                ast_node_id=_node_id(yul_call), source_location=_location(yul_call),
                function_ast_node_id=function_id,
                metadata={
                    "function_kind": kind, "semantic_relation": relation,
                    "storage_operation": operation, "storage_slot_expression": slot_expression,
                    "storage_slot_comparable": False, "evidence_scope": "opaque-yul",
                },
            ))
        for item in _walk(body):
            if item.get("nodeType") != "Identifier":
                continue
            ref = item.get("referencedDeclaration")
            if not isinstance(ref, int) or ref not in states:
                continue
            item_id = _node_id(item)
            semantic_role = roles.get(item_id, "read") if item_id is not None else "read"
            relation = {"read": "reads", "write": "writes", "read_write": "transition_expression"}[semantic_role]
            common = dict(contract=str(contract), function=str(function_name), relation=relation,
                          target=states[ref], confidence=0.98 if item_id in roles else 0.90,
                          source=f"solc-json-ast:{file}", ast_node_id=item_id,
                          source_location=_location(item), function_ast_node_id=function_id,
                          target_ast_node_id=ref,
                          metadata={
                              "function_kind": kind,
                              "semantic_relation": semantic_role,
                              **({"write_method": write_method_by_identifier[item_id]}
                                 if item_id in write_method_by_identifier else {}),
                              **({"write_args": write_args_by_identifier[item_id]}
                                 if item_id in write_args_by_identifier else {}),
                          })
            evidence.append(SemanticRelationshipEvidence(**common))
            evidence.append(SemanticRelationshipEvidence(
                **{**common, "relation": "reference", "confidence": 0.90,
                   "metadata": {"function_kind": kind, "semantic_relation": semantic_role}}))

    local_function_nodes = {node["id"]: node for node in _walk(ast)
        if node.get("nodeType") == "FunctionDefinition" and isinstance(node.get("id"), int)}
    calls_by_function: dict[int, set[int]] = {function_id: set() for function_id in local_function_nodes}
    for function_id, node in local_function_nodes.items():
        body = node.get("body")
        if not isinstance(body, dict): continue
        for call in _walk(body):
            if call.get("nodeType") != "FunctionCall": continue
            expression = call.get("expression")
            if not isinstance(expression, dict) or expression.get("nodeType") != "Identifier": continue
            callee_id = expression.get("referencedDeclaration")
            if isinstance(callee_id, int) and callee_id in global_function_nodes and callee_id != function_id:
                calls_by_function[function_id].add(callee_id)
    return evidence, calls_by_function


def _dedup_provenance(evidence: list[SemanticRelationshipEvidence]) -> tuple[SemanticRelationshipEvidence, ...]:
    seen: set[tuple[int | None, str, str]] = set()
    result: list[SemanticRelationshipEvidence] = []
    for item in evidence:
        key = (item.function_ast_node_id, item.target, item.relation)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return tuple(result)


def _fixed_point_propagate(global_calls: dict[int, set[int]],
    effects_by_function: dict[int, list[SemanticRelationshipEvidence]],
    global_function_nodes: dict[int, dict[str, Any]], declarations: dict[int, dict[str, Any]],
    function_files: dict[int, str]) -> list[SemanticRelationshipEvidence]:
    propagated: list[SemanticRelationshipEvidence] = []
    seen = {(item.function_ast_node_id, item.target, item.relation)
        for items in effects_by_function.values() for item in items
        if item.relation in {"reads", "writes", "transition_expression"}}
    changed = True
    while changed:
        changed = False
        for caller_id, callees in global_calls.items():
            caller = global_function_nodes.get(caller_id)
            if caller is None: continue
            caller_kind = caller.get("kind")
            caller_name = caller.get("name") or caller_kind or "anonymous"
            body = caller.get("body")
            call_sites: dict[int, list[dict[str, Any]]] = {}
            if isinstance(body, dict):
                for call in _walk(body):
                    expression = call.get("expression")
                    if call.get("nodeType") == "FunctionCall" and isinstance(expression, dict) and expression.get("nodeType") == "Identifier":
                        callee_id = expression.get("referencedDeclaration")
                        if isinstance(callee_id, int) and callee_id in callees:
                            call_sites.setdefault(callee_id, []).append(call)
            for callee_id in callees:
                sites = call_sites.get(callee_id, [])
                if not sites: continue
                for effect in tuple(effects_by_function.get(callee_id, ())):
                    if effect.relation not in {"reads", "writes", "transition_expression"}: continue
                    key = (caller_id, effect.target, effect.relation)
                    if key in seen: continue
                    seen.add(key)
                    callee = global_function_nodes.get(callee_id, {})
                    inherited = (effect.metadata or {}).get("propagated_from_internal_call")
                    propagated_from = inherited or callee.get("name") or callee.get("kind") or "anonymous"
                    scope = caller.get("scope")
                    contract = declarations.get(scope, {}).get("name", "unknown") if isinstance(scope, int) else "unknown"
                    item = SemanticRelationshipEvidence(contract=str(contract), function=str(caller_name),
                        relation=effect.relation, target=effect.target, confidence=min(effect.confidence, 0.94),
                        source=f"solc-json-ast-internal-call:{function_files.get(caller_id, 'unknown')}",
                        ast_node_id=_node_id(sites[0]), source_location=_location(sites[0]),
                        function_ast_node_id=caller_id, target_ast_node_id=effect.target_ast_node_id,
                        metadata={"function_kind": caller_kind,
                            "semantic_relation": (effect.metadata or {}).get("semantic_relation", effect.relation),
                            "propagated_from_internal_call": propagated_from,
                            "propagation": "transitive-internal-call" if inherited else "internal-call"})
                    effects_by_function.setdefault(caller_id, []).append(item)
                    propagated.append(item)
                    changed = True
    return propagated


def extract_compilation_relationships(asts: list[tuple[str, dict[str, Any]]] | list[dict[str, Any]]) -> tuple[SemanticRelationshipEvidence, ...]:
    """Extract direct relationships then propagate effects over the compilation-wide call graph."""
    normalized: list[tuple[str, dict[str, Any]]] = []
    for index, value in enumerate(asts):
        if isinstance(value, tuple) and len(value) == 2 and isinstance(value[1], dict):
            normalized.append((str(value[0]), value[1]))
        elif isinstance(value, dict):
            normalized.append((f"source-{index}.sol", value))
    global_function_nodes: dict[int, dict[str, Any]] = {}
    declarations: dict[int, dict[str, Any]] = {}
    function_files: dict[int, str] = {}
    for file, ast in normalized:
        for node in _walk(ast):
            node_id = node.get("id")
            if isinstance(node_id, int): declarations[node_id] = node
            if node.get("nodeType") == "FunctionDefinition" and isinstance(node_id, int):
                global_function_nodes[node_id] = node
                function_files[node_id] = file
    all_evidence: list[SemanticRelationshipEvidence] = []
    effects_by_function: dict[int, list[SemanticRelationshipEvidence]] = {}
    global_calls: dict[int, set[int]] = {}
    for file, ast in normalized:
        direct, edges = _extract_direct(ast, file, global_function_nodes)
        all_evidence.extend(direct)
        for item in direct:
            if item.function_ast_node_id is not None and item.relation != "reference":
                effects_by_function.setdefault(item.function_ast_node_id, []).append(item)
        for caller_id, callees in edges.items(): global_calls.setdefault(caller_id, set()).update(callees)
    all_evidence.extend(_fixed_point_propagate(global_calls, effects_by_function, global_function_nodes, declarations, function_files))
    return _dedup_provenance(all_evidence)


def extract_ast_relationships(ast: dict[str, Any], file: str) -> list[SemanticRelationshipEvidence]:
    """Backward-compatible wrapper for single-AST callers."""
    return list(extract_compilation_relationships([(file, ast)]))
