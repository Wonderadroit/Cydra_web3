"""Recognition of push/pop calls rooted in compiler-identified state variables."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .write_form import WriteForm


class ArrayPushWrite(WriteForm):
    """Extract the state-variable root of an array push/pop method call.

    state_vars maps compiler declaration IDs to state-variable names. The
    call must be a FunctionCall whose callee is a MemberAccess named push or
    pop, and the member receiver must resolve through zero or more IndexAccess
    nodes to a state-variable Identifier. This returns the base state variable
    (for example, _validators for _validators[virtualId].push(value)), never
    the indexed entry or a local variable with the same spelling.
    """

    _MUTATORS = {"push", "pop"}

    def __init__(self, state_vars: Mapping[int, str]):
        self.state_vars = dict(state_vars)

    @staticmethod
    def _get(node: Any, key: str, default: Any = None) -> Any:
        if isinstance(node, Mapping):
            return node.get(key, default)
        return getattr(node, key, default)

    def _target(self, ast_node: Any) -> str | None:
        if self._get(ast_node, "nodeType") != "FunctionCall":
            return None

        callee = self._get(ast_node, "expression")
        if self._get(callee, "nodeType") != "MemberAccess":
            return None
        if self._get(callee, "memberName") not in self._MUTATORS:
            return None

        receiver = self._get(callee, "expression")
        while self._get(receiver, "nodeType") == "IndexAccess":
            receiver = self._get(receiver, "baseExpression")

        if self._get(receiver, "nodeType") != "Identifier":
            return None
        declaration_id = self._get(receiver, "referencedDeclaration")
        if not isinstance(declaration_id, int):
            return None
        return self.state_vars.get(declaration_id)

    def matches(self, ast_node: Any) -> bool:
        return self._target(ast_node) is not None

    def extract_target(self, ast_node: Any) -> str | None:
        return self._target(ast_node)
