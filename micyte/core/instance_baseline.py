"""What every instance's core sandbox holds, declared ONCE.

The operator's direction (2026-08-14): "most instances should generally be using a single
system sandbox", whose default datum documents "include but are not limited to" an anchor,
``msn_profile``, ``contacts``, ``lcl_domain`` and ``calendar``.

"Include but are not limited to" is the load-bearing half. This is a FLOOR that a trade
extends, never a ceiling: a farm adds ``farm_profile``/``object_profiles``/``sources``, a
handyman instance adds ``job_log``. Those stay where they already are — declared by the
tools that need them (``micyte/tools/_requirements.py``) — because the question "what does
this trade need" is not the question this module answers.

## Why this exists

The base set had FIVE implementations and no declaration:

  scripts/bootstrap_handyman_sandbox.py   anchor, lcl, contacts, job_log
  fnd_app/scripts/bootstrap_farm_sandbox.py   lcl, anchor, farm_profile
  fnd_app/scripts/bootstrap_channel_sandbox.py   anchor, lcl, channel_profile, sources
  package_install_runtime.install_package     whatever the tools require
  fnd_app/scripts/onboard_wolf_farm.py        a composition of the above

Five lists that must agree about what an instance IS, and they already did not: only
the client instance has ``contacts``, no instance has a ``calendar``, and none has a profile
of itself. A base set nobody declares is a base set each caller re-invents slightly
differently, and the quietest copy is the one that drifts.

## The anchor is a PRECONDITION, not a baseline document

It is absent from ``BASELINE_DOCUMENTS`` on purpose, for the reason ``quiar`` gives
about its own requirements: "a sandbox without one has no namespace at all and is not a
sandbox this or any tool can be installed into". An anchor is COPIED from an existing one
(``bootstrap_handyman_sandbox`` takes the registrar's verbatim) and never invented, because
a made-up anchor "produces a document that looks canonical and means nothing". So it is
checked with :func:`is_anchored` and provisioned by nothing here.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops import field_registry as _fr
from micyte.core.document_naming import (
    ANCHOR_DOCUMENT_NAMES,
    LEGACY_LOCAL_DOMAIN_DOCUMENT,
    LOCAL_DOMAIN_DOCUMENT,
    LOCAL_DOMAIN_DOCUMENT_NAMES,
)
from micyte.ports.tool_package import DocumentRequirement

#: The canonical name of the local-domain document, and every spelling it may be stored
#: under. Both OWNED by :mod:`micyte.core.document_naming`, beside the anchor's reserved
#: pair: a reserved document name is a naming fact, and two modules declaring it is how one
#: of them starts accepting a name the other refuses.
LCL_DOCUMENT = LOCAL_DOMAIN_DOCUMENT
LEGACY_LCL_DOCUMENT = LEGACY_LOCAL_DOMAIN_DOCUMENT
LOCAL_DOMAIN_NAMES: tuple[str, ...] = LOCAL_DOMAIN_DOCUMENT_NAMES

#: What an instance maintains of ITSELF, named once so the shape test and the floor
#: cannot disagree about it. `micyte.core.instances` asks whether a sandbox holds this to
#: tell an instance's CORE sandbox from every other anchored one, and it must be asking
#: about the same document this floor provisions.
MSN_PROFILE_DOCUMENT = "msn_profile"

#: The floor. Every instance's core sandbox holds these, whatever trade it is.
BASELINE_DOCUMENTS: tuple[DocumentRequirement, ...] = (
    DocumentRequirement(
        name=MSN_PROFILE_DOCUMENT,
        archetype="system_profile",
        why="what this instance maintains of ITSELF — not the registrar's entry about it, "
            "and not its row in a channel roster",
    ),
    DocumentRequirement(
        name="contacts",
        archetype="natural_entity_profile",
        why="the people this instance deals with; a person and a contact are one archetype",
    ),  # its fields: CONTACT_FIELDS below, checked by `provisionable`.
    DocumentRequirement(
        name=LCL_DOCUMENT,
        archetype="local_domain_log",
        why="the local domain — the id space this sandbox mints for itself, and the log "
            "of which document each of its ids names",
    ),
    DocumentRequirement(
        name="calendar",
        archetype="event",
        why="this instance's own dated things, and the calendar tool's default target",
    ),
)


def provision_name(requirement: DocumentRequirement) -> str:
    """The name a NEW instance's copy of this baseline document is created under.

    The canonical one, always, from 2026-08-20. It returned the LEGACY name for six days —
    correctly, while nothing could read the canonical one — and kept returning it after
    every reader learned both, which is how a transitional shim becomes the convention it
    was written to retire. Reading is what has to accept two names during a rename; writing
    a THIRD document under the old one only makes the migration longer.
    """
    return requirement.name


def is_anchored(document_names: frozenset[str] | set[str]) -> bool:
    """Whether the sandbox has an anchor — under either reserved name."""
    return bool(set(document_names) & ANCHOR_DOCUMENT_NAMES)


def is_local_domain(name: str) -> bool:
    """Whether ``name`` is the local-domain document, canonical or legacy spelling."""
    return str(name or "").strip() in LOCAL_DOMAIN_NAMES


#: Where the local domain's root lives, and what its children are minted under.
#:
#: The rule this encodes is "a parent is a different thing from its first child" — the
#: bootstrap_handyman_sandbox lesson, caught by rendering the live instance: seeding the
#: root at the address its first child will take is how one node ends up carrying two
#: labels. The root is at ``1``, so the first minted type is ``1-1``.
#:
#: It was ``1-1`` until 2026-08-18, one level too deep, and the corpus disagreed with it
#: the whole time. Every populated tree defines ``1`` as a real row and hangs its branches
#: off it — ``registrar`` (``1 mycelium_classification`` → ``1-1 entity_class``, ``1-2
#: ag_profile``, …), ``agnet``, both farm ``system`` trees, and ``taxonomy/txa``, which
#: also proves a tree may have SEVERAL roots (``1 cytota``, ``2``, ``3``, ``4``). A
#: sandbox seeded at ``1-1`` had no ``1`` row at all, and since ``define_type`` refuses an
#: unclassified parent, it could never grow a second top-level branch: the shape the
#: corpus's own largest document is written in was unreachable from a fresh install.
#:
#: The original comment's reasoning is untouched by the correction — it argued against
#: seeding at ``1-1-1``, which root=``1`` / first-child=``1-1`` satisfies exactly.
DOMAIN_ROOT_NODE = "1"
DOMAIN_ROOT_LABEL = "domain"

#: Where a LOG-carrying sandbox puts things. The reserved branch is root ``1`` and the
#: operator's own tree starts at ``2`` — the operator's own numbering (2026-08-19), and
#: the reason a document slot is ``1-7``. Every reader still finds the branch by its LABEL
#: (:data:`micyte.core.datum_ops.local_domain.DOCUMENT_ROOT_LABEL`), because ``insert_node``
#: can re-key any address; this is only where the seed PUTS it.
DOCUMENT_ROOT_NODE = "1"
SECOND_ROOT_NODE = "2"


def seeded_local_domain_rows(
    namespace: str, *, label: str = DOMAIN_ROOT_LABEL,
    glyphs: tuple[str, ...] | None = None,
    sources: tuple[tuple[str, str], ...] = (),
    classes: dict[str, tuple[str, ...]] | None = None,
    convention: Any = None,
) -> tuple:
    """THE BASE STRUCTURE every local domain starts with, every row wearing a glyph.

    ``convention`` (2026-09-11, TASK-2026-09-11-001 P4) is the
    :class:`micyte.core.datum_ops.local_domain_convention.Convention` the structure is
    seeded FROM — the branch labels, the glyph each structural role wears, the artifact
    and class kinds and the class vocabularies. Absent, the code's constants are used,
    which is the bootstrap for a store that holds no library yet; the provisioner passes
    the one it read off the archetype library's own tree, so an edit made there is what
    every new sandbox is made of.

    The operator's depiction (2026-09-08), seeded whole rather than grown: a sandbox
    has its `local_domain` root, its `meta` with `glyphs` / `documents` / `sources` /
    `artifacts`, its `classes` and its `objects` before it has anything else, because a
    branch that only some sandboxes have is not a namespace, it is a feature.

    ``glyphs`` are the titles the glyph branch's slots carry, in slot order — the
    canonical eleven by default; the caller that has COPIED the drawings in passes the
    titles it actually wrote. ``sources`` are ``(title, hash)`` pairs for the sources
    branch — the two FND authority documents by default, resolved by the provisioner
    rather than typed here, so an empty tuple seeds the branch and nothing under it.
    ``classes`` maps each of `archetypes` / `datum_types` / `events` to the labels its
    children carry; absent, the three kinds are seeded empty.

    EVERY ROW IS `4-3` OR `4-4`. A structural node wears the glyph its role fixes
    (`STRUCTURAL_GLYPHS`); a glyph slot wears ITSELF; a source row is `4-4`, glyph then
    hash, when the namespace can express the hash cell (`mss_source_binary`) and `4-3`
    with the hash carried nowhere when it cannot — reported by the reader as a source
    with no hash rather than refused, because the glyph library's own namespace is one
    such and it is a real sandbox.

    ``label`` is accepted for the callers that pass one and no longer titles anything:
    the operator's tree is the `objects` branch's CHILDREN, and `objects` is what that
    branch is called everywhere.

    The rows are read back through :func:`node_kind_index` before they ship, as the
    seed always has been, and a namespace in which no marker reads as a type is REFUSED
    by name (`system`, which has no lcl vocabulary at all).
    """
    from micyte.core.datum_documents import AuthoritativeDatumDocumentRow
    from micyte.core.datum_ops import local_domain as ld
    from micyte.core.datum_ops.datum_resolve import NODE_KIND_TYPE, node_kind_index
    from micyte.core.datum_ops.labels import encode_label_bits

    ns = str(namespace or "").strip()
    node_marker, title_marker = ld.domain_markers(ns)  # raises ValueError by name
    try:
        hash_marker = _fr.marker(ns, "mss_source_binary")
    except KeyError:
        hash_marker = ""
    from micyte.core.datum_ops import local_domain_convention as ldc

    spec = convention if convention is not None else ldc.from_constants()
    glyph_titles = tuple(glyphs) if glyphs is not None else tuple(spec.glyphs)
    # The derived three take what the caller derived (`class_seed`); a kind the convention
    # SEEDS (project roles, fact kinds) takes the convention's vocabulary.
    kinds = {kind: (tuple((classes or {}).get(kind, ())) if kind in ld.CLASS_KINDS
                    else tuple(spec.vocabularies.get(kind, ())))
             for kind in spec.class_kinds}

    root = DOMAIN_ROOT_NODE
    meta = f"{root}-{ld.META_ORDINAL}"
    glyph_branch = f"{meta}-{ld.GLYPH_BRANCH_ORDINAL}"
    doc_branch = f"{meta}-{ld.DOCUMENT_BRANCH_ORDINAL}"
    source_branch = f"{meta}-{ld.SOURCE_BRANCH_ORDINAL}"
    artifact_branch = f"{meta}-{ld.ARTIFACT_BRANCH_ORDINAL}"
    class_branch = f"{root}-{ld.CLASS_BRANCH_ORDINAL}"
    object_branch = f"{root}-{ld.OBJECT_BRANCH_ORDINAL}"

    glyph_slot = {title: f"{glyph_branch}-{index}"
                  for index, title in enumerate(glyph_titles, start=1)}

    def wear(role: str) -> str:
        """The slot a structural node wears, falling back to the default glyph and then
        to the first glyph seeded — a structural node never goes bare."""
        title = spec.structural_glyphs.get(role) or spec.default_glyph
        return (glyph_slot.get(title) or glyph_slot.get(spec.default_glyph)
                or next(iter(glyph_slot.values()), ""))

    # (node, label, glyph slot it wears, trailing literal or "") — labels and glyphs are
    # the CONVENTION's; the ordinals are the seed's.
    heads: list[tuple[str, str, str, tuple[str, str] | None]] = [
        (root, spec.label(ld.ROOT_LABEL), wear(ld.ROOT_LABEL), None),
        (meta, spec.label(ld.META_LABEL), wear(ld.META_LABEL), None),
        (glyph_branch, spec.label("glyphs"), wear("glyphs"), None),
    ]
    for title in glyph_titles:
        heads.append((glyph_slot[title], title, glyph_slot[title], None))  # wears itself
    heads += [
        (doc_branch, spec.label("documents"), wear("documents"), None),
        (f"{doc_branch}-{ld.ANCHOR_SLOT_ORDINAL}", spec.label("anchor"), wear("anchor"), None),
        (f"{doc_branch}-{ld.LOG_SLOT_ORDINAL}", spec.label("local_domain_slot"),
         wear("local_domain_slot"), None),
        (source_branch, spec.label("sources"), wear("sources"), None),
    ]
    for index, (title, digest) in enumerate(sources, start=1):
        literal = (hash_marker, str(digest)) if hash_marker and digest else None
        heads.append((f"{source_branch}-{index}", str(title), wear("sources"), literal))
    heads.append((artifact_branch, spec.label("artifacts"), wear("artifacts"), None))
    for index, kind in enumerate(spec.artifact_kinds, start=1):
        heads.append((f"{artifact_branch}-{index}", spec.label(kind), wear(kind), None))
    heads.append((class_branch, spec.label(ld.CLASS_BRANCH_LABEL), wear(ld.CLASS_BRANCH_LABEL), None))
    for index, kind in enumerate(spec.class_kinds, start=1):
        kind_node = f"{class_branch}-{index}"
        heads.append((kind_node, spec.label(kind), wear(kind), None))
        for child_index, child in enumerate(kinds.get(kind, ()), start=1):
            heads.append((f"{kind_node}-{child_index}", str(child), wear(kind), None))
    heads.append((object_branch, spec.label(ld.OBJECT_BRANCH_LABEL), wear(ld.OBJECT_BRANCH_LABEL), None))

    # THE ADDRESS IS THE ARITY: a glyph-wearing row is `4-3`, one that also carries a
    # literal is `4-4`. Each family numbers its own iterations.
    counters = {ld.REF_FAMILY: 0, ld.FULL_FAMILY: 0}
    rows = []
    for node, text, glyph, literal in heads:
        family = ld.FULL_FAMILY if literal else ld.REF_FAMILY
        counters[family] += 1
        address = f"{family}-{counters[family]}"
        head = [address, node_marker, node, title_marker, encode_label_bits(text)]
        if glyph:
            head += [node_marker, glyph]
        if literal:
            head += [literal[0], literal[1]]
        rows.append(AuthoritativeDatumDocumentRow(datum_address=address, raw=[head, [text]]))
    rows = tuple(rows)

    # Read the seed back through the same index the editor reads. A marker that is
    # defined but reads as the wrong KIND (or as nothing) is skipped, not shipped.
    from micyte.core.datum_documents import AuthoritativeDatumDocument

    probe = AuthoritativeDatumDocument(
        document_id=f"lv.0.probe.{LCL_DOCUMENT}.{'0' * 64}",
        source_kind="sandbox_source", document_name=f"{LCL_DOCUMENT}.json",
        relative_path=f"probe/{LCL_DOCUMENT}.json", canonical_name=LCL_DOCUMENT,
        tool_id="probe", is_anchor=False, rows=rows, document_metadata={},
    )
    kinds_read = node_kind_index(probe)
    unreadable = [node for node, *_ in heads if kinds_read.get(node) != NODE_KIND_TYPE]
    if unreadable:
        raise ValueError(
            f"the {ns or '?'} namespace seeded {len(unreadable)} node(s) the editor "
            f"cannot read as types ({', '.join(unreadable[:4])}); refusing to ship a "
            "local domain its own editor cannot classify")
    return rows


def seeded_node_set(lcl_rows: Any) -> set[str]:
    """The node addresses a seeded (or any) local domain's rows DEFINE.

    The same shape scan every reader uses (``refs._is_definition_head``): a row whose
    first pair is a node-ref marker naming a node and whose second pair is a title.
    Family-agnostic on purpose — ``4-2``, ``4-3`` and ``4-4`` rows all define a node, and
    a scan that keyed on the family would compute a node set missing every node that
    wears a glyph, which is the set the magnitude is then compiled from.
    """
    from micyte.core.datum_ops.refs import _head, _is_definition_head

    out: set[str] = set()
    for row in lcl_rows or ():
        head = _head(getattr(row, "raw", None))
        if head is not None and _is_definition_head(head):
            out.add(str(head[2]))
    return out


def seeded_anchor_rows(anchor: Any, lcl_rows: Any) -> list[Any]:
    """The anchor's rows, with its lcl-SAMRAS magnitude denoting EXACTLY ``lcl_rows``.

    The second half of the seed, and the half that was missing. ``seeded_local_domain_rows``
    writes a tree's six structural rows; the anchor that tree is provisioned beside is a
    COPY of some other sandbox's anchor, and a copy carries the source's magnitude. Every
    lcl VERB recompiles the anchor after it writes (``_recompiled_anchor``), so the copied
    magnitude survived only as long as nobody edited the tree — which, for a freshly
    provisioned sandbox, is exactly the state the operator first opens it in.

    Measured 2026-09-08: ``archetype`` denoted 53 and defined 6, ``brevat`` 70/6,
    ``quiar`` 59/6, ``taxonomy`` 6,418/6 — and the domain surface drew every foreign node
    as ``(undefined)``. This makes the seed own both documents it changes.

    Raises ``InvalidSamrasStructure`` when the anchor has no lcl-SAMRAS row. The installer
    already refuses to seed a local domain beside such an anchor for the same reason
    ("a domain seeded past that would take its first edit to discover it is read-only"),
    so this raising is the same rule stated once more where it is enforced.
    """
    from micyte.core.datum_ops.samras_deps import recompiled_anchor_rows

    return recompiled_anchor_rows(anchor, seeded_node_set(lcl_rows), name="lcl")


def satisfies(requirement: DocumentRequirement, document_names: frozenset[str] | set[str]) -> bool:
    """Whether ``document_names`` already holds this baseline document, old name or new."""
    held = set(document_names)
    if requirement.name in held:
        return True
    if requirement.name == LCL_DOCUMENT:
        return bool(held & set(LOCAL_DOMAIN_NAMES))
    return False


def missing_baseline(
    document_names: frozenset[str] | set[str],
) -> tuple[DocumentRequirement, ...]:
    """The baseline documents this sandbox does NOT hold, in declaration order.

    Reports, never provisions. Whether a gap is filled — and whether filling it is safe —
    is the caller's decision: a bootstrap creates them, an audit prints them, and the
    migration in Phase 4 is what closes them on the instances that already exist.
    """
    return tuple(
        requirement
        for requirement in BASELINE_DOCUMENTS
        if not satisfies(requirement, document_names)
    )


#: Why a baseline requirement cannot be provisioned into a given namespace, when it
#: cannot. Keyed by the reason, not by the requirement: the next namespace-shaped refusal
#: should reuse the vocabulary rather than invent a second word for it.
REFUSED_BY_NAMESPACE = "refused_by_namespace"

#: The fields a contact row is made of, stated HERE because this is where the baseline
#: requirement for `contacts` lives, and imported by `tools/_requirements` rather than
#: restated there. One statement: the provisioner's refusal and the tool's refusal must
#: not be able to disagree about which fields a contact needs.
#:
#: `nominal` belongs because it RESOLVES in the registrar namespace at the borrowed
#: 3-1-31 — which is why the check below is `writable_fields` (defined AND borrowed) and
#: not `fields`. Checking only what an anchor defines would refuse a contact on the one
#: namespace where the whole thing works.
CONTACT_FIELDS: tuple[str, ...] = (
    "msn_id", "ruiqi_id", "email", "sosvid", "nominal", "utc", "website",
)

#: Baseline document -> the fields its rows need the anchor to express. A document
#: requirement asks whether the instance holds the right FILE; this asks whether the
#: anchor can say anything in it.
_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {"contacts": CONTACT_FIELDS}


def provisionable(
    requirement: DocumentRequirement, *, namespace: str,
) -> tuple[bool, str]:
    """Whether this baseline document can be CREATED in ``namespace``, and if not, why.

    A second question from :func:`missing_baseline`, which only answers "is it held".
    Absent and unprovisionable are different states, and conflating them is what makes a
    provisioner either crash or seed a row nothing can read.

    The case that forced this apart, measured on the live store 2026-08-24: FND's own
    ``system`` sandbox is the one instance of four whose baseline ``missing_baseline``
    reports as incomplete, and the missing document is ``lcl_domain`` — which
    :func:`seeded_local_domain_rows` REFUSES for the ``system`` namespace, by design and
    with a good reason ("no lcl-node vocabulary at all"). ``system`` is the only one of the
    six namespaces with neither ``txa_id`` nor ``lcl_id``. So the gap is not a gap: it is a
    fact about the namespace, and a report that calls it missing invites somebody to fill
    it.

    Decided by ATTEMPTING the seed rather than by re-deriving the condition, so this and
    :func:`seeded_local_domain_rows` cannot come to different answers. A predicate that
    restates its subject's rule is a second copy of that rule.
    """
    if requirement.name == LCL_DOCUMENT:
        try:
            seeded_local_domain_rows(str(namespace or ""))
        except ValueError as exc:
            return False, str(exc)
        return True, ""

    # The SECOND way a baseline document can be unprovisionable: the namespace has no
    # way to say what its rows are made of. TASK-2026-08-14-005 measured this — the
    # 2026-08-14 backfill gave every instance a `contacts` document and did NOT give
    # their anchors the fields a contact needs, so two instances hold a document whose
    # own tool refuses to render it. `satisfies` reports it as held, because holding the
    # FILE is all it ever asked, and that is why this shipped looking complete.
    needed = _REQUIRED_FIELDS.get(requirement.name)
    if not needed:
        return True, ""
    token = str(namespace or "").strip()
    if not token:
        return True, ""
    try:
        writable = _fr.writable_fields(token)
    except KeyError:
        # An unclassified namespace is NOT KNOWN to refuse. Reporting it as
        # unprovisionable would hide a baseline document on every sandbox nobody has
        # claimed yet, and not knowing is not the same as knowing it will not work —
        # the same posture `contacts_manager.unwritable_fields` takes on the read side.
        return True, ""
    missing = tuple(f for f in needed if f not in writable)
    if missing:
        return False, (
            f"the {token} namespace cannot express a {requirement.name}: it defines no "
            f"{', '.join(missing)}"
        )
    return True, ""


def baseline_rows(
    requirement: DocumentRequirement, *, namespace: str, label: str = "",
) -> tuple:
    """The rows a NEW copy of this baseline document is created with.

    Blank for all of them but one. The local domain is seeded with its root and the
    reserved branches, because "a domain with no root has nothing to hang a type on" —
    the bootstrap convention :func:`seeded_local_domain_rows` states and owns.

    Raises ``ValueError`` for a requirement :func:`provisionable` refuses. Callers are
    expected to ask first; this raises rather than returning blank rows because a local
    domain with no root is exactly the uneditable document the seed exists to prevent, and
    returning one quietly would be worse than stopping.
    """
    if requirement.name != LCL_DOCUMENT:
        return ()
    return seeded_local_domain_rows(
        str(namespace or ""), label=str(label or "").strip() or DOMAIN_ROOT_LABEL)


__all__ = [
    "BASELINE_DOCUMENTS",
    "DOMAIN_ROOT_LABEL",
    "DOMAIN_ROOT_NODE",
    "LCL_DOCUMENT",
    "LEGACY_LCL_DOCUMENT",
    "LOCAL_DOMAIN_NAMES",
    "REFUSED_BY_NAMESPACE",
    "baseline_rows",
    "is_anchored",
    "is_local_domain",
    "missing_baseline",
    "provision_name",
    "provisionable",
    "satisfies",
    "seeded_local_domain_rows",
]
