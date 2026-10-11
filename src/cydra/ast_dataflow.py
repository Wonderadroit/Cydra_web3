from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator


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


def extract_ast_relationships(ast: dict[str, Any], file: str) -> list[SemanticRelationshipEvidence]:
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
                          metadata={"function_kind": kind, "semantic_relation": semantic_role})
            evidence.append(SemanticRelationshipEvidence(**common))
            evidence.append(SemanticRelationshipEvidence(
                **{**common, "relation": "reference", "confidence": 0.90,
                   "metadata": {"function_kind": kind, "semantic_relation": semantic_role}}))
# Attribute state effects of same-source internal calls to their callers. A
    # public setter that delegates its storage mutation to a private/internal
    # helper still changes that state; omitting this edge can hide protected
    # state transitions from authorization reasoning. Keep this conservative:
    # only direct identifier calls resolving to a FunctionDefinition in this
    # AST are propagated (not arbitrary external/member calls).
    function_nodes = {
        node["id"]: node
        for node in _walk(ast)
        if node.get("nodeType") == "FunctionDefinition" and isinstance(node.get("id"), int)
    }
    function_names = {
        function_id: (
            node.get("name") if isinstance(node.get("name"), str) and node.get("name")
            else node.get("kind", "anonymous")
        )
        for function_id, node in function_nodes.items()
    }
    calls_by_function: dict[int, set[int]] = {function_id: set() for function_id in function_nodes}
    for function_id, node in function_nodes.items():
        body = node.get("body")
        if not isinstance(body, dict):
            continue
        for call in _walk(body):
            if call.get("nodeType") != "FunctionCall":
                continue
            expression = call.get("expression")
            if not isinstance(expression, dict) or expression.get("nodeType") != "Identifier":
                continue
            callee_id = expression.get("referencedDeclaration")
            if isinstance(callee_id, int) and callee_id in function_nodes and callee_id != function_id:
                calls_by_function[function_id].add(callee_id)

    # Fixed-point closure handles helper chains while the seen key prevents
    # recursive internal calls from producing duplicate or unbounded evidence.
    seen_effects = {
        (item.function_ast_node_id, item.relation, item.target, item.target_ast_node_id)
        for item in evidence
        if item.relation != "reference"
    }
    changed = True
    while changed:
        changed = False
        for caller_id, callees in calls_by_function.items():
            caller = function_nodes[caller_id]
            caller_kind = caller.get("kind")
            caller_name = function_names[caller_id]
            for callee_id in callees:
                call_sites = []
                body = caller.get("body")
                if isinstance(body, dict):
                    for call in _walk(body):
                        expression = call.get("expression")
                        if (
                            call.get("nodeType") == "FunctionCall"
                            and isinstance(expression, dict)
                            and expression.get("nodeType") == "Identifier"
                            and expression.get("referencedDeclaration") == callee_id
                        ):
                            call_sites.append(call)
                callee_effects = [
                    item for item in evidence
                    if item.function_ast_node_id == callee_id
                    and item.relation in {"reads", "writes", "transition_expression"}
                ]
                for call_site in call_sites:
                    for effect in callee_effects:
                        key = (caller_id, effect.relation, effect.target, effect.target_ast_node_id)
                        if key in seen_effects:
                            continue
                        seen_effects.add(key)
                        inherited = (effect.metadata or {}).get("propagated_from_internal_call")
                        propagated_from = inherited or function_names[callee_id]
                        evidence.append(SemanticRelationshipEvidence(
                            contract=str(
                                declarations.get(caller.get("scope"), {}).get("name", "unknown")
                                if isinstance(caller.get("scope"), int) else "unknown"
                            ),
                            function=str(caller_name),
                            relation=effect.relation,
                            target=effect.target,
                            confidence=min(effect.confidence, 0.94),
                            source=f"solc-json-ast-internal-call:{file}",
                            ast_node_id=_node_id(call_site),
                            source_location=_location(call_site),
                            function_ast_node_id=caller_id,
                            target_ast_node_id=effect.target_ast_node_id,
                            metadata={
                                "function_kind": caller_kind,
                                "semantic_relation": (effect.metadata or {}).get("semantic_relation", effect.relation),
                                "propagated_from_internal_call": propagated_from,
                                "propagation": "transitive-internal-call" if inherited else "internal-call",
                            },
                        ))
                        changed = True
    return evidence


