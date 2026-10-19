"""Abstract interface for observing state affected by a candidate write."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ObservationMethod(ABC):
    @abstractmethod
    def can_observe(self, write: Any) -> bool:
        """Whether the modeled write has a source-backed observer."""
        raise NotImplementedError

    @abstractmethod
    def emit_probe(self, write: Any, args: list[str] | None = None) -> str:
        """Render a probe using source-backed getter arguments when required."""
        raise NotImplementedError

    @abstractmethod
    def read_state(self, context: Any, args: list[Any] | None = None) -> Any:
        """Read observed state from the supplied execution context."""
        raise NotImplementedError
