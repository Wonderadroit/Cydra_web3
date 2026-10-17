"""Observation strategy for exact-name public scalar getters.

When multiple runtime getter candidates are supplied without an explicit
getter name, the fallback is deterministic: choose the lexicographically
smallest callable name. Callers that know the source-backed getter should
pass its exact name; no fallback is attempted when that exact name is absent.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .observation import ObservationMethod


class PublicGetterObservation(ObservationMethod):
    """Resolve public scalar getters and read them fail-closed."""

    _SCALAR_DECLARATION = (
        r"\b(address(?:\s+payable)?|bool|uint\d*|int\d*|bytes\d*)\s+public\s+"
    )

    def __init__(self, source_text: str = "", *, getter_name: str | None = None):
        self.source_text = source_text
        self.getter_name = getter_name
        self.last_reason: str | None = None

    @staticmethod
    def _write_name(write: Any) -> str | None:
        if isinstance(write, str):
            return write
        if isinstance(write, Mapping):
            value = write.get("name", write.get("target"))
        else:
            value = getattr(write, "name", getattr(write, "target", None))
        return value if isinstance(value, str) and value else None

    def resolve(self, write: Any) -> tuple[str, str] | None:
        """Return exact getter name and Solidity scalar type, or None."""
        name = self._write_name(write)
        if not name:
            return None
        pattern = re.compile(
            self._SCALAR_DECLARATION + re.escape(name) + r"\s*;"
        )
        match = pattern.search(self.source_text)
        if match is None:
            return None
        return name, match.group(1).strip()

    def can_observe(self, write: Any) -> bool:
        return self.resolve(write) is not None

    def emit_probe(self, write: Any) -> str:
        resolved = self.resolve(write)
        if resolved is None:
            return ""
        return f"target.{resolved[0]}()"

    def read_state(self, context: Any) -> Any:
        """Read a supplied getter; return None and record a reason on failure.

        Context may be a getter callable or a mapping containing a getters
        mapping. If this instance has getter_name, only that exact candidate is
        eligible. Otherwise names are sorted and the first callable is chosen.
        """
        self.last_reason = None
        getter = context if callable(context) else None
        if getter is None and isinstance(context, Mapping):
            direct = context.get("getter")
            candidates = context.get("getters")
            if callable(direct) and not candidates:
                getter = direct
            elif isinstance(candidates, Mapping):
                if self.getter_name is not None:
                    candidate = candidates.get(self.getter_name)
                    if callable(candidate):
                        getter = candidate
                else:
                    eligible = sorted(
                        (name, candidate)
                        for name, candidate in candidates.items()
                        if isinstance(name, str) and callable(candidate)
                    )
                    if eligible:
                        getter = eligible[0][1]
        if getter is None:
            self.last_reason = "getter_unavailable"
            return None
        try:
            return getter()
        except Exception as exc:
            self.last_reason = f"getter_reverted:{type(exc).__name__}"
            return None
