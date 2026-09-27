"""A project as a DOCUMENT, read into the view a website's resolver can rely on.

Operator, 2026-09-11: *"a polished thought out convention of datum doc structure for
projects such that a website can have its own custom reader or resolver such that any
design can be the shown result, but the extent of information can be made dynamic and
yet also expected."*

## The convention (docs/wiki/44-project-documents.md)

One document per project, filed on the instance's tree under its project node, whose rows
are four archetypes the library declares (``scripts/mint_archetype_sandbox.py``):

====================  ==========================================  ======================
archetype             cells, in order                             one row per
====================  ==========================================  ======================
``project_profile``   msn_id, site_msn, lcl_id, title, utc?,      the document (header)
                      status_ref?, hyphae_ref?
``project_text``      lcl_id ROLE, nominal order, title text      paragraph / fact line
``project_artifact``  lcl_id SLOT, lcl_id ROLE, nominal order,    picture / tour
                      title? caption
``project_fact``      nominal value, lcl_id KIND, title? word     detail
====================  ==========================================  ======================

The extent is DYNAMIC because rows are added, not cells: a project with forty photographs
and one with three are the same shapes forty and three times. It is EXPECTED because this
reader answers the same :class:`ProjectView` for every project — the keys a resolver
reads are fixed, and a role or fact kind the instance minted beyond the base vocabulary
arrives under the same keys, addressed by its node.

**What the reader does with what it does not know.** A row of an archetype outside the
four — a derived archetype a site minted from the base because the base could not say what
it needed — is carried under ``extras[<archetype>]`` with its fields folded by name, and a
row NO archetype covers under ``unmatched``. Neither is dropped and neither is guessed at:
a resolver that wants the extra reads it by the archetype's name, which is the contract
the library's partition gives it (every archetype in exactly one class).

**Pure.** Takes the document and a registry the caller already holds; touches no store.
Node LABELS are the tree's and are passed in when a caller has them (`labels`), so a role
reads as ``feature`` where the tree is known and as its address where it is not — never as
a guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import archetype_shape as ash
from .datum_resolve import as_text, decode_label, iter_marker_pairs

#: The header and the three extents, by name — the four rows a project document is.
HEADER_ARCHETYPE = "project_profile"
TEXT_ARCHETYPE = "project_text"
ARTIFACT_ARCHETYPE = "project_artifact"
FACT_ARCHETYPE = "project_fact"
PROJECT_ARCHETYPES: tuple[str, ...] = (
    HEADER_ARCHETYPE, TEXT_ARCHETYPE, ARTIFACT_ARCHETYPE, FACT_ARCHETYPE)

#: The BASE vocabulary a site may rely on — the labels of the role and fact-kind nodes the
#: convention seeds under an instance's `classes` (TASK-2026-09-11-001 P4). An instance may
#: mint more; a resolver reading these finds them on every instance that took the base.
ARTIFACT_ROLES: tuple[str, ...] = ("feature", "gallery", "tour", "plan", "hidden")
TEXT_ROLES: tuple[str, ...] = (
    "summary", "story", "fact", "detail", "feature_interior", "feature_exterior",
    "address", "location", "marketing_name", "property_type", "map_url", "tour", "tour_title")
FACT_KINDS: tuple[str, ...] = (
    "beds", "baths", "half_baths", "square_feet", "lot_acres", "stories", "year",
    "sold_price", "sold_year")
STATUSES: tuple[str, ...] = ("for_sale", "sold", "coming_soon", "completed", "in_progress")


@dataclass(frozen=True)
class ProjectView:
    """What a project document says, in the shape every resolver reads.

    ``texts`` / ``artifacts`` are keyed by ROLE and ``facts`` by KIND — the node's label
    where the caller supplied labels, else its address — each list in its declared order.
    """

    title: str = ""
    kind: str = ""
    owner: str = ""
    site: str = ""
    opened: str = ""
    status: str = ""
    owner_profile: str = ""
    header_address: str = ""
    texts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    artifacts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    facts: dict[str, dict[str, Any]] = field(default_factory=dict)
    extras: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    unmatched: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title, "kind": self.kind, "owner": self.owner, "site": self.site,
            "opened": self.opened, "status": self.status, "owner_profile": self.owner_profile,
            "header_address": self.header_address,
            "texts": self.texts, "artifacts": self.artifacts, "facts": self.facts,
            "extras": self.extras, "unmatched": list(self.unmatched),
        }


def _head(row: Any) -> list[Any]:
    raw = getattr(row, "raw", None)
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return list(raw[0])
    return []


def _cells(head: list[Any], *, namespace: str) -> list[tuple[str, str]]:
    """``[(field, magnitude), …]`` in cell order — the run kept as separate cells, because
    a project_artifact's two lcl cells MEAN different things by position."""
    return [(ash._field_name(as_text(marker), sandbox=namespace), as_text(magnitude))
            for marker, magnitude in iter_marker_pairs(head)]


def _folded(cells: list[tuple[str, str]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name, value in cells:
        out.setdefault(name, []).append(value)
    return out


def _first(cells: list[tuple[str, str]], name: str, *, skip: int = 0) -> str:
    seen = 0
    for field_name, value in cells:
        if field_name == name:
            if seen == skip:
                return value
            seen += 1
    return ""


def _order(value: str) -> int:
    return int(value) if value.isdigit() else 0


def _named(node: str, labels: dict[str, str] | None) -> str:
    return (labels or {}).get(node) or node


def read_project(document: Any, *, registry: Any, namespace: str,
                 labels: dict[str, str] | None = None) -> ProjectView:
    """Fold every row of ``document`` to its archetype and answer the view.

    ``registry`` is the archetype registry (`micyte.core.archetypes.registry_for`);
    ``namespace`` the sandbox's field numbering; ``labels`` ``{node: label}`` off the
    tree, optional. Rows are read in address order within each family so ``order`` is
    what the writer said and not what the store returned.
    """
    view: dict[str, Any] = {
        "title": "", "kind": "", "owner": "", "site": "", "opened": "", "status": "",
        "owner_profile": "", "header_address": "",
    }
    texts: dict[str, list[dict[str, Any]]] = {}
    lines: dict[tuple[str, int], list[tuple[int, str, str]]] = {}
    artifacts: dict[str, list[dict[str, Any]]] = {}
    facts: dict[str, dict[str, Any]] = {}
    extras: dict[str, list[dict[str, Any]]] = {}
    unmatched: list[str] = []

    for row in getattr(document, "rows", ()) or ():
        address = as_text(getattr(row, "datum_address", ""))
        head = _head(row)
        if len(head) < 3:
            continue                                  # the structural blank, or nothing
        shape = ash.row_shape(row.raw, sandbox=namespace)
        matches = tuple(registry.match_row(shape)) if registry is not None else ()
        cells = _cells(head, namespace=namespace)
        chosen = next((name for name in PROJECT_ARCHETYPES if name in matches), "")
        if chosen == HEADER_ARCHETYPE and not view["header_address"]:
            view.update({
                "owner": _first(cells, "msn_id"), "site": _first(cells, "site_msn"),
                "kind": _first(cells, "lcl_id"), "title": decode_label(_first(cells, "title")),
                "opened": _first(cells, "utc"), "status": _first(cells, "status_ref"),
                "owner_profile": _first(cells, "hyphae_ref"), "header_address": address,
            })
            continue
        if chosen == TEXT_ARCHETYPE:
            # A paragraph is its LINES (a title babelette holds 64 characters): the first
            # nominal is the paragraph's order, the second — absent on a one-line
            # paragraph — the line's order within it. Lines join below.
            role = _named(_first(cells, "lcl_id"), labels)
            lines.setdefault((role, _order(_first(cells, "nominal"))), []).append(
                (_order(_first(cells, "nominal", skip=1)), address,
                 decode_label(_first(cells, "title"))))
            continue
        if chosen == ARTIFACT_ARCHETYPE:
            role = _named(_first(cells, "lcl_id", skip=1), labels)
            artifacts.setdefault(role, []).append({
                "address": address, "slot": _first(cells, "lcl_id"),
                "order": _order(_first(cells, "nominal")),
                "caption": decode_label(_first(cells, "title"))})
            continue
        if chosen == FACT_ARCHETYPE:
            kind = _named(_first(cells, "lcl_id"), labels)
            facts[kind] = {"address": address, "value": _first(cells, "nominal"),
                           "word": decode_label(_first(cells, "title"))}
            continue
        if matches:
            extras.setdefault(matches[0], []).append(
                {"address": address, "fields": _folded(cells)})
        else:
            unmatched.append(address)

    for (role, order), parts in lines.items():
        parts.sort(key=lambda p: (p[0], p[1]))
        texts.setdefault(role, []).append({
            "address": parts[0][1], "order": order,
            "text": " ".join(text for _line, _address, text in parts if text).strip(),
            "lines": len(parts)})
    for table in (texts, artifacts):
        for entries in table.values():
            entries.sort(key=lambda e: (e["order"], e["address"]))
    return ProjectView(texts=texts, artifacts=artifacts, facts=facts, extras=extras,
                       unmatched=unmatched, **view)


__all__ = [
    "ARTIFACT_ARCHETYPE",
    "ARTIFACT_ROLES",
    "FACT_ARCHETYPE",
    "FACT_KINDS",
    "HEADER_ARCHETYPE",
    "PROJECT_ARCHETYPES",
    "STATUSES",
    "TEXT_ARCHETYPE",
    "TEXT_ROLES",
    "ProjectView",
    "read_project",
]
