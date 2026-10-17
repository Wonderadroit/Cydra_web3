"""Recognition of nested mapping/indexed state-variable assignments."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .write_form import WriteForm


class NestedMappingWrite(WriteForm):
    """Extract a state-variable root from one or more indexed assignments.

    state_vars maps compiler declaration IDs to state variable names.
    The LHS must be an Assignment whose left side is one or more nested
    IndexAccess nodes rooted directly in a state-variable Identifier.
    MemberAccess roots are deliberately rejected, so a local struct field
    that happens to contain a mapping cannot be mistaken for contract state.
    """

    _ASSIGNMENT_OPERATORS = {"=", "+=", "-=", "*=", "/=", "%="}

    def __init__(self, state_vars: Mapping[int, str]):
        self.state_vars = dict(state_vars)

    @staticmethod
    def _get(node: Any, key: str, default: Any = None) -> Any:
        if isinstance(node, Mapping):
            return node.get(key, default)
        return getattr(node, key, default)

    def _target(self, ast_node: Any) -> str | None:
        if self._get(ast_node, "nodeType") != "Assignment":
            return None
        if self._get(ast_node, "operator") not in self._ASSIGNMENT_OPERATORS:
            return None

        lhs = self._get(ast_node, "leftHandSide")
        saw_index = False
        while self._get(lhs, "nodeType") == "IndexAccess":
            saw_index = True
            lhs = self._get(lhs, "baseExpression")

        if not saw_index or self._get(lhs, "nodeType") != "Identifier":
            return None
        declaration_id = self._get(lhs, "referencedDeclaration")
        if not isinstance(declaration_id, int):
            return None
        return self.state_vars.get(declaration_id)

    def matches(self, ast_node: Any) -> bool:
        return self._target(ast_node) is not None

    def extract_target(self, ast_node: Any) -> str | None:
        return self._target(ast_node)

    def extract_args(self, ast_node: Any) -> list[str]:
        """Return nested index expressions in source order."""
        if not self.matches(ast_node):
            return []
        lhs = self._get(ast_node, "leftHandSide")
        indexes = []
        while self._get(lhs, "nodeType") == "IndexAccess":
            indexes.append(self._get(lhs, "indexExpression"))
            lhs = self._get(lhs, "baseExpression")
        indexes.reverse()
        return [self._expression_name(item) for item in indexes]

    @classmethod
    def _expression_name(cls, node: Any) -> str:
        kind = cls._get(node, "nodeType")
        if kind == "Identifier":
            return str(cls._get(node, "name", ""))
        if kind == "Literal":
            return str(cls._get(node, "value", ""))
        return ""
