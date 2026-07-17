"""Hyphae-value flag registry — the binding substrate for tools and lenses.

The vision (``docs/wiki/60-canonical-datum-and-hyphae-flags.md``): a datum's
*canonical hyphae value* (the address-independent fold of its minimum-but-complete
abstraction path, see :func:`core.datum_semantics.compile_hyphae_value`) is matched
against a registry of **flags**. When a datum's compiled hyphae value matches a
registered value, the flag "is raised" — binding a tool and/or a lens to that
datum (and, by ``family_root`` scope, to a whole family) *by content*, not by the
coarse archetype / family-string buckets used today.

This module is the pure, store-agnostic registry. It depends only on
``core.datum_semantics`` (to compile values) + the standard library. It is seeded
**empty**: with no flags registered, ``raise_flags`` returns nothing and every
flag-aware consumer (lens resolver, tool eligibility) behaves exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from micyte.core.datum_semantics import compile_hyphae_value

DATUM_SCOPE = "datum"
FAMILY_ROOT_SCOPE = "family_root"
_VALID_SCOPES = (DATUM_SCOPE, FAMILY_ROOT_SCOPE)


@dataclass(frozen=True)
class HyphaeFlag:
    """A registered binding keyed on a canonical hyphae value.

    At least one of ``tool_id`` / ``lens_id`` must be set — a flag with neither
    binds nothing and is rejected at registration.
    """

    hyphae_value: str
    scope: str = DATUM_SCOPE
    tool_id: str = ""
    lens_id: str = ""
    label: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if not self.hyphae_value:
            raise ValueError("HyphaeFlag.hyphae_value is required")
        if self.scope not in _VALID_SCOPES:
            raise ValueError(f"HyphaeFlag.scope must be one of {_VALID_SCOPES}: {self.scope!r}")
        if not (self.tool_id or self.lens_id):
            raise ValueError("HyphaeFlag must bind at least one of tool_id / lens_id")


@dataclass(frozen=True)
class RaisedFlag:
    """The result of a datum's hyphae value matching one or more registered flags."""

    datum_address: str
    hyphae_value: str
    scope: str
    tool_ids: tuple[str, ...] = ()
    lens_id: str = ""


@dataclass
class HyphaeFlagRegistry:
    """A pure ``hyphae_value -> [HyphaeFlag]`` registry."""

    _by_value: dict[str, list[HyphaeFlag]] = field(default_factory=dict)

    def register(self, flag: HyphaeFlag) -> None:
        self._by_value.setdefault(flag.hyphae_value, []).append(flag)

    def flags_for(self, hyphae_value: str) -> tuple[HyphaeFlag, ...]:
        return tuple(self._by_value.get(hyphae_value, ()))

    def is_empty(self) -> bool:
        return not self._by_value

    def clear(self) -> None:
        self._by_value.clear()

    def raise_for_value(self, *, datum_address: str, hyphae_value: str) -> RaisedFlag | None:
        """Raise the merged flag for an already-compiled ``hyphae_value`` (or None)."""
        flags = self.flags_for(hyphae_value)
        if not flags:
            return None
        tool_ids = tuple(dict.fromkeys(f.tool_id for f in flags if f.tool_id))
        lens_id = next((f.lens_id for f in flags if f.lens_id), "")
        scope = next((f.scope for f in flags if f.scope == FAMILY_ROOT_SCOPE), flags[0].scope)
        return RaisedFlag(
            datum_address=datum_address,
            hyphae_value=hyphae_value,
            scope=scope,
            tool_ids=tool_ids,
            lens_id=lens_id,
        )


# The process-wide default registry. Seeded empty — populating it is the job of a
# future Utilities/Control-Panel surface (see docs/wiki/81). While empty, all
# flag-aware code paths are behavior-preserving.
DEFAULT_HYPHAE_FLAG_REGISTRY = HyphaeFlagRegistry()


def raise_flags(
    document: Any,
    *,
    registry: HyphaeFlagRegistry = DEFAULT_HYPHAE_FLAG_REGISTRY,
) -> dict[str, RaisedFlag]:
    """Compile each row's canonical hyphae value and return the raised flag per
    matching datum address. Empty/no-match → empty dict (the registry fast-paths
    an empty registry, so this is free when nothing is registered).
    """
    if registry.is_empty():
        return {}
    raised: dict[str, RaisedFlag] = {}
    for row in document.rows:
        address = row.datum_address
        value = compile_hyphae_value(document, address)
        flag = registry.raise_for_value(datum_address=address, hyphae_value=value)
        if flag is not None:
            raised[address] = flag
    return raised


__all__ = [
    "DATUM_SCOPE",
    "DEFAULT_HYPHAE_FLAG_REGISTRY",
    "FAMILY_ROOT_SCOPE",
    "HyphaeFlag",
    "HyphaeFlagRegistry",
    "RaisedFlag",
    "raise_flags",
]
