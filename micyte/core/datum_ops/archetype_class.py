"""Archetype classes — what a row DENOTES, declared as data beside the archetype library.

``archetype_shape`` folds a row to its FIELDS. ``archetypes`` names that fold. Neither says
what the row *is*: that ``record`` and ``event_log_entry`` are both lists while
``legal_entity_profile`` describes one subject is, today, a fact carried only in the fact
that somebody wrote two ``record_line`` viewscopes and one ``slot_grid``.

This module is that missing level. A class declares an **organizer** — what its rows are
indexed by — and the operator's tree falls straight out of it:

===========  ==========================  ==================================================
organizer    the tree node               what it means
===========  ==========================  ==================================================
``subject``  ``object > profile``        one subject, described. Drawn as a ``slot_grid``.
``address``  ``list > Record``           indexed by a SAMRAS id. A registry, a contact list.
``time``     ``list > Log``              indexed by an event. An invoice, an event log.
``none``     a measure                   a quantity in space or time; a component, not a
                                         subject and not a series.
===========  ==========================  ==================================================

## The class is NOT an archetype, and must not be minted as one

An archetype is its own denotation because it is a blank INSTANCE of the shape it names —
see :mod:`micyte.core.archetypes`. A class is not a shape at all; it is a grouping *over*
shapes. Minting one as an archetype would make it claim a row shape, and
:meth:`ArchetypeRegistry.ambiguities` would correctly refuse it against every member it
names. So a class document carries ``document_metadata.role = "class"``, exactly as a
viewscope carries ``role = "viewscope"``, and the archetype registry never sees it.

What replaces "the document is its own denotation" here is the **partition**:
:func:`partition_problems` asserts that every archetype belongs to exactly one LEAF class,
in both directions. A class naming an archetype that does not exist, and an archetype no
class names, are both defects — and the second is the one that matters, because it is the
silent one.

## The document

::

    4-1-1  [title -> organizer, title -> container, title -> parent]   ["class"]
    4-2-N  [title -> archetype]                                        ["<member>"]
    4-3-N  [title -> group, title -> primitive, title -> field]        ["<label>"]

The ``4-3`` rows are :class:`viewscope.Slot` rows, in the same layout the viewscope
documents use — so a class draws its members and a member may still override with a
viewscope of its own.

**The slots live HERE rather than in a ``viewscope_<class>`` document**, and that is not a
convenience. Viewscopes are keyed by the name their document carries after the prefix, so a
``viewscope_<class>`` would share one key space with the archetypes — and ``class_record``
is already a live ARCHETYPE, whose viewscope is already ``viewscope_class_record``. A class
called ``record`` and a class called ``invoice`` would then be indistinguishable from the
archetypes of those names. One document per class, carrying its own slots, has no such
collision to avoid.

Read and write both live here, for the reason :mod:`viewscope` gives: a format whose reader
and writer live apart is a format that drifts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import field_registry as _fr
from .datum_resolve import as_text, decode_label, iter_marker_pairs

#: Document naming: ``kind_<name>``.
#:
#: An UNDERSCORE, not a dot — a canonical id is dot-delimited, so ``document_naming``
#: refuses a name containing one. Same trap ``viewscope_`` avoids.
#:
#: ``kind_`` and not ``class_``, which is what this was first written as. The tree has a
#: class called ``record``, and ``class_record`` is ALREADY a live archetype — so the class
#: library's own document would have collided with an archetype document on its first write.
#: ``kind`` is not a new coinage either: it is the word the codebase already uses for this
#: question (``DeclaredWrite.document_kind``, and ``core.archetypes``' own "what KIND a
#: document is"). Nothing may be named ``kind_*`` but a class.
CLASS_PREFIX = "kind_"

#: The metadata role that marks a member of the class library.
ROLE_KEY = "role"
ROLE_VALUE = "class"

#: Row families: the header, its members, then the slots its members are drawn with.
HEADER_FAMILY = "4-1"
MEMBER_FAMILY = "4-2"
SLOT_FAMILY = "4-3"

#: What a class's rows are indexed by. This is the operator's own distinction — a Record is
#: organised by SAMRAS id, a Log by events — and it is the whole content of the top split.
ORGANIZERS: tuple[str, ...] = ("subject", "address", "time", "none")

#: The container an organizer implies, when a class declares none. Not a new vocabulary:
#: these are :data:`viewscope.CONTAINERS`, and the mapping is what the 20 hand-written
#: viewscopes already do — 10 profiles are ``slot_grid``, 8 lists are ``record_line``.
CONTAINER_FOR_ORGANIZER: dict[str, str] = {
    "subject": "slot_grid",
    "address": "record_line",
    "time": "record_line",
    "none": "slot_grid",
}


def class_name(name: str) -> str:
    return CLASS_PREFIX + as_text(name)


def name_of(document_name: str) -> str:
    """The class a ``class_<name>`` document declares, or ``""``."""
    name = as_text(document_name)
    return name[len(CLASS_PREFIX) :] if name.startswith(CLASS_PREFIX) else ""


@dataclass(frozen=True)
class SlotSpec:
    """One drawn thing, as this module reads it off the row.

    Deliberately NOT a :class:`viewscope.Slot`. ``viewscope`` imports this module to resolve
    a class's drawing, so importing ``Slot`` back would close the cycle. The conversion is
    one line in :func:`viewscope.resolve_viewscope`, and it belongs on the side that owns
    the primitive vocabulary — this module has no business validating a primitive.
    """

    group: str
    primitive: str
    field: str
    label: str = ""


@dataclass(frozen=True)
class ArchetypeClass:
    """One node of the denotation tree."""

    name: str
    organizer: str
    container: str
    parent: str = ""
    members: tuple[str, ...] = ()
    slots: tuple[SlotSpec, ...] = ()
    document_id: str = ""

    @property
    def is_leaf(self) -> bool:
        """A class that names members is a leaf; one that only groups is a branch.

        The distinction is what makes the partition checkable: an archetype belongs to
        exactly one LEAF, and every leaf's members are disjoint. A branch (``profile``,
        ``record``, ``log``) carries the organizer and the container its leaves inherit.
        """
        return bool(self.members)


class ClassRegistry:
    """The declared classes, and the archetype -> class binding they induce."""

    def __init__(self, classes: tuple[ArchetypeClass, ...]) -> None:
        self._classes = classes
        self._by_name = {c.name: c for c in classes}
        self._of_archetype: dict[str, str] = {}
        for klass in classes:
            for member in klass.members:
                # First declaration wins and the partition check reports the collision,
                # rather than the binding resolving by iteration order — which is the same
                # rule `ambiguities()` applies one level down, and for the same reason.
                self._of_archetype.setdefault(member, klass.name)

    def __len__(self) -> int:
        return len(self._classes)

    @property
    def classes(self) -> tuple[ArchetypeClass, ...]:
        return self._classes

    def get(self, name: str) -> ArchetypeClass | None:
        return self._by_name.get(as_text(name))

    def class_of(self, archetype: str) -> str:
        """The leaf class ``archetype`` belongs to, or ``""``."""
        return self._of_archetype.get(as_text(archetype), "")

    def ancestry(self, name: str) -> tuple[str, ...]:
        """``name`` and every class above it, nearest first.

        Cycle-safe: a parent chain that loops stops at the repeat rather than hanging, so a
        malformed library degrades to a short answer instead of a wedged request. The cycle
        itself is reported by :func:`partition_problems`, which is where a defect belongs.
        """
        out: list[str] = []
        seen: set[str] = set()
        current = as_text(name)
        while current and current not in seen:
            seen.add(current)
            out.append(current)
            klass = self._by_name.get(current)
            current = klass.parent if klass is not None else ""
        return tuple(out)

    def lineage_of(self, archetype: str) -> tuple[str, ...]:
        """Every class ``archetype`` inherits from, nearest first. Empty when unclassed."""
        leaf = self.class_of(archetype)
        return self.ancestry(leaf) if leaf else ()

    def organizer_of_class(self, name: str) -> str:
        """The nearest declared organizer at or above the CLASS ``name``, or ``""``."""
        for ancestor in self.ancestry(name):
            klass = self._by_name.get(ancestor)
            if klass is not None and klass.organizer:
                return klass.organizer
        return ""

    def organizer_of(self, archetype: str) -> str:
        """The nearest declared organizer above the ARCHETYPE ``archetype``, or ``""``."""
        leaf = self.class_of(archetype)
        return self.organizer_of_class(leaf) if leaf else ""

    def drawing_for(self, archetype: str) -> tuple[str, tuple[SlotSpec, ...], str]:
        """``(container, slots, declaring_class)`` for ``archetype``, or ``("", (), "")``.

        The nearest class up the chain that declares any slots wins WHOLE — its container
        and its slots together. Merging a leaf's slots into an ancestor's was the other
        option and it is worse: two classes would each hold half of one layout, and the
        order the halves interleave in would be decided by the walk rather than by anyone.
        A leaf that wants a different arrangement declares the whole arrangement.
        """
        for name in self.lineage_of(archetype):
            klass = self._by_name.get(name)
            if klass is not None and klass.slots:
                return klass.container, klass.slots, klass.name
        return "", (), ""


def _head(row: Any) -> list[Any] | None:
    raw = row.get("raw") if isinstance(row, dict) else getattr(row, "raw", None)
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return list(raw[0])
    return None


def _address(row: Any) -> str:
    if isinstance(row, dict):
        return as_text(row.get("datum_address"))
    return as_text(getattr(row, "datum_address", ""))


def _tail_label(row: Any) -> str:
    raw = row.get("raw") if isinstance(row, dict) else getattr(row, "raw", None)
    if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], list) and raw[1]:
        return decode_label(raw[1][0])
    return ""


def _is_class_document(document: Any) -> bool:
    metadata = getattr(document, "document_metadata", None)
    if not isinstance(metadata, dict):
        return False
    return as_text(metadata.get(ROLE_KEY)) == ROLE_VALUE


def _document_name(document: Any) -> str:
    name = as_text(getattr(document, "canonical_name", ""))
    if name:
        return name
    parts = as_text(getattr(document, "document_id", "")).split(".")
    return parts[3] if len(parts) > 4 else ""


def load_class(document: Any) -> tuple[ArchetypeClass | None, list[str]]:
    """Read one ``class_<name>`` document, plus why any row was ignored.

    An unknown organizer is REFUSED rather than passed through: the organizer is what
    selects the container, so a class carrying one nothing implements would silently draw
    its members with the fallback and look like a rendering bug three layers away.
    """
    problems: list[str] = []
    if not _is_class_document(document):
        return None, problems
    name = name_of(_document_name(document))
    if not name:
        return None, problems

    organizer = container = parent = ""
    members: list[str] = []
    slots: list[SlotSpec] = []
    for row in getattr(document, "rows", ()) or ():
        head = _head(row)
        if head is None:
            continue
        address = _address(row)
        values = [decode_label(magnitude) for _marker, magnitude in iter_marker_pairs(head)]
        if address.startswith(HEADER_FAMILY + "-"):
            organizer, container, parent = [*values, "", "", ""][:3]
            organizer, container, parent = as_text(organizer), as_text(container), as_text(parent)
            if organizer and organizer not in ORGANIZERS:
                problems.append(f"{name}: unknown organizer {organizer!r}")
                return None, problems
        elif address.startswith(MEMBER_FAMILY + "-"):
            member = as_text(values[0] if values else "")
            if not member:
                problems.append(f"{address}: member row names no archetype")
                continue
            members.append(member)
        elif address.startswith(SLOT_FAMILY + "-"):
            group, primitive, field_name = [*values, "", "", ""][:3]
            field_name = as_text(field_name)
            if not field_name:
                problems.append(f"{address}: slot names no field")
                continue
            slots.append(
                SlotSpec(
                    group=as_text(group),
                    primitive=as_text(primitive),
                    field=field_name,
                    label=_tail_label(row),
                )
            )

    if not organizer and not parent:
        problems.append(f"{name}: declares neither an organizer nor a parent")
        return None, problems
    return (
        ArchetypeClass(
            name=name,
            organizer=organizer,
            container=container or CONTAINER_FOR_ORGANIZER.get(organizer, ""),
            parent=parent,
            members=tuple(members),
            slots=tuple(slots),
            document_id=as_text(getattr(document, "document_id", "")),
        ),
        problems,
    )


def load_classes(documents: Any) -> tuple[ClassRegistry, list[str]]:
    """Every class in the catalog, as a registry."""
    out: dict[str, ArchetypeClass] = {}
    problems: list[str] = []
    for document in documents:
        klass, reasons = load_class(document)
        problems.extend(reasons)
        if klass is None:
            continue
        if klass.name in out:
            problems.append(f"{klass.name}: declared by more than one document")
            continue
        out[klass.name] = klass
    ordered = tuple(out[k] for k in sorted(out))
    # A container a class inherits rather than declares is resolved HERE, once, so every
    # reader sees the same answer. Doing it at read time in each caller is how two surfaces
    # come to disagree about what a class is.
    resolved: list[ArchetypeClass] = []
    registry = ClassRegistry(ordered)
    for klass in ordered:
        container = klass.container
        organizer = klass.organizer
        if not container or not organizer:
            for ancestor in registry.ancestry(klass.name)[1:]:
                above = registry.get(ancestor)
                if above is None:
                    continue
                container = container or above.container
                organizer = organizer or above.organizer
                if container and organizer:
                    break
        resolved.append(
            ArchetypeClass(
                name=klass.name,
                organizer=organizer,
                container=container or CONTAINER_FOR_ORGANIZER.get(organizer, ""),
                parent=klass.parent,
                members=klass.members,
                slots=klass.slots,
                document_id=klass.document_id,
            )
        )
    return ClassRegistry(tuple(resolved)), problems


def partition_problems(classes: ClassRegistry, archetype_names: Any) -> list[str]:
    """Is every archetype in exactly ONE leaf class? Reported in BOTH directions.

    This is what a class library has instead of "the document is its own denotation". The
    direction that matters is the second one: a class naming an archetype that does not
    exist is loud the first time anything reads it, while an archetype no class names is
    silent — it simply never inherits a viewscope, which is indistinguishable from the
    orphan state this whole layer exists to end.
    """
    problems: list[str] = []
    known = {as_text(name) for name in archetype_names}

    owners: dict[str, list[str]] = {}
    for klass in classes.classes:
        for member in klass.members:
            owners.setdefault(member, []).append(klass.name)
    for member, holders in sorted(owners.items()):
        if member not in known:
            problems.append(f"class {holders[0]!r} names {member!r}, which is not an archetype")
        if len(holders) > 1:
            problems.append(
                f"{member!r} is claimed by {len(holders)} classes ({', '.join(sorted(holders))}) — "
                "an archetype in two classes has no class, because the binding would resolve "
                "by iteration order"
            )
    for name in sorted(known - set(owners)):
        problems.append(f"archetype {name!r} belongs to no class")

    for klass in classes.classes:
        if klass.parent and classes.get(klass.parent) is None:
            problems.append(f"class {klass.name!r} names parent {klass.parent!r}, which is not a class")
        chain = classes.ancestry(klass.name)
        parent_of_last = classes.get(chain[-1])
        if parent_of_last is not None and parent_of_last.parent:
            problems.append(f"class {klass.name!r} sits on a parent CYCLE: {' -> '.join(chain)}")
        if not classes.organizer_of_class(klass.name):
            problems.append(f"class {klass.name!r} inherits no organizer")
    return problems


def build_class_rows(klass: ArchetypeClass, *, namespace: str = _fr.ARCHETYPE) -> list[dict[str, Any]]:
    """A class as datum rows. The inverse of :func:`load_class`."""
    title = _fr.marker(namespace, "title")
    rows: list[dict[str, Any]] = [
        {
            "datum_address": f"{HEADER_FAMILY}-1",
            "raw": [
                [f"{HEADER_FAMILY}-1", title, klass.organizer, title, klass.container,
                 title, klass.parent],
                ["class"],
            ],
        }
    ]
    for index, member in enumerate(klass.members, start=1):
        address = f"{MEMBER_FAMILY}-{index}"
        rows.append(
            {"datum_address": address, "raw": [[address, title, member], [member]]}
        )
    for index, slot in enumerate(klass.slots, start=1):
        address = f"{SLOT_FAMILY}-{index}"
        label = slot.label or slot.field.replace("_", " ")
        rows.append(
            {
                "datum_address": address,
                "raw": [
                    [address, title, slot.group, title, slot.primitive, title, slot.field],
                    [label],
                ],
            }
        )
    return rows


__all__ = [
    "CLASS_PREFIX",
    "CONTAINER_FOR_ORGANIZER",
    "HEADER_FAMILY",
    "MEMBER_FAMILY",
    "ORGANIZERS",
    "ROLE_KEY",
    "ROLE_VALUE",
    "SLOT_FAMILY",
    "ArchetypeClass",
    "ClassRegistry",
    "SlotSpec",
    "build_class_rows",
    "class_name",
    "load_class",
    "load_classes",
    "name_of",
    "partition_problems",
]
