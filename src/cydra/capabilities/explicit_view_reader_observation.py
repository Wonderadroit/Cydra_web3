"""Observation through source-backed explicit view readers.

This strategy is intentionally separate from MappingGetterObservation:
it supports semantic readers such as isValidator(id, account), but only when
the view function body directly indexes the modeled mapping root.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .observation import ObservationMethod


class ExplicitViewReaderObservation(ObservationMethod):
    """Resolve and call an explicit view reader for a mapping state root."""

    _SCALAR_RETURN = r"(address(?:\s+payable)?|bool|uint\d*|int\d*|bytes\d*)"

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

    @staticmethod
    def _body(source: str, open_brace: int) -> str | None:
        depth = 0
        for pos in range(open_brace, len(source)):
            if source[pos] == "{":
                depth += 1
            elif source[pos] == "}":
                depth -= 1
                if depth == 0:
                    return source[open_brace + 1:pos]
        return None

    def _candidates(self, write: Any) -> list[tuple[str, int, str]]:
        state_name = self._write_name(write)
        if not state_name:
            return []
        # Keep the reader signature and body in one match; nested mapping
        # access is accepted, while unrelated mentions in comments/signatures
        # do not count as evidence of a read.
        pattern = re.compile(
            r"\bfunction\s+([A-Za-z_]\w*)\s*\(([^)]*)\)"
            r"([^{};]*)\{",
            re.S,
        )
        candidates: list[tuple[str, int, str]] = []
        for match in pattern.finditer(self.source_text):
            name, params, qualifiers = match.group(1), match.group(2), match.group(3)
            if not re.search(r"\b(?:public|external)\b", qualifiers):
                continue
            if not re.search(r"\bview\b", qualifiers):
                continue
            open_brace = match.end() - 1
            body = self._body(self.source_text, open_brace)
            if body is None:
                continue
            if not re.search(r"\b" + re.escape(state_name) + r"\s*\[", body):
                continue
            return_match = re.search(r"\breturns\s*\(\s*" + self._SCALAR_RETURN, qualifiers)
            if return_match is None:
                continue
            arity = 0 if not params.strip() else len(params.split(","))
            candidates.append((name, arity, return_match.group(1).strip()))
        return sorted(candidates, key=lambda item: item[0])

    def resolve(self, write: Any) -> tuple[str, int, str] | None:
        candidates = self._candidates(write)
        if self.getter_name is not None:
            return next((item for item in candidates if item[0] == self.getter_name), None)
        return candidates[0] if candidates else None

    def can_observe(self, write: Any) -> bool:
        return self.resolve(write) is not None

    def emit_probe(self, write: Any, args: list[str] | None = None) -> str:
        resolved = self.resolve(write)
        if resolved is None:
            self.last_reason = "getter_not_found"
            return ""
        name, arity, _return_type = resolved
        call_args = args or []
        if len(call_args) != arity:
            self.last_reason = "arg_arity_mismatch"
            return ""
        self.last_reason = None
        return f"target.{name}({', '.join(call_args)})"

    def read_state(self, context: Any, args: list[Any] | None = None) -> Any:
        self.last_reason = None
        resolved_name = None
        if isinstance(context, Mapping):
            source_candidates = context.get("getter_names")
            if isinstance(source_candidates, (list, tuple)):
                if self.getter_name is not None:
                    resolved_name = self.getter_name if self.getter_name in source_candidates else None
                elif source_candidates:
                    resolved_name = sorted(
                        name for name in source_candidates if isinstance(name, str)
                    )[0]
        if resolved_name is None:
            resolved = self.getter_name
            if resolved is None:
                self.last_reason = "getter_not_found"
                return None
            resolved_name = resolved
        getter = None
        if isinstance(context, Mapping):
            getters = context.get("getters")
            if isinstance(getters, Mapping):
                candidate = getters.get(resolved_name)
                if callable(candidate):
                    getter = candidate
        if getter is None:
            self.last_reason = "getter_not_found"
            return None
        try:
            return getter(*(args or []))
        except TypeError:
            self.last_reason = "arg_arity_mismatch"
            return None
        except Exception:
            self.last_reason = "call_reverted"
            return None
