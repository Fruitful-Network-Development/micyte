"""The local domain LOG — a node may denote a document, and the log is where it says so.

A local domain document has always answered one question per row: *what is this node
called*. From 2026-08-19 it answers a second one for the rows that have it to give: *which
document does this node denote*. The operator's words: "create a type of lcl_id entry that
not only associates a title to that node address, but ... defines that node as a 'pointer'
in essence to that document."

## The address IS the arity

A datum address is ``<layer>-<value_group>-<iteration>`` and **value_group is the tuple
count** (:mod:`micyte.core.mss.document_codec`: "the VG number = tuple count"). So the two
shapes a local domain row can take are not a convention this module invents — they are
where the rows already have to live:

======================================================  ===========================
``4-2-N``  ``[addr, lcl_id, <node>, title, <bits>]``     a node
``4-3-N``  ``[addr, lcl_id, <node>, title, <bits>,       a node that DENOTES a document
            lcl_id, <slot>]``
======================================================  ===========================

``<slot>`` is a child of the **meta root** — the reserved branch whose children are
document slots — and the datum document it names is CALLED that slot (``lv.<msn>.<sandbox>
.1-7.<hash>``). That is the whole change: the association used to ride the document's
filename (``note_2-1-3_yes``) and now rides a cell.

## Exactly one definition row per node

Attaching a document MOVES a node's row from ``4-2-*`` to ``4-3-*``; detaching moves it
back. Never both. :class:`~micyte.core.datum_ops.datum_resolve.NameIndex` resolves a label
by ``setdefault`` — first row in document order wins — and ``LclBuilder.ensure`` already
records what a second definition row costs: "Two definition rows make a node's label
order-dependent and its kind ambiguous." One row per node is what lets every existing
reader (:func:`defined_node_addrs`, :func:`node_kind_index`, :func:`view_token_index`) keep
working untouched: they match by SHAPE, not by address family.

## What a slot's TITLE carries

The slot node's label is the DOCUMENT's title — which is what makes "the drop-down should
simply display the titles of the datum docs, not the lcl_id's" one read of the tree rather
than a second index.

An ANSWER is a slot titled ``<node> <option>`` (``2-1-3 yes``). That is the operator's own
naming from 2026-08-19, moved off the filename and onto the title cell. The leaf rule is
untouched by it: an answer is still a document, never a child node, so a node that poses a
question in a writing still takes no children.

## The meta root is found by LABEL

The operator named node ``1``. This module finds it by its reserved label anyway, the way
``actions_root`` finds the actions branch — ``insert_node`` can re-key any address, and a
hardcoded ``1`` would be a second statement of a fact the tree already carries. Seeding and
the migration put it at ``1``; a tree that later moves it keeps working.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from micyte.core.structures.samras.structure import as_text

from .datum_resolve import NODE_KIND_TYPE, decode_label, kind_of_marker
from .node_addrs import parent_of
from .refs import _head, _is_definition_head, is_node_addr_reference, is_node_ref_marker

#: THE BASE STRUCTURE every local domain carries (operator, 2026-09-08), found by LABEL
#: at every level — the ordinals are only where the SEED puts it, because `insert_node`
#: can re-key any address and a reader that trusted an ordinal would break on the first
#: tree that moved.
#:
#:     1        local_domain                      ROOT_LABEL
#:     1-1      meta                              META_LABEL
#:     1-1-1    glyphs      1-1-1-n  a drawing    GLYPH_BRANCH_LABEL
#:     1-1-2    documents   1-1-2-n  a slot       DOCUMENT_BRANCH_LABEL (reserved 1, 2)
#:     1-1-3    sources     1-1-3-n  a pin        SOURCE_BRANCH_LABEL
#:     1-1-4    artifacts   1-1-4-k  a KIND       ARTIFACT_BRANCH_LABEL / ARTIFACT_KINDS
#:     1-2      classes     1-2-k    a vocabulary CLASS_BRANCH_LABEL / CLASS_KINDS
#:     1-3      objects     free-form             OBJECT_BRANCH_LABEL
#:
#: ONE root. The operator's own tree, which was root `2` (and root `1` on five live trees
#: whose meta sat at `2`), is the `objects` branch's children. A second top-level node is
#: no longer a shape this module writes, and since the 25 live trees migrated
#: (2026-09-09) not one it reads either: the pre-2026-09-08 shape — a root labelled
#: `documents` with `icons`/`documents` beneath — is read by exactly one program,
#: `migrate_local_domain_base._read_legacy_log`, which needs it in order to leave it.
ROOT_LABEL = "local_domain"
META_LABEL = "meta"
META_ORDINAL = 1
CLASS_BRANCH_LABEL = "classes"
CLASS_BRANCH_ORDINAL = 2
OBJECT_BRANCH_LABEL = "objects"
OBJECT_BRANCH_ORDINAL = 3
#: The three vocabularies under `classes`, in ordinal order: 'type' denotations the
#: interface offers when a datum document is created (archetypes), the babelette chains
#: an anchor declares (datum_types), and the kinds of dated thing the calendar draws.
CLASS_KINDS: tuple[str, ...] = ("archetypes", "datum_types", "events")
#: The four kinds under `artifacts`, in ordinal order. An artifact slot hangs UNDER its
#: kind (`1-1-4-1-n`), which is how a client's Resources tab derives its subtabs.
ARTIFACT_KINDS: tuple[str, ...] = ("image", "record", "video", "memo")

#: The label a ROOT must carry for its children to be the document namespace — the
#: PRE-2026-09-08 meta root. Still read (every live tree carries it until Phase 3 of
#: TASK-2026-09-08-001 migrates it); never seeded again.
DOCUMENT_ROOT_LABEL = "documents"

#: THE FLOOR. Every definition row wears a glyph, so the least a row may be is `4-3`
#: (node, title, glyph) and a row that denotes something is `4-4`. `4-2` is READ — every
#: live tree still has them — and never written where there is a glyph to wear:
#: `LclBuilder._add_row` defaults the glyph and `set_node_icon` refuses to take one away.
#: A tree with no glyph branch at all (the pre-migration shape) keeps writing `4-2`,
#: because a default glyph that does not exist would be a dangling reference written into
#: every node at once — the 2026-08-20 lesson.
DEFAULT_GLYPH = "circle"
#: The canonical drawings every sandbox holds under `glyphs`, in slot order — `circle`
#: first because it is the default every ordinary node wears. Eleven, not twelve: FND's
#: `glyph` library carries a twelfth document that is its own icon-branch copy of `circle`.
CANONICAL_GLYPHS: tuple[str, ...] = (
    "circle", "disc", "dot", "ring", "square", "document", "folder", "anchor mark",
    "log", "link", "code brackets",
)
#: What the STRUCTURAL nodes wear, by role. Fixed rather than chosen: a structural node is
#: the same thing in every sandbox, so it looks the same in every sandbox.
STRUCTURAL_GLYPHS: dict[str, str] = {
    ROOT_LABEL: "ring", META_LABEL: "folder", "glyphs": "dot", "documents": "document",
    "sources": "link", "artifacts": "square", CLASS_BRANCH_LABEL: "code brackets",
    OBJECT_BRANCH_LABEL: "disc", "anchor": "anchor mark", "local_domain_slot": "log",
    "image": "square", "record": "document", "video": "square", "memo": "document",
    "archetypes": "code brackets", "datum_types": "code brackets", "events": "log",
}

#: The meta root's THREE branches, found by label exactly as the meta root itself is.
#:
#: The operator's numbering (2026-08-20): "canonicalizing icons as child nodes of ``1-1``
#: and all other documents as child nodes under ``1-2``". The split is not filing tidiness
#: — it is what makes a third reference SELF-DESCRIBING. An icon reference and a document
#: reference are both an ``lcl_id`` marker naming a node, so nothing in the cell tells them
#: apart; once icons live under one branch and documents under the other, the ADDRESS does,
#: and one row family can carry either.
#: The third branch, added 2026-08-23 for the `artifact` datum type (plan P5): a file
#: whose bytes are datum rows, filed by the node that denotes it exactly as a document is.
#:
#: ORDINAL 3 UNDER THE META ROOT, never the literal address `1-3`. Measured across all 13
#: live trees: the meta root is `1` in seven and `2` in six, so `artifacts` lands at `1-3`
#: in seven and `2-3` in six. Writing `1-3` would file artifacts into the ORDINARY domain
#: tree of the other six — where `1-3` is already `classification` or `event_class` in four
#: of them. Ordinal 3 under the correct meta root is free in 13 of 13, which is the only
#: reason this can be additive the way the 2026-08-20 documents retrofit was.
#: `glyphs` since 2026-09-08 (the operator's word). `icons` is the spelling every live
#: tree carries and is READ as the same branch; the seed writes `glyphs`.
GLYPH_BRANCH_LABEL = "glyphs"
ICON_BRANCH_LABEL = "icons"
DOCUMENT_BRANCH_LABEL = "documents"
SOURCE_BRANCH_LABEL = "sources"
ARTIFACT_BRANCH_LABEL = "artifacts"
GLYPH_BRANCH_ORDINAL = 1
ICON_BRANCH_ORDINAL = GLYPH_BRANCH_ORDINAL
DOCUMENT_BRANCH_ORDINAL = 2
SOURCE_BRANCH_ORDINAL = 3
#: 4 under the canonical meta (`1-1-4`). It was ordinal 3 under the legacy meta from
#: 2026-08-23 to 2026-09-08 and no live tree ever minted it, which is what let it move.
ARTIFACT_BRANCH_ORDINAL = 4

#: The three families a definition row can live in. Stated here rather than spelled at each
#: reader, because they are one fact — a row's arity — written three ways.
#:
#: ``4-3`` widened rather than split on 2026-08-20. It used to mean "denotes a document";
#: it now means "carries one further lcl reference", and which KIND that is comes from the
#: branch the address sits under. A fourth family for "icon" would have been a second way
#: to say the same arity, and the address is the arity.
NODE_FAMILY = "4-2"
REF_FAMILY = "4-3"
FULL_FAMILY = "4-4"

#: The families the BASE shapes live in, in arity order: a node (2 pairs), a node wearing
#: a glyph or denoting a document (3), a node doing both (4). NOT every family a definition
#: row can live in: a row minted with further pairs — a record container's VIEW marker, a
#: source's pin — carries one pair more per extra and lives one family higher, because the
#: address IS the arity (I7). Readers that mean "is this row a node definition at all"
#: ask :func:`is_definition_address` and the head's shape, never these names; six readers
#: matched these prefixes until 2026-09-29 and would have been blind to a five-pair row.
DEFINITION_FAMILIES: tuple[str, ...] = (NODE_FAMILY, REF_FAMILY, FULL_FAMILY)
#: The same, as address PREFIXES — for the base shapes only (see above).
DEFINITION_PREFIXES: tuple[str, ...] = tuple(f"{family}-" for family in DEFINITION_FAMILIES)


def is_definition_row(address: Any, head: Any) -> bool:
    """Is this lcl row a node definition — a layer-4 row whose head opens with a node?

    Looser than `refs._is_definition_head` on purpose: that predicate also requires a
    KNOWN node-ref marker, and the tree must still see a node written on a marker nobody
    classified (the delete verbs refuse to sweep exactly those — "unclassified" is a
    finding, not an invisibility). In the local domain document every layer-4 row is a
    definition row or the structural blank, so the shape asked here is the node itself.
    """
    if not is_definition_address(address) or not isinstance(head, list) or len(head) < 3:
        return False
    from micyte.core.datum_ops.refs import is_node_addr_reference

    return is_node_addr_reference(head[2])


def is_definition_address(address: Any) -> bool:
    """Could ``address`` hold a node definition row — is it an instance (layer-4) row?

    The family says the arity, not the kind; the KIND is the head's shape
    (`refs._is_definition_head`: an id-pair on a node marker, then a title). A reader
    that filters on a family tuple decides the arity a node may have, and no reader has
    that authority.
    """
    text = str(address or "")
    parts = text.split("-")
    return len(parts) == 3 and parts[0] == "4" and all(p.isdigit() for p in parts)

#: What separates a node address from an OPTION in a slot's title. A space, because a title
#: is 64 characters of printable ASCII that a person reads, and ``2-1-3 yes`` is what the
#: operator wrote. A node address cannot contain one, which is what lets the split be exact.
OPTION_SEP = " "

#: What a document created on the domain surface can BE — ``token -> (archetype, label)``.
#:
#: The operator asked for text, contacts and event logs and nothing else. Each is an
#: archetype the library already holds, so a created document is a blank INSTANCE of a real
#: shape rather than a file whose kind nothing can check; a kind with nothing behind it
#: would be a picker entry producing a document no tool can open.
#:
#: Declared HERE rather than in the write runtime because the surface and the writer both
#: need it and two lists of what a document may be is how a picker offers a kind the writer
#: refuses (the ``JOB_LOG`` rule).
DOCUMENT_KINDS: dict[str, tuple[str, str]] = {
    "text": ("text_note", "Text"),
    "contacts": ("natural_entity_profile", "Contacts"),
    "event_log": ("event_log_entry", "Event log"),
}

#: A title is one title babelette: 64 characters of printable ASCII. Longer is refused with
#: the overage named rather than truncated — a document whose title is silently cut is one
#: an operator cannot find by the name they gave it.
TITLE_CHARS = 64

#: The two slots every log RESERVES, in the operator's own numbering (2026-08-20): the
#: first names the sandbox's anchor and the second names the log itself.
#:
#: They are reserved rather than minted because they are the two documents a sandbox cannot
#: be without — a sandbox with no anchor "has no namespace at all and is not a sandbox this
#: or any tool can be installed into" (``instance_baseline``), and a sandbox with no log has
#: no namespace to file anything INTO. Reserving them is what makes the id space COMPLETE:
#: with the anchor at ``1-1`` and the log at ``1-2``, every document in an adopted sandbox
#: has an lcl id, which is the property that makes "a single name space" true rather than
#: nearly true.
#:
#: Both keep their reserved FILENAMES. The operator's first brief exempted "the local domain
#: log doc itself or the anchor file" from lcl_id naming, and the exemption is load-bearing
#: in a way the exemption for any other document would not be: every reader of a sandbox
#: finds its anchor and its log BY NAME, and a document that can only be found through the
#: log cannot be the log.
ANCHOR_SLOT_ORDINAL = 1
LOG_SLOT_ORDINAL = 2

#: The first ordinal a MINTED document slot may take. Not a style choice: a slot below it
#: would collide with a reserved one, and the collision would read as a document that had
#: quietly become the anchor.
FIRST_FREE_SLOT_ORDINAL = 3

#: What the reserved slots are TITLED — the operator's own names for the two documents
#: (2026-09-08): `anchor` and `local_domain`. The title IS the document's name here, which
#: is the one place a slot's title and its document's name agree by construction.
RESERVED_SLOT_TITLES: dict[int, str] = {
    ANCHOR_SLOT_ORDINAL: "anchor",
    LOG_SLOT_ORDINAL: "local_domain",
}
#: What they were titled from 2026-08-20 to 2026-09-08, still on every live tree until
#: Phase 3 of TASK-2026-09-08-001 retitles them. `is_reserved` accepts either, because a
#: reserved slot that stopped being reserved on a relabel would let a customer's document
#: take the anchor's id — the exact hazard the title check exists to close.
LEGACY_RESERVED_SLOT_TITLES: dict[int, str] = {
    ANCHOR_SLOT_ORDINAL: "Anchor",
    LOG_SLOT_ORDINAL: "Local domain log",
}

_ADDRESS = re.compile(r"^[0-9]+(?:-[0-9]+)*$")


def is_node_address(text: str) -> bool:
    """``2-1-3`` yes, ``1`` yes, ``services`` no, ``2-1-3 yes`` no."""
    return bool(_ADDRESS.match(as_text(text)))


def option_slug(option: str) -> str:
    """An option's storable form: lowercase, ``a-z0-9-``, and never a space.

    A space is the separator :func:`parse_slot_title` splits on, so an option carrying one
    would put the split in the wrong place and the answer would read back as an unattached
    document. A dash is kept because it cannot be confused with the separator and reads the
    way somebody would type "not sure".
    """
    out: list[str] = []
    for ch in as_text(option).strip().lower():
        if ch.isascii() and ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")


def slot_title(node: str, option: str = "") -> str:
    """The title an ANSWER's slot carries: ``2-1-3 yes``. Inverse of :func:`parse_slot_title`."""
    slug = option_slug(option)
    return f"{as_text(node)}{OPTION_SEP}{slug}" if slug else as_text(node)


def parse_slot_title(title: str) -> tuple[str, str]:
    """``(node, option)`` for a title that names one, else ``("", "")``.

    ``2-1-3 yes`` -> ``("2-1-3", "yes")``; ``Driveway cleaning`` -> ``("", "")``. Split at
    the FIRST space and ask whether the left half is an address — an option is one word by
    construction (:func:`option_slug`), so anything after a second space is prose that
    merely starts with something address-shaped.
    """
    text = as_text(title).strip()
    head, sep, tail = text.partition(OPTION_SEP)
    if not sep or not tail or " " in tail:
        return "", ""
    if not is_node_address(head):
        return "", ""
    return head, tail


def checked_title(title: str) -> tuple[str, str]:
    """``(title, error)`` — printable ASCII, one line, within the babelette.

    Here rather than in the write runtime because two verbs need it — creating a document
    and retitling its slot — and a second copy is how one of them starts accepting a title
    the other refuses.
    """
    text = as_text(title).strip()
    if not text:
        return "", "a document needs a title — it is what the tree and the picker show"
    bad = {ch for ch in text if not (32 <= ord(ch) <= 126)}
    if bad:
        return "", (f"the title carries {''.join(sorted(bad))!r}, which a title babelette "
                    "cannot store — it is fixed-width printable ASCII")
    if len(text) > TITLE_CHARS:
        return "", (f"this title is {len(text)} characters; a title holds at most "
                    f"{TITLE_CHARS}. Trim {len(text) - TITLE_CHARS}.")
    return text, ""


# ---------------------------------------------------------------------------- markers


def domain_markers(namespace: str) -> tuple[str, str]:
    """``(node marker, title marker)`` for one namespace's local domain rows.

    Which marker says "type" varies by anchor and always has: the farm/taxonomy stack
    carries a type on ``txa_id`` (``rf.3-1-1``) while the registrar's ``lcl`` is a pure
    vocabulary riding ``lcl_id`` (``rf.3-1-13``) throughout. Both read as a TYPE through
    ``_KIND_BY_MARKER``; the wrong one for a namespace is not an error, it is a cell that
    means something else — in the registrar numbering ``rf.3-1-1`` is
    ``HOPS-babelette-coordinate`` and ``rf.3-1-2`` is ``SAMRAS-babelette-msn_id``.

    That is not hypothetical. Measured on BPW's live ``oveure`` lcl on 2026-08-19: the
    seeded root (written through the registry) folds to ``L4:lcl_id,title`` while every row
    ``mint_child`` wrote folds to ``L4:coordinate,msn_id``. It broke nothing while nothing
    read the fold; it breaks the moment an ARCHETYPE has to recognise these rows.

    A namespace in which no candidate reads as a type is REFUSED by name — ``system`` is
    such a namespace, which is why a local domain cannot live in an FND-numbered sandbox.
    """
    from . import field_registry as fr

    tried: list[str] = []
    for field in ("txa_id", "lcl_id"):
        try:
            node_marker = fr.marker(namespace, field)
            title_marker = fr.marker(namespace, "title")
        except KeyError:
            tried.append(field)
            continue
        if kind_of_marker(node_marker) == NODE_KIND_TYPE:
            return node_marker, title_marker
        tried.append(field)
    raise ValueError(
        f"the {as_text(namespace) or '?'} namespace cannot express a local-domain type "
        f"node (tried {', '.join(tried)}) — a row written here would be one the editor "
        "cannot read, so it is refused instead"
    )


# ---------------------------------------------------------------------------- the log


@dataclass(frozen=True)
class Entry:
    """One node's single definition row, whichever family it lives in."""

    node: str
    label: str
    #: The document slot this node denotes, or ``""``. A child of the log's DOCUMENT
    #: branch, and the NAME of the datum document itself.
    slot: str
    #: Where the row is, so a writer can replace exactly it.
    address: str
    #: The icon slot this node wears, or ``""``. A child of the log's ICON branch, and the
    #: name of a glyph document imported from the ``glyph`` library.
    icon: str = ""
    #: The ARTIFACT this node denotes, or ``""``. A child of the log's ARTIFACT branch.
    #:
    #: NOT A THIRD TRAILING REFERENCE — the arity is unchanged, and that matters because
    #: THE ADDRESS IS THE ARITY. A head carries at most two references (`FULL_FAMILY`,
    #: `4-4`): the icon it wears and the ONE thing it denotes. `artifact` and `slot` are
    #: two readings of that single denotation, told apart by the branch the reference sits
    #: under — exactly as `4-3`'s own note already says: "it now means 'carries one further
    #: lcl reference', and which KIND that is comes from the branch the address sits under."
    #: A node therefore denotes a document or an artifact, never both, and no new family is
    #: needed to say so.
    #:
    #: A resource entry reads as three lcl ids all the same — its own node address, its
    #: icon, and the file it stands for — because the node's address is one of them.
    #:
    #: SEPARATE FIELD rather than overloading `slot`, because a caller asking "what document
    #: does this node denote" must not be handed an artifact id that will not resolve in
    #: the document store. `ARTIFACT_BRANCH_LABEL` was declared 2026-08-23 and nothing read
    #: it until 2026-08-31 — `artifacts_viewer` says so itself: "until nodes denote
    #: artifacts there is nothing to group by".
    artifact: str = ""
    #: The SOURCE this node denotes, or ``""``. A child of the log's SOURCE branch
    #: (2026-09-08): a pin on a document held elsewhere — another sandbox's, or FND's
    #: archetype library — by title and content hash, never by holding it. Like
    #: `artifact`, a third reading of the ONE denotation, told apart by branch.
    source: str = ""
    #: The content hash a SOURCE row carries in its fourth tuple (`local_domain_source`,
    #: 4-4: lcl_id, title, glyph, mss_source_binary). Empty on every other row.
    hash: str = ""

    @property
    def denotes(self) -> bool:
        return bool(self.slot)

    @property
    def wears(self) -> bool:
        return bool(self.icon)

    @property
    def denotes_artifact(self) -> bool:
        return bool(self.artifact)

    @property
    def denotes_source(self) -> bool:
        return bool(self.source)


@dataclass(frozen=True)
class LocalDomainLog:
    """What a local domain document says, read once.

    ``entries`` is keyed on node and holds at most one row per node — see the module note.
    ``meta_root`` is ``""`` for a sandbox that has not adopted the log, and every method
    below then answers emptily rather than guessing, which is the honest shape: a tree with
    no document branch denotes no documents.
    """

    entries: dict[str, Entry]
    meta_root: str
    #: The meta root's document branch, found by LABEL. Falls back to the meta root itself
    #: on a tree that has not subdivided yet, so every reader here works unchanged across
    #: the migration and nothing has to ask which shape it is looking at.
    document_root: str = ""
    #: The meta root's icon branch, found by LABEL. ``""`` until a tree subdivides — and a
    #: log with no icon branch honestly has no icons rather than a default nobody wrote.
    icon_root: str = ""
    #: The meta root's ARTIFACT branch, found by LABEL. ``""`` on every tree that has not
    #: minted one — which was all 13 of them until 2026-08-31 — and a log without it
    #: honestly denotes no artifacts rather than borrowing the document branch.
    artifact_root: str = ""
    #: THE CANONICAL SHAPE (2026-09-08). ``root`` is the node labelled `local_domain`;
    #: ``meta_root`` is its child labelled `meta`. Every root is ``""`` on a tree that
    #: has not adopted the log, and every method below answers emptily for it — such a
    #: tree honestly has no branches rather than guessed ones.
    root: str = ""
    source_root: str = ""
    class_root: str = ""
    object_root: str = ""

    @property
    def canonical(self) -> bool:
        """Whether this tree carries the 2026-09-08 base structure (a `local_domain` root
        with `meta` beneath it) — which, since the live trees migrated, is whether it has
        a log at all. The WRITERS ask, and refuse a second root on a canonical tree."""
        return bool(self.root)

    @property
    def glyph_root(self) -> str:
        """The glyph branch — the same node ``icon_root`` names, under the operator's
        word for it. The field keeps its old name because thirty readers use it."""
        return self.icon_root

    def glyphs(self) -> dict[str, Entry]:
        return self.icons()

    def glyph_slot(self, title: str) -> str:
        """The slot of the glyph titled ``title`` (case-insensitive), or ``""``."""
        wanted = as_text(title).strip().lower()
        for slot, entry in self.icons().items():
            if entry.label.strip().lower() == wanted:
                return slot
        return ""

    def default_glyph(self) -> str:
        """The slot every ordinary node wears until somebody chooses: `circle`, or the
        first glyph the branch holds when there is no circle, or ``""`` when the sandbox
        holds no glyph at all — in which case there is nothing to default TO, and the
        writers keep the pre-migration `4-2` shape rather than write a dangling
        reference into every node at once."""
        return self.glyph_slot(DEFAULT_GLYPH) or next(iter(self.icons()), "")

    def sources(self) -> dict[str, Entry]:
        """``{source slot: its entry}`` — every pin this sandbox keeps, in address order."""
        if not self.source_root:
            return {}
        return {
            node: entry
            for node, entry in sorted(self.entries.items(), key=lambda kv: _order(kv[0]))
            if parent_of(node) == self.source_root
        }

    def is_source_node(self, node: str) -> bool:
        return bool(self.source_root) and parent_of(as_text(node)) == self.source_root

    def artifact_kinds(self) -> dict[str, Entry]:
        """``{kind node: entry}`` — the children of the artifact branch whose labels are
        the four kinds. Empty on a tree with no artifact branch."""
        if not self.artifact_root:
            return {}
        return {
            node: entry
            for node, entry in sorted(self.entries.items(), key=lambda kv: _order(kv[0]))
            if parent_of(node) == self.artifact_root
            and entry.label.strip().lower() in ARTIFACT_KINDS
        }

    def class_kinds(self) -> dict[str, Entry]:
        """``{kind node: entry}`` for `archetypes` / `datum_types` / `events`."""
        if not self.class_root:
            return {}
        return {
            node: entry
            for node, entry in sorted(self.entries.items(), key=lambda kv: _order(kv[0]))
            if parent_of(node) == self.class_root
            and entry.label.strip().lower() in CLASS_KINDS
        }

    @property
    def slot_root(self) -> str:
        """Where document slots hang. The document branch, or the meta root before it."""
        return self.document_root or self.meta_root

    @property
    def subdivided(self) -> bool:
        """Whether this tree carries the icon/document split."""
        return bool(self.icon_root and self.document_root)

    # -- what a node says -----------------------------------------------------
    def slot_of(self, node: str) -> str:
        entry = self.entries.get(as_text(node))
        return entry.slot if entry else ""

    def label_of(self, node: str) -> str:
        entry = self.entries.get(as_text(node))
        return entry.label if entry else ""

    # -- what a document says -------------------------------------------------
    def slots(self) -> dict[str, Entry]:
        """``{slot: its own entry}`` — every document slot, in address order.

        A slot IS a node: a child of the meta root whose label is the document's title. So
        "list the documents" and "list the children of that branch" are one question, which
        is why the retired documents gallery could be folded into the tree.
        """
        root = self.slot_root
        if not root:
            return {}
        return {
            node: entry
            for node, entry in sorted(self.entries.items(), key=lambda kv: _order(kv[0]))
            if parent_of(node) == root
        }

    def node_of_slot(self, slot: str) -> str:
        """Which node denotes ``slot``, or ``""`` when nothing does (it is unassigned)."""
        target = as_text(slot)
        for node, entry in self.entries.items():
            if entry.slot == target:
                return node
        return ""

    def unassigned(self) -> list[str]:
        """Slots no node points at. Visible on the tree by construction — they hang off the
        meta root — which is the whole reason a separate gallery stopped being needed.

        The RESERVED pair is excluded. The anchor and the log are permanently unattached by
        design, so counting them as unassigned would show every sandbox two documents
        "waiting for a home" forever — a number that never goes down teaches nobody
        anything.
        """
        pointed = {entry.slot for entry in self.entries.values() if entry.slot}
        reserved = self.reserved_slots()
        return [slot for slot in self.slots()
                if slot not in pointed and slot not in reserved]

    def artifacts(self) -> dict[str, Entry]:
        """``{node: its entry}`` for every child of the ARTIFACT branch, in address order.

        The artifact-branch twin of :meth:`slots`, and the same sentence holds: an artifact
        slot IS a node, so "list the artifacts" and "list the children of that branch" are
        one question. ``{}`` on a tree that has not minted the branch, which is honest —
        it denotes no artifacts — rather than falling back to the document branch and
        reporting documents as if they were files.
        """
        root = self.artifact_root
        if not root:
            return {}
        # The branch's children are the four KINDS and the artifacts hang beneath them;
        # a child of the branch that is not a kind (none, on a seeded tree) still reads
        # as an artifact rather than vanishing.
        kinds = set(self.artifact_kinds())
        return {
            node: entry
            for node, entry in sorted(self.entries.items(), key=lambda kv: _order(kv[0]))
            if (parent_of(node) == root and node not in kinds)
            or parent_of(node) in kinds
        }

    def node_of_artifact(self, artifact: str) -> str:
        """Which node denotes ``artifact``, or ``""`` when nothing does."""
        target = as_text(artifact)
        for node, entry in self.entries.items():
            if entry.artifact == target:
                return node
        return ""

    def children_of(self, node: str) -> dict[str, Entry]:
        """``{node: entry}`` for the direct children of ``node``, in address order.

        The tree walk every grouping surface needs, written once here rather than in each
        of them. A caller that re-derived it from `entries` would have to know `_order` and
        `parent_of`, which is how two surfaces come to disagree about what a tree is.
        """
        parent = as_text(node)
        if not parent:
            return {}
        return {
            child: entry
            for child, entry in sorted(self.entries.items(), key=lambda kv: _order(kv[0]))
            if parent_of(child) == parent
        }

    def attachable(self) -> dict[str, Entry]:
        """The slots a node may be pointed AT — every slot but the reserved pair.

        A node denoting the anchor would be a node claiming to say what the sandbox's
        ground truth is, and a node denoting the log would be a node inside the thing that
        records it. Neither is a sentence the tree can mean.
        """
        reserved = self.reserved_slots()
        return {slot: entry for slot, entry in self.slots().items()
                if slot not in reserved}

    def next_slot(self) -> str:
        """The next contiguous child of the meta root.

        Contiguous, and the SAMRAS validator means it literally: "child ordinals must be
        contiguous". That is why the RESERVED PAIR is two real rows rather than a rule
        somebody remembers — a log that merely promised to keep ``1-1`` and ``1-2`` free
        and started its documents at ``1-3`` would not compile at all.
        """
        return self._next_child(self.slot_root)

    def next_icon_slot(self) -> str:
        """The next contiguous child of the ICON branch, or ``""`` before one exists.

        A tree that has not subdivided cannot take an icon: there is nowhere for it to hang
        that a reader could tell apart from a document, and inventing the branch here would
        make "which root is reserved" a side effect of pressing a button.
        """
        return self._next_child(self.icon_root)

    def _next_child(self, root: str) -> str:
        if not root:
            return ""
        highest = 0
        for node in self.entries:
            if parent_of(node) == root:
                tail = node.rsplit("-", 1)[-1]
                if tail.isdigit():
                    highest = max(highest, int(tail))
        return f"{root}-{highest + 1}"

    def icons(self) -> dict[str, Entry]:
        """``{icon slot: its own entry}`` — every glyph this sandbox holds, in order."""
        if not self.icon_root:
            return {}
        return {
            node: entry
            for node, entry in sorted(self.entries.items(), key=lambda kv: _order(kv[0]))
            if parent_of(node) == self.icon_root
        }

    def icon_of(self, node: str) -> str:
        entry = self.entries.get(as_text(node))
        return entry.icon if entry else ""

    # -- what a node IS -------------------------------------------------------
    def is_slot_node(self, node: str) -> bool:
        """Whether ``node`` is a document slot — a child of the DOCUMENT branch.

        Asked here rather than spelled ``parent_of(node) == log.meta_root`` at each
        reader, which is what nine of them did. On a subdivided tree that comparison is
        false for every slot, and the readers went quiet rather than wrong: the tree still
        drew, the slots simply stopped being slots and their Open links vanished.
        """
        root = self.slot_root
        return bool(root) and parent_of(as_text(node)) == root

    def is_icon_node(self, node: str) -> bool:
        """Whether ``node`` is a glyph — a child of the ICON branch."""
        return bool(self.icon_root) and parent_of(as_text(node)) == self.icon_root

    def is_document_node(self, node: str) -> bool:
        """Whether ``node`` IS a document — on either branch.

        A glyph is a datum document exactly as a text note is; it is filed on the icon
        branch rather than the document branch because that is what tells an icon
        reference from a pointer. Every rule that follows from "this node IS a document"
        — it takes no children, it is not offered as a parent, its title is the
        document's, it opens — is the same rule for both, and asking two questions where
        one fact exists is how the second one goes stale.
        """
        return (self.is_slot_node(node) or self.is_icon_node(node)
                or self.is_source_node(node) or as_text(node) in self.artifacts())

    def branch_roots(self) -> frozenset[str]:
        """The root, the meta root, every branch and every fixed KIND: the nodes that are
        STRUCTURE, not subject.

        None of them may be moved, deleted, or given a document. They are where every
        document in the sandbox is filed, and filing them under a topic would put them all
        inside one. The `objects` branch is structural; its CHILDREN are the operator's.
        """
        fixed = (self.root, self.meta_root, self.icon_root, self.document_root,
                 self.source_root, self.artifact_root, self.class_root, self.object_root)
        return frozenset(node for node in fixed if node) | frozenset(
            self.artifact_kinds()) | frozenset(self.class_kinds())

    def is_structural(self, node: str) -> bool:
        return as_text(node) in self.branch_roots()

    # -- the reserved pair ----------------------------------------------------
    def reserved_slots(self) -> dict[str, int]:
        """``{slot address: ordinal}`` for the two reserved slots this log would use.

        Computed from the meta root rather than hardcoded, for the reason the meta root is
        found by label at all: ``insert_node`` can re-key the branch, and a reserved slot
        that stopped being reserved when its parent moved is worse than no reservation.
        """
        root = self.slot_root
        if not root:
            return {}
        return {
            f"{root}-{ordinal}": ordinal
            for ordinal in (ANCHOR_SLOT_ORDINAL, LOG_SLOT_ORDINAL)
        }

    def is_reserved(self, slot: str) -> bool:
        """Whether ``slot`` IS the reserved anchor or log slot — address AND title.

        The address alone is not enough, and the migration rehearsal is what proved it:
        BPW's ``oveure`` already had a ``1-1``, titled "Driveway cleaning", from the day
        the log was minted with no reservation. An address-only check read that branch as
        "already reserved" and would have left a customer's driveway note occupying the
        anchor's id.

        The title is a safe second half BECAUSE a reserved slot cannot be retitled — the
        one thing that could make this drift is the one thing the verbs refuse.
        """
        token = as_text(slot)
        ordinal = self.reserved_slots().get(token)
        if ordinal is None:
            return False
        entry = self.entries.get(token)
        return entry is not None and entry.label in (
            RESERVED_SLOT_TITLES[ordinal], LEGACY_RESERVED_SLOT_TITLES[ordinal])

    def reserved_pair_present(self) -> bool:
        """Whether both reserved slots are actual ROWS, carrying their reserved titles.

        Not a formality. A slot is a node, node ordinals must be contiguous from 1, and the
        magnitude is recompiled from the node set — so a branch that has not been seeded
        with the pair cannot have a document at ``1-3`` at all. A tree missing it is an
        unmigrated tree, and every verb that would mint a slot says so rather than filling
        the gap as a side effect.
        """
        return bool(self.slot_root) and all(
            self.is_reserved(slot) for slot in self.reserved_slots())

    def document_name_of_slot(self, slot: str, *, anchor_name: str = "") -> str:
        """The datum document a slot NAMES — the reserved filename, or the slot itself.

        ``anchor_name`` is passed in rather than assumed because a sandbox's anchor is
        called ``anchor`` or ``anthology`` depending on when it was made, and both are
        reserved. An empty one means the caller does not know, so the anchor slot resolves
        to nothing rather than to a guess.
        """
        token = as_text(slot)
        ordinal = self.reserved_slots().get(token)
        if ordinal == ANCHOR_SLOT_ORDINAL:
            return as_text(anchor_name)
        if ordinal == LOG_SLOT_ORDINAL:
            from micyte.core.instance_baseline import LCL_DOCUMENT

            return LCL_DOCUMENT
        return token


def _order(node: str) -> tuple[int, ...]:
    return tuple(int(part) for part in as_text(node).split("-") if part.isdigit())


def trailing_refs(head: Any) -> tuple[str, ...]:
    """Every node reference a definition head carries AFTER its node and title.

    The third tuple and, since 2026-08-20, the fourth. Read positionally and stopped at
    the first pair that is not a node reference, because a head may carry further pairs a
    later field adds and "the last node reference" would silently adopt one of them.
    """
    if not isinstance(head, list):
        return ()
    out: list[str] = []
    index = 5
    while index + 1 < len(head):
        if not is_node_ref_marker(head[index]) or not is_node_addr_reference(head[index + 1]):
            break
        out.append(as_text(head[index + 1]))
        index += 2
    return tuple(out)


def pointer_of(head: Any) -> str:
    """The FIRST trailing reference, unclassified.

    Kept for readers that predate the icon branch and only ever see a document pointer. On
    a subdivided tree this is the ICON, so a caller that means "the document" must ask the
    log — which is why :func:`read_log` classifies rather than leaving this to guess.
    """
    refs = trailing_refs(head)
    return refs[0] if refs else ""


def read_log(document: Any | None) -> LocalDomainLog:
    """Read one local domain document into a :class:`LocalDomainLog`.

    ``None`` and a document with no definition rows both give an empty log with no meta
    root, so every caller has one shape to handle.
    """
    entries: dict[str, Entry] = {}
    refs: dict[str, tuple[str, ...]] = {}
    heads: dict[str, list[Any]] = {}
    for row in getattr(document, "rows", ()) or ():
        head = _head(getattr(row, "raw", None))
        if head is None or not _is_definition_head(head):
            continue
        node = as_text(head[2])
        if not node or node in entries:
            # First row wins, which is what `NameIndex` already does. A second definition
            # row for one node is a defect this module reports by ignoring rather than by
            # letting the last writer decide what a node is called.
            continue
        heads[node] = head
        raw = getattr(row, "raw", None)
        label = ""
        if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], list) and raw[1]:
            label = as_text(raw[1][0])
        if not label and len(head) >= 5:
            label = decode_label(head[4])
        entries[node] = Entry(
            node=node, label=label, slot="", address=as_text(
                getattr(row, "datum_address", "")),
        )
        refs[node] = trailing_refs(head)

    ordered = sorted(entries.items(), key=lambda kv: _order(kv[0]))

    def child_labelled(parent: str, label: str) -> str:
        wanted = label.lower()
        for node, entry in ordered:
            if parent_of(node) == parent and entry.label.strip().lower() == wanted:
                return node
        return ""

    # ONE SHAPE, one reader (since the 25 live trees migrated, 2026-09-08). The root is
    # the top-level node labelled `local_domain` and the meta is its child labelled
    # `meta`; every branch beneath is found by label. A tree with no such root is a
    # sandbox that has not adopted the log — meta ``""``, every method answering emptily
    # — which is the honest shape and the one every reader already handles.
    #
    # The 2026-08-20 shape (a top-level `documents` that WAS the meta) is read by exactly
    # one thing now: `migrate_local_domain_base._read_legacy_log`, which is the one
    # program that needs the old shape in order to leave it.
    root = ""
    for node, entry in ordered:
        if not parent_of(node) and entry.label.strip().lower() == ROOT_LABEL:
            root = node
            break
    meta = child_labelled(root, META_LABEL) if root else ""
    class_root = child_labelled(root, CLASS_BRANCH_LABEL) if root else ""
    object_root = child_labelled(root, OBJECT_BRANCH_LABEL) if root else ""

    # The branches, by LABEL, exactly as the meta root itself was found. `glyphs` is the
    # operator's word and `icons` is what every live tree carries; they are one branch.
    icon_root = (child_labelled(meta, GLYPH_BRANCH_LABEL)
                 or child_labelled(meta, ICON_BRANCH_LABEL)) if meta else ""
    document_root = child_labelled(meta, DOCUMENT_BRANCH_LABEL) if meta else ""
    source_root = child_labelled(meta, SOURCE_BRANCH_LABEL) if meta else ""
    artifact_root = child_labelled(meta, ARTIFACT_BRANCH_LABEL) if meta else ""
    artifact_kinds = {
        node for node, entry in ordered
        if artifact_root and parent_of(node) == artifact_root
        and entry.label.strip().lower() in ARTIFACT_KINDS
    }

    # Classify each trailing reference by the branch it sits under. On an unsubdivided
    # tree there is one branch and every reference is a document slot, which is what these
    # rows have always meant.
    for node, found in refs.items():
        icon = slot = artifact = source = ""
        for ref in found:
            parent = parent_of(ref)
            if icon_root and parent == icon_root:
                icon = icon or ref
            elif document_root and parent == document_root:
                slot = slot or ref
            elif artifact_root and (parent == artifact_root or parent in artifact_kinds):
                artifact = artifact or ref
            elif source_root and parent == source_root:
                source = source or ref
            elif not icon_root and not document_root:
                # The UNSUBDIVIDED tree, where there is one branch and every reference has
                # always meant a document slot. `artifact_root` is deliberately absent from
                # this condition: a tree with no branches at all cannot have minted an
                # artifact branch, so reaching here with one would be a contradiction, and
                # widening the fallback would file artifacts as documents on exactly the
                # trees least able to tell the difference.
                slot = slot or ref
        if icon or slot or artifact or source:
            entries[node] = replace(
                entries[node], icon=icon, slot=slot, artifact=artifact, source=source)

    # A SOURCE row's fourth tuple is its content hash — a literal, not a node reference,
    # so `trailing_refs` stopped before it. Read it off the head by position: the pair
    # after the last node reference.
    for node, entry in list(entries.items()):
        if not (source_root and parent_of(node) == source_root):
            continue
        head = heads.get(node) or []
        refs_seen = len(refs.get(node, ()))
        index = 5 + 2 * refs_seen
        if index + 1 < len(head):
            entries[node] = replace(entry, hash=as_text(head[index + 1]))

    return LocalDomainLog(entries=entries, meta_root=meta,
                          document_root=document_root, icon_root=icon_root,
                          artifact_root=artifact_root, root=root,
                          source_root=source_root, class_root=class_root,
                          object_root=object_root)


def filed_documents(
    log: LocalDomainLog, names: Any, *, anchor_name: str = "",
) -> tuple[dict[str, str], tuple[str, ...]]:
    """``({document name: slot}, unfiled names)`` for one sandbox's documents.

    A document is FILED when a slot names it. Everything else is UNFILED — and unfiled is
    shown, never hidden: a sandbox that holds documents its log does not know about has to
    say so, which is the same rule the sources section follows and the same reason the
    unassigned slot is drawn on the tree.

    Unfiled is the honest state for most of the corpus and will stay that way. Registrar's
    482 documents are NAMED for the msn nodes they profile and the archetype library's 77
    are named for the archetype they blank-instance; in both the name IS the denotation, so
    filing them would trade a meaning for an ordinal. The log records what it knows and
    makes no claim about the rest.
    """
    held = tuple(as_text(name) for name in (names or ()) if as_text(name))
    by_name: dict[str, str] = {}
    for slot in log.slots():
        document = log.document_name_of_slot(slot, anchor_name=anchor_name)
        if document:
            by_name[document] = slot
    filed = {name: by_name[name] for name in held if name in by_name}
    unfiled = tuple(name for name in held if name not in by_name)
    return filed, unfiled


__all__ = [
    "ANCHOR_SLOT_ORDINAL",
    "ARTIFACT_BRANCH_LABEL",
    "ARTIFACT_BRANCH_ORDINAL",
    "ARTIFACT_KINDS",
    "CANONICAL_GLYPHS",
    "CLASS_BRANCH_LABEL",
    "CLASS_BRANCH_ORDINAL",
    "CLASS_KINDS",
    "DEFAULT_GLYPH",
    "DEFINITION_FAMILIES",
    "DEFINITION_PREFIXES",
    "DOCUMENT_BRANCH_LABEL",
    "DOCUMENT_BRANCH_ORDINAL",
    "DOCUMENT_KINDS",
    "DOCUMENT_ROOT_LABEL",
    "FIRST_FREE_SLOT_ORDINAL",
    "FULL_FAMILY",
    "GLYPH_BRANCH_LABEL",
    "GLYPH_BRANCH_ORDINAL",
    "ICON_BRANCH_LABEL",
    "ICON_BRANCH_ORDINAL",
    "LEGACY_RESERVED_SLOT_TITLES",
    "LOG_SLOT_ORDINAL",
    "META_LABEL",
    "META_ORDINAL",
    "NODE_FAMILY",
    "OBJECT_BRANCH_LABEL",
    "OBJECT_BRANCH_ORDINAL",
    "OPTION_SEP",
    "REF_FAMILY",
    "RESERVED_SLOT_TITLES",
    "ROOT_LABEL",
    "SOURCE_BRANCH_LABEL",
    "SOURCE_BRANCH_ORDINAL",
    "STRUCTURAL_GLYPHS",
    "TITLE_CHARS",
    "Entry",
    "LocalDomainLog",
    "checked_title",
    "domain_markers",
    "filed_documents",
    "is_definition_address",
    "is_definition_row",
    "is_node_address",
    "option_slug",
    "parse_slot_title",
    "pointer_of",
    "read_log",
    "slot_title",
    "trailing_refs",
]
