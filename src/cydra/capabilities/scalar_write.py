"""Recognition of direct scalar assignments to compiler-identified state vars."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .write_form import WriteForm


class ScalarWrite(WriteForm):
    """Match direct state-identifier assignments using injected declaration IDs.

    state_vars maps Solidity compiler declaration IDs to state variable names.
    Using declaration IDs, rather than identifier text, prevents a local
    variable that shadows a state variable from being misclassified as a write.
    Member access and indexed lvalues are intentionally left to future write
    forms such as StructFieldWrite and NestedMappingWrite.
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
        if self._get(lhs, "nodeType") != "Identifier":
            return None
        declaration_id = self._get(lhs, "referencedDeclaration")
        if not isinstance(declaration_id, int):
            return None
        return self.state_vars.get(declaration_id)

    def matches(self, ast_node: Any) -> bool:
        return self._target(ast_node) is not None

    def extract_target(self, ast_node: Any) -> str | None:
        return self._target(ast_node)
