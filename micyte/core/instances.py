"""Instance identity: which msn a sandbox is keyed on, and what instances exist.

An instance is a scoped view of the store keyed on ``msn_id``. Its msn is a
property of its data — the msn its own documents already carry — and is
discovered, never computed.

THE RULE: never derive meaning by parsing msn segments. An msn is a hierarchical
path like a domain name, and a label's meaning is parent-dependent: under
``-77-`` segment 6 is an organisational tier, but under ``-66-`` the same
position is geography. Reading a segment in isolation tells you nothing. The
authority for "which entity owns this sandbox" is ``registrar.legal_entity``;
the authority for "which msn is this sandbox keyed on today" is the sandbox's
own documents. This module answers the second question. The two agreeing is an
invariant worth checking (see ``MyCiteV2/scripts/rekey_sandbox_msn.py``), not an
assumption to build on.

Pure functions over a document list — every input is already-read data, so this
stays in ``micyte.core`` with no adapter dependency. Callers do the I/O.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from micyte.core.document_naming import CanonicalNameError, parse_canonical_document_id

# A sandbox is a farm instance when it carries both of these. Shape, not a list:
# a farm onboarded tomorrow is discovered with no code change. This generalizes
# micyte/tools/agronomics_viewer.py::_list_farms.
FARM_SHAPE: frozenset[str] = frozenset({"anchor", "farm_profile"})

# The reflective, corpus-wide sandbox an instance opens on when it is not a farm.
# A structural name (like the FARM_SHAPE names), not a tenant's name.
SYSTEM_SANDBOX = "system"

# Where "which entity owns this msn" is answered. The registrar is the authority —
# the DNS of the network — and the only correct way to attach meaning to an msn.
REGISTRAR_SANDBOX = "registrar"
LEGAL_ENTITY_DOCUMENT = "legal_entity"
# legal_entity rows serialize as flat (value, "rf.x-y-z") pairs, value first.
MSN_FIELD = "rf.3-1-3"
SLUG_FIELD = "rf.3-1-13"

# Words that read wrong under a plain title-case: legal suffixes ("Llc") and
# acronyms ("Fnd Ebi"). A rule about how WORDS render — deliberately not a
# registry of sandboxes or entities. Adding a farm must never require touching
# this; adding an acronym is the only reason to.
_WORD_RENDERINGS: dict[str, str] = {
    "llc": "LLC",
    "inc": "Inc",
    "lp": "LP",
    "co": "Co",
    "fnd": "FND",
    "ebi": "EBI",
    "cts": "CTS",
    "gis": "GIS",
    "txa": "TXA",
    "lcl": "LCL",
}


def prettify_token(token: str) -> str:
    """``wolf_family_sustainable_farm_llc`` -> ``Wolf Family Sustainable Farm LLC``."""
    return " ".join(_WORD_RENDERINGS.get(word, word.title()) for word in (token or "").split("_") if word)


@dataclass(frozen=True)
class SandboxInstance:
    """A sandbox present in the store, and the msn it is keyed on."""

    sandbox: str
    msn_id: str
    document_names: frozenset[str]

    @property
    def is_farm(self) -> bool:
        return FARM_SHAPE <= self.document_names


def _parsed(documents: Iterable[Any]) -> Iterator[Any]:
    """Yield the parsed id of every canonically-named document, skipping the rest."""
    for document in documents:
        try:
            yield parse_canonical_document_id(str(getattr(document, "document_id", "") or ""))
        except CanonicalNameError:
            continue


def sandbox_msn_id(documents: Iterable[Any], sandbox: str) -> str | None:
    """The msn ``sandbox``'s documents are keyed on.

    ``None`` when the sandbox has no documents (nothing to discover from) or when
    its documents disagree (a split-brain sandbox — the caller must not guess).
    """
    found = {p.msn_id for p in _parsed(documents) if p.sandbox == sandbox and p.msn_id}
    return found.pop() if len(found) == 1 else None


def list_sandbox_instances(documents: Iterable[Any]) -> list[SandboxInstance]:
    """Every sandbox in the store, keyed on the msn its documents carry.

    Sandboxes whose documents disagree about their msn are omitted rather than
    guessed at.
    """
    names: dict[str, set[str]] = {}
    msns: dict[str, set[str]] = {}
    for p in _parsed(documents):
        if not p.sandbox:
            continue
        names.setdefault(p.sandbox, set()).add(p.name)
        msns.setdefault(p.sandbox, set()).add(p.msn_id)
    out = [
        SandboxInstance(sandbox=sb, msn_id=next(iter(msns[sb])), document_names=frozenset(ns))
        for sb, ns in names.items()
        if len(msns.get(sb, ())) == 1
    ]
    out.sort(key=lambda i: i.sandbox)
    return out


def list_farm_instances(documents: Iterable[Any]) -> list[SandboxInstance]:
    """The sandboxes that are farms, by shape (``anchor`` + ``farm_profile``)."""
    return [i for i in list_sandbox_instances(documents) if i.is_farm]


def _row_fields(row: Any) -> dict[str, Any]:
    raw = row.raw if isinstance(row.raw, list) else [row.raw]
    flat = raw[0] if raw and isinstance(raw[0], list) else raw
    return {str(flat[i + 1]): flat[i] for i in range(0, len(flat) - 1, 2)}


def _find_legal_entity(documents: Iterable[Any]) -> Any | None:
    """The single ``registrar.legal_entity`` document, or ``None``."""
    for document in documents:
        try:
            parsed = parse_canonical_document_id(str(getattr(document, "document_id", "") or ""))
        except CanonicalNameError:
            continue
        if parsed.sandbox == REGISTRAR_SANDBOX and parsed.name == LEGAL_ENTITY_DOCUMENT:
            return document
    return None


def _slug_for_msn(legal_entity: Any, msn_id: str) -> str | None:
    """The entity slug ``legal_entity`` binds to ``msn_id`` — scans its rows only.

    ``None`` when the registrar does not know the msn, or binds it ambiguously.
    """
    slugs = {
        str(fields.get(SLUG_FIELD))
        for row in legal_entity.rows
        if (fields := _row_fields(row)).get(MSN_FIELD) == msn_id and fields.get(SLUG_FIELD)
    }
    return slugs.pop() if len(slugs) == 1 else None


def registrar_entity_slug(documents: Iterable[Any], msn_id: str) -> str | None:
    """The entity slug ``registrar.legal_entity`` binds to ``msn_id``.

    This is the resolution step: an msn means whatever the registrar says it
    means. ``None`` when the registrar does not know the msn, or binds it
    ambiguously — in which case the caller must not invent a name for it.

    Resolving many msns at once? Find the legal_entity once (``_find_legal_entity``)
    and call ``_slug_for_msn`` per msn — this convenience re-scans for it each call.
    """
    legal_entity = _find_legal_entity(documents)
    return _slug_for_msn(legal_entity, msn_id) if legal_entity is not None else None


@dataclass(frozen=True)
class PortalInstance:
    """One msn, and every sandbox keyed on it.

    This is the unit the profile switcher switches between: "which MiCyte portal
    am I in". FND owns several sandboxes under one msn; a farm owns one.
    """

    msn_id: str
    sandboxes: tuple[SandboxInstance, ...]
    entity_slug: str | None

    @property
    def is_farm(self) -> bool:
        return any(s.is_farm for s in self.sandboxes)

    @property
    def home_sandbox(self) -> str:
        """The sandbox the portal opens on when this instance is selected."""
        farms = sorted(s.sandbox for s in self.sandboxes if s.is_farm)
        if farms:
            return farms[0]
        names = sorted(s.sandbox for s in self.sandboxes)
        return SYSTEM_SANDBOX if SYSTEM_SANDBOX in names else names[0]

    @property
    def label(self) -> str:
        """Human label — the registrar's entity name, else the home sandbox."""
        return prettify_token(self.entity_slug or self.home_sandbox)


def list_portal_instances(documents: Iterable[Any]) -> list[PortalInstance]:
    """Every portal instance in the store, keyed by msn.

    Farms sort last so the operator's own instance leads, then alphabetically —
    an ordering rule, so no instance is privileged by being named in code.
    """
    documents = list(documents)
    # Resolve the registrar's legal_entity document ONCE (a full-corpus scan);
    # each instance's slug is then a small scan of that one document's rows,
    # instead of re-scanning the whole corpus per msn.
    legal_entity = _find_legal_entity(documents)
    by_msn: dict[str, list[SandboxInstance]] = {}
    for instance in list_sandbox_instances(documents):
        by_msn.setdefault(instance.msn_id, []).append(instance)
    out = [
        PortalInstance(
            msn_id=msn,
            sandboxes=tuple(sorted(sandboxes, key=lambda s: s.sandbox)),
            entity_slug=_slug_for_msn(legal_entity, msn) if legal_entity is not None else None,
        )
        for msn, sandboxes in by_msn.items()
    ]
    out.sort(key=lambda i: (i.is_farm, i.label))
    return out


def default_farm_sandbox(documents: Iterable[Any]) -> str | None:
    """The farm to show when the caller has not chosen one.

    The first farm in a stable alphabetical order — a rule, not a name. ``None``
    when the store holds no farm, because inventing one would claim a farm exists
    where none does. Callers must handle ``None`` rather than substitute a
    literal.
    """
    farms = list_farm_instances(documents)
    return farms[0].sandbox if farms else None
