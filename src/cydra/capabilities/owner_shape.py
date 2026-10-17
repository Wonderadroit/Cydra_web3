"""Source-backed owner() authority shape, preserving the legacy resolver behavior."""
from __future__ import annotations

import re
from typing import Any

from .authority_shape import AuthorityShape


class OwnerShape(AuthorityShape):
    """Resolve an owner variable referenced by a recognized modifier guard.

    This intentionally mirrors the previous inline owner-principal detection:
    it requires a modifier applied to the function, a sender equality check, and
    a public address state declaration. It does not infer ownership from names.
    """

    def resolve_authorized(self, source_text: str, function: Any) -> str | None:
        modifier_bodies = {
            match.group(1): match.group(2)
            for match in re.finditer(
                r"\bmodifier\s+([A-Za-z_]\w*)\s*\([^)]*\)\s*\{([^{}]*)\}",
                source_text,
                re.DOTALL,
            )
        }
        for modifier in function.modifiers:
            body = modifier_bodies.get(modifier)
            if body is None:
                continue
            guard = re.search(
                r"\bmsg\s*\.\s*sender\s*==\s*([A-Za-z_]\w*)|"
                r"\b([A-Za-z_]\w*)\s*==\s*msg\s*\.\s*sender\b",
                body,
            )
            if guard:
                candidate = guard.group(1) or guard.group(2)
                if re.search(
                    rf"\baddress(?:\s+payable)?\s+public\s+{re.escape(candidate)}\s*;",
                    source_text,
                ):
                    return candidate
        return None

    def detect(self, source_text: str, function: Any) -> bool:
        return self.resolve_authorized(source_text, function) is not None

    def verify_role(self, source_text: str, function: Any) -> bool:
        # OwnerShape is not a role-based shape; no role semantics are inferred.
        return False
