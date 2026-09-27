"""The registrar's event vocabulary, found in its local domain BY LABEL.

An event entry names its class through the log's scaffold, and its kind, chronology
structure, time unit and cadence by local-domain references. Until 2026-09-09 those lived at
fixed addresses — classes ``1-3-K``, kinds ``1-3-8-K``, structures ``1-5-K``, units ``1-6-K``,
cadence ``1-4-*``, ag categories ``1-2-K`` — and four readers and writers keyed their tables on
them. The local-domain base structure migration moved the registrar's whole classification
under one object (``objects / mycelium_classification``: ``event_class``, ``event_kind`` as its
seventh child, ``chronology_structure``, ``time_unit``, ``cadence``, ``ag_profile``) and kept
the LEAF NUMBERING, so every reference changed its prefix and no table matched: on the live
network map every event drew the generic glyph in group "other" with no kind, the calendar's
cadence read as raw addresses, the registrar's event writer refused every class it was asked
for, and the micyte.com offering export skipped every entry as malformed (2026-09-25).

This module is the one place that knows the shape. The roots are found by their labels in
the tree (``from_log``), with the pre-migration addresses as the fallback for a tree that
predates them (``LEGACY``); a reference is classified by the root it sits under, and every
table keys on the reference's LEAF ORDINAL (``ordinal``), which the migration preserved and
which the offering's wire format already carries. A caller holding a pre-migration address
translates it to the tree's (``translate``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: The labels the roots wear in the registrar's tree.
CLASS_LABEL = "event_class"
KIND_LABEL = "event_kind"
STRUCTURE_LABEL = "chronology_structure"
UNIT_LABEL = "time_unit"
CADENCE_LABEL = "cadence"
CATEGORY_LABEL = "ag_profile"
ENTITY_LABEL = "entity_class"

#: Asked in this order: a kind sits UNDER the class root; under the legacy shape the entity
#: root ``1-1`` is a prefix of nothing else, and under the migrated tree it is found by label.
ROLES = ("kind", "class", "structure", "unit", "cadence", "category", "entity")


def ordinal(ref: Any) -> int:
    """The leaf ordinal of a local-domain reference — ``1-3-1-3-4`` and ``1-3-4`` are both
    class 4. ``0`` for a blank or malformed reference."""
    text = str(ref or "").strip()
    tail = text.rsplit("-", 1)[-1] if text else ""
    return int(tail) if tail.isdigit() else 0


@dataclass(frozen=True)
class EventVocabulary:
    class_root: str
    kind_root: str
    structure_root: str
    unit_root: str
    cadence_root: str
    category_root: str
    entity_root: str = ""

    @classmethod
    def from_log(cls, log: Any) -> EventVocabulary:
        """The roots by label from a :class:`LocalDomainLog` (or anything with ``entries``
        of ``label``-bearing nodes); a root the tree lacks keeps its legacy address."""
        by_label: dict[str, str] = {}
        entries = getattr(log, "entries", None) or {}
        for node, entry in entries.items():
            label = str(getattr(entry, "label", "") or "")
            if label and label not in by_label:
                by_label[label] = str(node)
        return cls(
            class_root=by_label.get(CLASS_LABEL, LEGACY.class_root),
            kind_root=by_label.get(KIND_LABEL, LEGACY.kind_root),
            structure_root=by_label.get(STRUCTURE_LABEL, LEGACY.structure_root),
            unit_root=by_label.get(UNIT_LABEL, LEGACY.unit_root),
            cadence_root=by_label.get(CADENCE_LABEL, LEGACY.cadence_root),
            category_root=by_label.get(CATEGORY_LABEL, LEGACY.category_root),
            entity_root=by_label.get(ENTITY_LABEL, LEGACY.entity_root),
        )

    def root(self, role: str) -> str:
        return getattr(self, f"{role}_root")

    @staticmethod
    def _under(ref: str, root: str) -> bool:
        return bool(root) and (ref == root or ref.startswith(root + "-"))

    def role_of(self, ref: Any) -> str:
        """``"kind"``, ``"class"``, ``"structure"``, ``"unit"``, ``"cadence"``, ``"category"``
        or ``""``. Kinds sit UNDER the class root, so they are asked first."""
        text = str(ref or "").strip()
        if not text:
            return ""
        for role in ROLES:
            if self._under(text, self.root(role)):
                return role
        return ""

    def below(self, role: str, ref: Any) -> tuple[int, ...]:
        """The ordinals of ``ref`` below ``role``'s root — ``(1, 4)`` for the producer's
        fourth child — or ``()`` when ``ref`` is not under that root."""
        text = str(ref or "").strip()
        root = self.root(role)
        if not self._under(text, root):
            return ()
        tail = text[len(root):].strip("-")
        return tuple(int(part) for part in tail.split("-") if part.isdigit()) if tail else ()

    def is_(self, role: str, ref: Any) -> bool:
        return self.role_of(ref) == role

    def node(self, role: str, *ordinals: int) -> str:
        """The reference of ``ordinals`` under ``role``'s root in THIS tree."""
        return "-".join([self.root(role), *(str(int(o)) for o in ordinals)])

    def translate(self, ref: Any) -> str:
        """``ref`` as this tree spells it: a reference already under one of this tree's roots
        is returned as is; one under a LEGACY root is rebuilt under the same role here,
        keeping every ordinal below the root; anything else is returned unchanged."""
        text = str(ref or "").strip()
        if not text or self.role_of(text):
            return text
        role = LEGACY.role_of(text)
        if not role:
            return text
        below = text[len(LEGACY.root(role)):].strip("-")
        return "-".join([self.root(role), *below.split("-")]) if below else self.root(role)


#: The pre-2026-09-09 shape, and the fallback for a tree that carries no such labels.
LEGACY = EventVocabulary(
    class_root="1-3", kind_root="1-3-8", structure_root="1-5", unit_root="1-6",
    cadence_root="1-4", category_root="1-2", entity_root="1-1",
)

#: The chronology structures by leaf ordinal, and the log document each one's entries live in.
STRUCTURE_QC, STRUCTURE_HC, STRUCTURE_LC = 2, 3, 4
LOG_BY_STRUCTURE_ORDINAL = {STRUCTURE_QC: "qc_log", STRUCTURE_HC: "hc_log", STRUCTURE_LC: "lc_log"}
#: The event kinds and time units by leaf ordinal.
KIND_OPEN_HOURS, KIND_OFF_SEASON, KIND_HOLIDAY = 1, 2, 3
UNIT_DAY, UNIT_HOUR, UNIT_MINUTE = 1, 2, 3


def log_for_structure(ref: Any) -> str:
    """The log document for a chronology structure reference, by its ordinal; ``""`` when
    the ordinal names no chronology."""
    return LOG_BY_STRUCTURE_ORDINAL.get(ordinal(ref), "")


__all__ = [
    "CADENCE_LABEL", "CATEGORY_LABEL", "CLASS_LABEL", "ENTITY_LABEL", "KIND_HOLIDAY", "KIND_LABEL",
    "KIND_OFF_SEASON", "KIND_OPEN_HOURS", "LEGACY", "LOG_BY_STRUCTURE_ORDINAL", "ROLES",
    "STRUCTURE_HC", "STRUCTURE_LABEL", "STRUCTURE_LC", "STRUCTURE_QC", "UNIT_DAY", "UNIT_HOUR",
    "UNIT_LABEL", "UNIT_MINUTE", "EventVocabulary", "log_for_structure", "ordinal",
]
