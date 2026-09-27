"""Viewscopes — how a datum document is rendered, declared as data beside its archetype.

A **lens** (``micyte.state_machine.lens``) is a cell-level codec: it turns one canonical
magnitude into one display value. A **viewscope** is the document-level counterpart: given
that a document IS a ``geospatial_polygon`` or an ``administrative_entity_profile``, it says
which primitives draw it and how they are arranged. Lens is to cell as viewscope is to
document, and neither replaces the other — a viewscope's field slots resolve their cells
through lenses exactly as the raw grid does.

The declaration lives in the ``archetype`` sandbox beside the archetype it binds to, in a
``viewscope.<archetype>`` document::

    4-1-1  [title -> container]                                       ["viewscope"]
    4-2-N  [title -> group, title -> primitive, title -> field]       ["<label>"]

Read and write are both in this module, deliberately — a format whose reader and writer
live apart is a format that drifts. That is the rule ``record_spec`` established when the
LCL record shapes became data, and this is the same move one level up: there, a *record
type* stopped being Python; here, a *view* does.

**Primitives are code; composition is data.** The five primitives below are the fixed
vocabulary a renderer implements. Which primitive draws which field, in which group, in
what order, is rows — so a new archetype gets a view without new JavaScript, which is the
whole point of retiring 25 bespoke viewers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import field_registry as _fr
from .datum_resolve import as_text, decode_label, iter_marker_pairs

#: Document naming: one viewscope per archetype, named for it.
#:
#: An UNDERSCORE, not a dot. A canonical id is dot-delimited
#: (``lv.<msn>.<sandbox>.<name>.<hash>``), so ``document_naming`` refuses a name containing
#: one — ``viewscope.geospatial_polygon`` would have split the id into six segments and
#: parsed as a different document entirely.
VIEWSCOPE_PREFIX = "viewscope_"

#: Row families. A header, then its slots, in order.
CONTAINER_FAMILY = "4-1"
SLOT_FAMILY = "4-2"

#: Containers a viewscope may declare — how the slots are laid out.
#:
#: ``slot_grid``  — named groups of labelled slots. The profile/card layout.
#: ``record_line`` — one line per matching ROW, slots as columns. The list layout, for a
#:                   document whose archetype matches many rows (a directory).
#: ``tree``        — one node per matching row, nested by the ADDRESS its key field holds.
#:                   A SAMRAS address is its own path: `1-1-3-3-5-8` is a child of
#:                   `1-1-3-3-5`. So a taxonomy renders as the tree it already is, and
#:                   nothing has to be declared about the hierarchy — it is in the data.
#:
#:                   This is not `samras_structure`'s tree. That one decodes the ANCHOR's
#:                   compiled radix to find every node the structure DENOTES, then reports
#:                   which the document leaves undefined. Comparing a document to its
#:                   structure is a derivation and stays a tool; showing what a document
#:                   says is this.
#: ``glyph_canvas`` — the document IS one drawing. It declares no slots because it has no
#:                   fields to draw: its rows decode to path data through
#:                   :mod:`micyte.core.datum_ops.glyph` and nothing else is consulted.
#:
#:                   A CONTAINER and not a primitive, though ``symbol`` looks close.
#:                   ``symbol`` renders ``<img src="/assets/icons/<ref>.svg">`` — a
#:                   FILENAME — and a glyph has no file. That it stopped having one is the
#:                   whole point.
CONTAINERS: tuple[str, ...] = ("slot_grid", "record_line", "tree", "glyph_canvas")

#: Primitives a slot may use. Fixed, because each is a renderer.
#:
#: ``field_pair``  — a label and its lens-decoded value.
#: ``node_chip``   — a SAMRAS address (msn/txa/lcl), rendered as a chip that resolves to a
#:                   name when one is known and stays an address when it is not.
#: ``map_ring``    — a HOPS coordinate run, drawn as geometry.
#: ``text``        — a decoded nominal/title blob, given room to be read.
#: ``symbol``     — an icon leaflet, DRAWN. `taxon_record` carries an `icon_ref` and its
#:                   viewscope drew it as a `field_pair`, so a taxonomy node showed the
#:                   FILENAME of its own icon where the icon belongs.
#: ``reference``   — a slot whose value names ANOTHER document; the renderer resolves it and
#:                   draws that document's own viewscope inline. This is the composition
#:                   edge: `administrative_entity_profile` carries `region_polygon_ref`, so
#:                   a jurisdiction draws its own boundary without a bespoke map viewer.
PRIMITIVES: tuple[str, ...] = ("field_pair", "node_chip", "map_ring", "text", "reference", "symbol")

#: The primitives a viewscope can EDIT, and the ones it must refuse.
#:
#: Editability is a property of the primitive, not a decision the renderer makes — the same
#: declaration that says how a slot is drawn says whether it can be typed into. Measured
#: across the live library before this was chosen: 27 archetypes carry 101 slots, and
#: ``msn_id`` alone appears in 16 of them. A viewscope that made every slot editable would
#: hand an operator a text box for the msn a job's customer IS, and a re-pointed reference
#: looks exactly like a corrected typo.
#:
#: ``field_pair`` is "a label and its lens-decoded value" and ``text`` is "a decoded
#: nominal/title blob" — scalars, and a text box is the whole of what they need. The other
#: four DENOTE something: a SAMRAS address, a coordinate run, an icon leaflet, another
#: document. Each is refusable for a stated reason rather than merely absent, so the
#: renderer can say why a value is read-only instead of silently not offering it.
EDITABLE_PRIMITIVES: frozenset[str] = frozenset({"field_pair", "text"})

#: Of the editable ones, those whose stored magnitude is a LABEL BIT-STRING rather than the
#: value itself. ``title`` reads as text and is stored as ``encode_label_bits(value)``;
#: writing the string verbatim would put a human-readable word where every reader expects
#: bits and decode it to nothing.
LABEL_ENCODED_PRIMITIVES: frozenset[str] = frozenset({"text"})

#: Why a primitive is not editable here. Stated, because "no input appeared" is
#: indistinguishable from a bug.
NOT_EDITABLE_BECAUSE: dict[str, str] = {
    "node_chip": "this is an address of another node — it is chosen, not typed",
    "reference": "this names another document; edit that document instead",
    "map_ring": "this is geometry, and a coordinate run is not text",
    "symbol": "this is an icon leaflet, picked from the sprite",
}

#: The primitive a slot gets when it declares none, by the field's own kind. Keyed on the
#: logical field name so a declaration can stay short and still be right.
DEFAULT_PRIMITIVE: dict[str, str] = {
    "coordinate": "map_ring",
    "msn_id": "node_chip",
    "site_msn": "node_chip",
    "txa_id": "node_chip",
    "lcl_id": "node_chip",
    "entity_kind": "node_chip",
    "icon_ref": "symbol",
    "region_polygon_ref": "reference",
    "hyphae_ref": "reference",
    "observed_by": "reference",
    "title": "text",
    "common_name": "text",
    "name": "text",
}
FALLBACK_PRIMITIVE = "field_pair"


@dataclass(frozen=True)
class Slot:
    """One drawn thing: a logical field, a primitive, and the group it sits in."""

    field: str
    primitive: str
    group: str = ""
    label: str = ""

    @property
    def display_label(self) -> str:
        return self.label or self.field.replace("_", " ")

    @property
    def editable(self) -> bool:
        """Whether this slot can be typed into — decided by its PRIMITIVE."""
        return self.primitive in EDITABLE_PRIMITIVES

    @property
    def label_encoded(self) -> bool:
        """Whether the value written for this slot is stored as label BITS."""
        return self.primitive in LABEL_ENCODED_PRIMITIVES

    @property
    def not_editable_because(self) -> str:
        """Why this slot is read-only, or "" when it is not."""
        return "" if self.editable else NOT_EDITABLE_BECAUSE.get(
            self.primitive, f"{self.primitive} slots are not editable"
        )

    def normalized(self) -> Slot:
        """This slot with its label made explicit.

        The writer puts ``display_label`` in the row's tail so a human reading the raw
        document sees a name rather than a blank, which means the reader gets a label back
        whether one was declared or not. Normalizing before comparison is what makes the
        mint's round-trip check an equality rather than an approximation — and the check
        earned that: it caught exactly this drift the first time it ran.
        """
        return self if self.label else Slot(
            field=self.field, primitive=self.primitive, group=self.group,
            label=self.display_label,
        )


@dataclass(frozen=True)
class Viewscope:
    """How to draw documents of one archetype."""

    archetype: str
    container: str
    slots: tuple[Slot, ...]
    document_id: str = ""

    @property
    def groups(self) -> tuple[str, ...]:
        seen: list[str] = []
        for slot in self.slots:
            if slot.group not in seen:
                seen.append(slot.group)
        return tuple(seen)

    def slots_in(self, group: str) -> tuple[Slot, ...]:
        return tuple(slot for slot in self.slots if slot.group == group)

    def normalized(self) -> Viewscope:
        """This viewscope as it will read back after a write. See :meth:`Slot.normalized`."""
        return Viewscope(
            archetype=self.archetype,
            container=self.container,
            slots=tuple(slot.normalized() for slot in self.slots),
            document_id=self.document_id,
        )


def default_primitive(field: str) -> str:
    return DEFAULT_PRIMITIVE.get(as_text(field), FALLBACK_PRIMITIVE)


def viewscope_name(archetype: str) -> str:
    return VIEWSCOPE_PREFIX + as_text(archetype)


def archetype_of(document_name: str) -> str:
    """The archetype a ``viewscope.<archetype>`` document binds to, or ``""``."""
    name = as_text(document_name)
    return name[len(VIEWSCOPE_PREFIX) :] if name.startswith(VIEWSCOPE_PREFIX) else ""


# --------------------------------------------------------------------------------------
# WRITE
# --------------------------------------------------------------------------------------


def build_viewscope_rows(
    viewscope: Viewscope, *, namespace: str = _fr.ARCHETYPE
) -> list[dict[str, Any]]:
    """A viewscope as datum rows. The inverse of :func:`load_viewscopes`."""
    title = _fr.marker(namespace, "title")
    rows: list[dict[str, Any]] = [
        {
            "datum_address": f"{CONTAINER_FAMILY}-1",
            "raw": [[f"{CONTAINER_FAMILY}-1", title, viewscope.container], ["viewscope"]],
        }
    ]
    for index, slot in enumerate(viewscope.slots, start=1):
        address = f"{SLOT_FAMILY}-{index}"
        rows.append(
            {
                "datum_address": address,
                "raw": [
                    [address, title, slot.group, title, slot.primitive, title, slot.field],
                    [slot.display_label],
                ],
            }
        )
    return rows


# --------------------------------------------------------------------------------------
# READ
# --------------------------------------------------------------------------------------


def _head(row: Any) -> list[Any] | None:
    raw = row.get("raw") if isinstance(row, dict) else getattr(row, "raw", None)
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return list(raw[0])
    return None


def _tail_label(row: Any) -> str:
    raw = row.get("raw") if isinstance(row, dict) else getattr(row, "raw", None)
    if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], list) and raw[1]:
        return decode_label(raw[1][0])
    return ""


def _address(row: Any) -> str:
    if isinstance(row, dict):
        return as_text(row.get("datum_address"))
    return as_text(getattr(row, "datum_address", ""))


def load_viewscope(document: Any) -> tuple[Viewscope | None, list[str]]:
    """Read one ``viewscope.<archetype>`` document, plus why any row was ignored.

    A slot naming a primitive this build does not implement is REFUSED with a reason, not
    dropped silently and not passed through: a renderer asked for a primitive it has never
    heard of draws nothing, and a viewscope that half-draws a document is worse than one
    that declines to.
    """
    problems: list[str] = []
    name = as_text(getattr(document, "canonical_name", ""))
    if not name:
        parts = as_text(getattr(document, "document_id", "")).split(".")
        name = parts[3] if len(parts) > 4 else ""
    archetype = archetype_of(name)
    if not archetype:
        return None, problems

    container = ""
    slots: list[Slot] = []
    for row in getattr(document, "rows", ()) or ():
        head = _head(row)
        if head is None:
            continue
        address = _address(row)
        values = [decode_label(magnitude) for _marker, magnitude in iter_marker_pairs(head)]
        if address.startswith(CONTAINER_FAMILY + "-"):
            declared = as_text(values[0] if values else "")
            if declared not in CONTAINERS:
                problems.append(f"{address}: unknown container {declared!r}")
                continue
            container = declared
        elif address.startswith(SLOT_FAMILY + "-"):
            group, primitive, field = [*values, "", "", ""][:3]
            field = as_text(field)
            if not field:
                problems.append(f"{address}: slot names no field")
                continue
            primitive = as_text(primitive) or default_primitive(field)
            if primitive not in PRIMITIVES:
                problems.append(f"{address}: slot {field!r} wants unknown primitive {primitive!r}")
                continue
            slots.append(
                Slot(field=field, primitive=primitive, group=as_text(group), label=_tail_label(row))
            )
    if not container:
        problems.append(f"{name}: declares no container")
        return None, problems
    return (
        Viewscope(
            archetype=archetype,
            container=container,
            slots=tuple(slots),
            document_id=as_text(getattr(document, "document_id", "")),
        ),
        problems,
    )


def resolve_viewscope(
    archetype: str,
    viewscopes: dict[str, Viewscope],
    classes: Any = None,
    *,
    declared_fields: Any = None,
) -> tuple[Viewscope | None, str]:
    """The viewscope that draws ``archetype``, and where it came from.

    Order is specific-beats-general: the archetype's OWN viewscope, else the nearest class
    up its lineage that declares slots. Returns ``(viewscope, source)`` where ``source`` is
    ``"archetype"``, ``"class:<name>"``, or ``""`` when nothing draws it — the caller says
    so in the payload, because "inherited from the profile class" and "written for this
    archetype" are different facts about a rendering and an operator debugging a wrong-looking
    document needs to know which one it is looking at.

    ``declared_fields`` is the archetype's own field vocabulary (``Archetype.required_fields``
    plus its optional runs). A class slot naming a field this archetype does not carry is
    DROPPED rather than drawn empty: the class describes what its members have in common,
    and ``natural_entity_profile`` has no ``coordinate`` however much the profile class knows
    what one would look like. Passing ``None`` keeps every slot, which is what a caller with
    no registry to hand should get.
    """
    own = viewscopes.get(as_text(archetype))
    if own is not None:
        return own, "archetype"
    if classes is None:
        return None, ""
    container, specs, declaring = classes.drawing_for(as_text(archetype))
    if not specs or not container:
        return None, ""
    allowed = None if declared_fields is None else {as_text(f) for f in declared_fields}
    slots: list[Slot] = []
    for spec in specs:
        if allowed is not None and spec.field not in allowed:
            continue
        primitive = as_text(spec.primitive) or default_primitive(spec.field)
        if primitive not in PRIMITIVES:
            continue
        slots.append(
            Slot(field=spec.field, primitive=primitive, group=spec.group, label=spec.label)
        )
    if not slots:
        return None, ""
    return (
        Viewscope(archetype=as_text(archetype), container=container, slots=tuple(slots)),
        f"class:{declaring}",
    )


def load_viewscopes(documents: Any) -> tuple[dict[str, Viewscope], list[str]]:
    """Every viewscope in the catalog, keyed by the archetype it binds to."""
    out: dict[str, Viewscope] = {}
    problems: list[str] = []
    for document in documents:
        metadata = getattr(document, "document_metadata", None)
        if not isinstance(metadata, dict) or as_text(metadata.get("role")) != "viewscope":
            continue
        viewscope, reasons = load_viewscope(document)
        problems.extend(reasons)
        if viewscope is None:
            continue
        if viewscope.archetype in out:
            problems.append(f"{viewscope.archetype}: declared by more than one viewscope")
            continue
        out[viewscope.archetype] = viewscope
    return out, problems


__all__ = [
    "CONTAINERS",
    "CONTAINER_FAMILY",
    "DEFAULT_PRIMITIVE",
    "PRIMITIVES",
    "SLOT_FAMILY",
    "VIEWSCOPE_PREFIX",
    "Slot",
    "Viewscope",
    "archetype_of",
    "build_viewscope_rows",
    "default_primitive",
    "load_viewscope",
    "load_viewscopes",
    "resolve_viewscope",
    "viewscope_name",
]
