"""The local domain CONVENTION as data — what a tree is made of, read off a tree.

TASK-2026-09-11-001 P4. Operator: *"edit the local domain archetype document from the FND
instance in the archetype sandbox … mostly organization of defaults and icon selection so
that I can update the convention from there."*

Until now the convention lived in code: :mod:`local_domain`'s labels and ordinals,
``CANONICAL_GLYPHS``, ``STRUCTURAL_GLYPHS``, ``ARTIFACT_KINDS``, ``CLASS_KINDS`` — and the
seed (:func:`micyte.core.instance_baseline.seeded_local_domain_rows`) turned them into
rows. The archetype library's own ``lcl_domain`` is that seed written out, so it already
SAYS the convention; this module reads it back as a :class:`Convention` and the seed takes
one instead of reaching for the constants. The constants stay as the BOOTSTRAP — a store
with no library yet — and :func:`disagreements` is the test that the two say the same
thing, so an edit to the library that the code cannot honour is a red test, not a drift.

What a Convention holds is exactly what the operator asked to edit: the branch LABELS,
the GLYPH each structural role wears, the canonical glyph titles in slot order, the
artifact and class kinds, and the class VOCABULARIES (the children under each class kind
— which is where `project_roles` and `project_facts` live). Ordinals are not in it: they
are where the seed puts a branch, and every reader finds a branch by label.

Pure: no I/O. A tree arrives as a :class:`local_domain.LocalDomainLog`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import local_domain as ld
from .datum_resolve import as_text

#: The structural ROLES a convention names a glyph for, in the order the seed writes them.
#: A role is how the seed knows a node, and the label under which the library's tree
#: carries it; the two are one table here so neither can name a role the other lacks.
STRUCTURAL_ROLES: tuple[str, ...] = (
    ld.ROOT_LABEL, ld.META_LABEL, "glyphs", "documents", "anchor", "local_domain_slot",
    "sources", "artifacts", *ld.ARTIFACT_KINDS, ld.CLASS_BRANCH_LABEL, *ld.CLASS_KINDS,
    ld.OBJECT_BRANCH_LABEL,
)

#: The class vocabularies the convention seeds beyond the derived three — the project
#: document's roles and fact kinds (docs/wiki/44-project-documents.md), so a website's
#: resolver finds them on every instance that took the base.
PROJECT_ROLE_KIND = "project_roles"
PROJECT_FACT_KIND = "project_facts"
PROJECT_STATUS_KIND = "project_status"
#: What a movement of stock can BE (TASK-2026-09-12-001). The direction each one moves the
#: balance is `micyte.core.datum_ops.stock_log.DIRECTIONS`, so a kind seeded here and
#: absent there is refused at the door rather than silently untotalled.
STOCK_EVENT_KIND = "stock_events"
BASE_VOCABULARIES: dict[str, tuple[str, ...]] = {
    # Picture roles first, then text roles: what a site's profile carries today
    # (BHN's `mycite.site_core.profile.v1`), each a ROLE a resolver reads by name.
    PROJECT_ROLE_KIND: (
        "feature", "gallery", "tour", "plan", "hidden",
        "summary", "story", "fact", "detail", "feature_interior", "feature_exterior",
        "address", "location", "marketing_name", "property_type", "map_url",
        "tour_title"),
    PROJECT_FACT_KIND: ("beds", "baths", "half_baths", "square_feet", "lot_acres",
                        "stories", "year", "sold_price", "sold_year"),
    # Where a project stands, as the header's `status_ref` names it.
    PROJECT_STATUS_KIND: ("for_sale", "sold", "coming_soon", "completed", "in_progress"),
    # What came in and what went out. `output` and `spoilage` are both subtractions and
    # are two kinds because "sold" and "lost" are different answers to "why did it fall".
    STOCK_EVENT_KIND: ("supply", "return", "adjustment_up",
                       "output", "spoilage", "adjustment_down"),
}


@dataclass(frozen=True)
class Convention:
    """What every local domain is made of."""

    #: role -> the label the branch carries (root, meta, glyphs, documents, …).
    labels: dict[str, str] = field(default_factory=dict)
    #: The canonical glyph titles in slot order.
    glyphs: tuple[str, ...] = ()
    #: role -> the glyph TITLE a structural node of that role wears.
    structural_glyphs: dict[str, str] = field(default_factory=dict)
    #: The kinds under `artifacts`, in order.
    artifact_kinds: tuple[str, ...] = ()
    #: The kinds under `classes`, in order — the derived three and any the convention adds.
    class_kinds: tuple[str, ...] = ()
    #: class kind -> the labels its children carry, for the kinds the convention SEEDS
    #: (a derived kind's children come from the library and the anchor, not from here).
    vocabularies: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: The default glyph an ordinary node wears.
    default_glyph: str = ld.DEFAULT_GLYPH
    #: Where it came from — a document id, or "constants".
    source: str = "constants"

    def label(self, role: str) -> str:
        return self.labels.get(role) or role

    def to_dict(self) -> dict[str, Any]:
        return {
            "labels": dict(self.labels), "glyphs": list(self.glyphs),
            "structural_glyphs": dict(self.structural_glyphs),
            "artifact_kinds": list(self.artifact_kinds), "class_kinds": list(self.class_kinds),
            "vocabularies": {k: list(v) for k, v in self.vocabularies.items()},
            "default_glyph": self.default_glyph, "source": self.source,
        }


def from_constants() -> Convention:
    """The convention the code carries — the bootstrap, and what a library must agree with."""
    labels = {role: role for role in STRUCTURAL_ROLES}
    labels.update({
        "glyphs": ld.GLYPH_BRANCH_LABEL, "documents": ld.DOCUMENT_BRANCH_LABEL,
        "sources": ld.SOURCE_BRANCH_LABEL, "artifacts": ld.ARTIFACT_BRANCH_LABEL,
        "anchor": ld.RESERVED_SLOT_TITLES[ld.ANCHOR_SLOT_ORDINAL],
        "local_domain_slot": ld.RESERVED_SLOT_TITLES[ld.LOG_SLOT_ORDINAL],
    })
    return Convention(
        labels=labels, glyphs=tuple(ld.CANONICAL_GLYPHS),
        structural_glyphs={role: ld.STRUCTURAL_GLYPHS.get(role, ld.DEFAULT_GLYPH)
                           for role in STRUCTURAL_ROLES},
        artifact_kinds=tuple(ld.ARTIFACT_KINDS),
        class_kinds=(*ld.CLASS_KINDS, *BASE_VOCABULARIES),
        vocabularies={k: tuple(v) for k, v in BASE_VOCABULARIES.items()},
        default_glyph=ld.DEFAULT_GLYPH, source="constants",
    )


def _child_labelled(log: Any, parent: str, label: str) -> str:
    wanted = as_text(label).strip().lower()
    for node, entry in log.children_of(parent).items():
        if as_text(entry.label).strip().lower() == wanted:
            return node
    return ""


def from_log(log: Any, *, source: str = "") -> Convention:
    """Read the convention a tree states — the library's, when the tree is the library's.

    Roles are found by POSITION in the base structure (the meta root's branches, the
    reserved slots, the kinds under `artifacts` and `classes`) and their labels and glyphs
    are whatever the tree carries, which is the point: the operator renames a branch or
    changes what it wears in the library and this reads it back.
    """
    glyph_title = {slot: as_text(entry.label) for slot, entry in log.icons().items()}

    def wears(node: str) -> str:
        return glyph_title.get(log.icon_of(node), "") if node else ""

    labels: dict[str, str] = {}
    structural: dict[str, str] = {}

    def take(role: str, node: str) -> None:
        if node:
            labels[role] = as_text(log.label_of(node))
            structural[role] = wears(node)

    take(ld.ROOT_LABEL, log.root)
    take(ld.META_LABEL, log.meta_root)
    take("glyphs", log.glyph_root)
    take("documents", log.document_root)
    if log.document_root:
        reserved = dict(log.reserved_slots())          # {slot: ordinal}
        take("anchor", next((s for s, o in reserved.items() if o == ld.ANCHOR_SLOT_ORDINAL), ""))
        take("local_domain_slot",
             next((s for s, o in reserved.items() if o == ld.LOG_SLOT_ORDINAL), ""))
    take("sources", log.source_root)
    take("artifacts", log.artifact_root)
    artifact_kinds: list[str] = []
    for node, entry in log.children_of(log.artifact_root).items() if log.artifact_root else ():
        kind = as_text(entry.label)
        artifact_kinds.append(kind)
        take(kind, node)
    take(ld.CLASS_BRANCH_LABEL, log.class_root)
    class_kinds: list[str] = []
    vocabularies: dict[str, tuple[str, ...]] = {}
    for node, entry in log.children_of(log.class_root).items() if log.class_root else ():
        kind = as_text(entry.label)
        class_kinds.append(kind)
        take(kind, node)
        children = tuple(as_text(e.label) for e in log.children_of(node).values())
        if kind not in ld.CLASS_KINDS:
            vocabularies[kind] = children
    take(ld.OBJECT_BRANCH_LABEL, log.object_root)
    glyphs = tuple(as_text(entry.label) for entry in log.icons().values())
    default = glyph_title.get(log.default_glyph(), ld.DEFAULT_GLYPH)
    return Convention(
        labels=labels, glyphs=glyphs, structural_glyphs=structural,
        artifact_kinds=tuple(artifact_kinds), class_kinds=tuple(class_kinds),
        vocabularies=vocabularies, default_glyph=default or ld.DEFAULT_GLYPH,
        source=source or "log",
    )


def disagreements(stated: Convention, expected: Convention) -> list[str]:
    """Every way ``stated`` differs from ``expected`` on what the SEED needs, by name.

    The seed needs labels for the roles it mints, a glyph for each, the kinds and the
    vocabularies. A library that renamed a branch, changed what a role wears, or added a
    vocabulary is a convention the seed must honour — and the constants must be brought
    to say the same, or a fresh store (no library) would seed a different tree than a
    live one. So this is the agreement test, and it is symmetric on purpose.
    """
    out: list[str] = []
    for role in STRUCTURAL_ROLES:
        if stated.label(role) != expected.label(role):
            out.append(f"{role}: label {stated.label(role)!r} vs {expected.label(role)!r}")
        wear_s = stated.structural_glyphs.get(role, "")
        wear_e = expected.structural_glyphs.get(role, "")
        if wear_s and wear_e and wear_s != wear_e:
            out.append(f"{role}: wears {wear_s!r} vs {wear_e!r}")
    # Glyph titles are compared IN ORDER: a slot's ordinal is the drawing every node cites.
    # Kinds and vocabularies are compared as SETS: a reader finds them by label, and a tree
    # brought up later minted its missing kind after the ones it had.
    if tuple(stated.glyphs) != tuple(expected.glyphs):
        out.append(f"glyphs: {list(stated.glyphs)} vs {list(expected.glyphs)}")
    if set(stated.artifact_kinds) != set(expected.artifact_kinds):
        out.append(f"artifact kinds: {sorted(stated.artifact_kinds)} vs {sorted(expected.artifact_kinds)}")
    if set(stated.class_kinds) != set(expected.class_kinds):
        out.append(f"class kinds: {sorted(stated.class_kinds)} vs {sorted(expected.class_kinds)}")
    for kind in sorted(set(stated.vocabularies) | set(expected.vocabularies)):
        if set(stated.vocabularies.get(kind, ())) != set(expected.vocabularies.get(kind, ())):
            out.append(f"{kind}: {sorted(stated.vocabularies.get(kind, ()))} vs "
                       f"{sorted(expected.vocabularies.get(kind, ()))}")
    if stated.default_glyph != expected.default_glyph:
        out.append(f"default glyph: {stated.default_glyph!r} vs {expected.default_glyph!r}")
    return out


__all__ = [
    "BASE_VOCABULARIES",
    "PROJECT_FACT_KIND",
    "PROJECT_ROLE_KIND",
    "PROJECT_STATUS_KIND",
    "STOCK_EVENT_KIND",
    "STRUCTURAL_ROLES",
    "Convention",
    "disagreements",
    "from_constants",
    "from_log",
]
