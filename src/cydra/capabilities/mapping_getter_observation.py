"""Fail-closed observation through source-backed mapping getters."""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .observation import ObservationMethod


class MappingGetterObservation(ObservationMethod):
    """Read mapping state only through a matching public/getX getter.

    Custom semantic readers such as isValidator are deliberately deferred to
    a later observation strategy. No raw-storage fallback is attempted.
    """

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
    def _mapping_decl(source: str, name: str) -> tuple[str, int] | None:
        for match in re.finditer(r"\bmapping\s*\(", source):
            open_pos = source.find("(", match.start())
            depth = 0
            close_pos = None
            for pos in range(open_pos, len(source)):
                if source[pos] == "(":
                    depth += 1
                elif source[pos] == ")":
                    depth -= 1
                    if depth == 0:
                        close_pos = pos
                        break
            if close_pos is None:
                continue
            tail = source[close_pos + 1:]
            decl = re.match(
                r"\s*(?:(public|private|internal)\s+)?"
                + re.escape(name) + r"\s*;",
                tail,
            )
            if not decl:
                continue
            mapping_type = source[match.start():close_pos + 1]
            arity = len(re.findall(r"\bmapping\s*\(", mapping_type))
            return (decl.group(1) or "internal", arity)
        return None

    @staticmethod
    def _view_reader(source: str, state_name: str) -> tuple[str, int] | None:
        pattern = re.compile(
            r"function\s+(\w+)\s*\(([^)]*)\)[^{;]*\bview\b[^{}]*\{([^{}]*)\}",
            re.S,
        )
        for match in pattern.finditer(source):
            name, params, body = match.groups()
            # Day 5 supports conventional getX readers only. isX/custom
            # semantic readers belong to ExplicitViewReaderObservation.
            if not re.fullmatch(r"get[A-Z]\w*", name):
                continue
            if not re.search(r"\b" + re.escape(state_name) + r"\s*\[", body):
                continue
            arity = 0 if not params.strip() else len(params.split(","))
            return name, arity
        return None

    def resolve(self, write: Any) -> tuple[str, int] | None:
        name = self._write_name(write)
        if not name:
            return None
        decl = self._mapping_decl(self.source_text, name)
        if decl is None:
            return None
        visibility, arity = decl
        if self.getter_name is not None:
            reader = self._view_reader(self.source_text, name)
            if reader and reader[0] == self.getter_name:
                return reader
            if visibility == "public" and self.getter_name == name:
                return name, arity
            return None
        if visibility == "public":
            return name, arity
        return self._view_reader(self.source_text, name)

    def can_observe(self, write: Any) -> bool:
        return self.resolve(write) is not None

    def emit_probe(self, write: Any, args: list[str] | None = None) -> str:
        resolved = self.resolve(write)
        if resolved is None:
            self.last_reason = "getter_not_found"
            return ""
        name, arity = resolved
        call_args = args or []
        if len(call_args) != arity:
            self.last_reason = "arg_arity_mismatch"
            return ""
        self.last_reason = None
        return f"target.{name}({', '.join(call_args)})"

    def _runtime_getter_name(self, candidates: Mapping[Any, Any]) -> str | None:
        if self.getter_name is not None:
            return self.getter_name
        # Accept only a source-declared public mapping getter or conventional
        # getX view reader; never select an arbitrary single candidate.
        for name in candidates:
            if not isinstance(name, str):
                continue
            if re.search(
                r"\bmapping\s*\([^;]*?\)\s*public\s+"
                + re.escape(name) + r"\s*;",
                self.source_text,
                re.S,
            ):
                return name
            if re.fullmatch(r"get[A-Z]\w*", name) and re.search(
                r"function\s+" + re.escape(name) + r"\s*\([^)]*\)[^{;]*\bview\b",
                self.source_text,
                re.S,
            ):
                return name
        return None

    def read_state(self, context: Any, args: list[Any] | None = None) -> Any:
        self.last_reason = None
        call_args = args or []
        getter = context if callable(context) else None
        if getter is None and isinstance(context, Mapping):
            candidates = context.get("getters")
            if isinstance(candidates, Mapping):
                name = self._runtime_getter_name(candidates)
                candidate = candidates.get(name) if name is not None else None
                if callable(candidate):
                    getter = candidate
            direct = context.get("getter")
            if getter is None and callable(direct) and self.getter_name is not None:
                getter = direct
        if getter is None:
            self.last_reason = "getter_not_found"
            return None
        try:
            return getter(*call_args)
        except TypeError:
            self.last_reason = "arg_arity_mismatch"
            return None
        except Exception:
            self.last_reason = "call_reverted"
            return None
