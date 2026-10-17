"""Abstract interface for recognizing and extracting state-write forms."""
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
