"""Abstract interface for recognizing and extracting state-write forms.

Implementations may receive analysis context (such as the compiler's
state-variable declaration-ID map) through their constructor. Keep that
injection in the implementation: the stable matches and extract_target
method signatures do not carry hidden global state.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class WriteForm(ABC):
    @abstractmethod
    def matches(self, ast_node: Any) -> bool:
        """Return whether the AST node has this write form."""
        raise NotImplementedError

    @abstractmethod
    def extract_target(self, ast_node: Any) -> str | None:
        """Extract the written state target, or return None when unresolved."""
        raise NotImplementedError
