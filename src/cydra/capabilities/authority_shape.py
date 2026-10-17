"""Abstract authority-shape interface; implementations must preserve source evidence."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AuthorityShape(ABC):
    @abstractmethod
    def detect(self, source_text: str, function: Any) -> bool:
        """Return whether this shape is evidenced for the supplied function."""
        raise NotImplementedError

    @abstractmethod
    def resolve_authorized(self, source_text: str, function: Any) -> str | None:
        """Resolve a privileged actor only when source evidence supports it."""
        raise NotImplementedError

    @abstractmethod
    def verify_role(self, source_text: str, function: Any) -> bool:
        """Verify role-based authorization evidence; do not infer from names alone."""
        raise NotImplementedError
