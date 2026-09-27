"""Render a datum document through its viewscope — one document read, never the catalog.

The workbench has two view modes today, both spreadsheets: ``interpreted`` and ``raw``.
This adds a third. Where those show a document's ROWS, a viewscope shows the document as
the thing it is — a boundary as geometry, a directory as lines, a jurisdiction as a name
beside its boundary — because its archetype says which primitives draw it.

**Cost.** ``read_authoritative_datum_documents`` parses one 138 MB blob holding all 544
documents (~350 MB warm, and the reason a document-level write costs this portal ~690 MB).
This surface reads the subject document from ``datum_document_semantics`` — 6 KB for the
median document — and the archetype library with one per-sandbox read: measured, **34
documents in 0.004 s at 22 MB**. Nothing here touches the catalog.

The four biggest documents in the store (42 MB, 30 MB, 27 MB, 12 MB) are refused with a
stated reason rather than rendered. A viewscope over 26,670 auction rows is not a view.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from micyte.core import archetypes as arc
from micyte.core.datum_documents import AuthoritativeDatumDocument, AuthoritativeDatumDocumentRow
from micyte.core.datum_ops import archetype_class as ac
from micyte.core.datum_ops import archetype_shape as ash
from micyte.core.datum_ops import viewscope as vs
from micyte.core.datum_ops.datum_resolve import as_text, decode_label, iter_marker_pairs
from micyte.core.document_naming import parse_canonical_document_id
from micyte.core.structures.hops import decode_hops_coordinate_token

from ._node_names import EMPTY_INDEX, name_index_for

#: Where the shared leaflet pool is mounted, for any slot that draws one.
ICON_URL_PREFIX = "/assets/icons/"

SCHEMA = "mycite.v2.portal.workbench.viewscope.v1"
TENANT_DEFAULT = "fnd"

#: How many rows a container will draw before refusing, keyed by container. The point of a
#: viewscope is legibility; 26,670 LINES is not more legible than a spreadsheet.
#:
#: A tree gets more room because depth is what makes it readable: 4,119 taxonomy nodes are
#: a tree, and a tree of that size is exactly the thing a list cannot show. The giant
#: market logs are `record_line` and stay refused.
MAX_RENDERED_ROWS = 2000
MAX_ROWS_BY_CONTAINER: dict[str, int] = {"tree": 8000}


def _row_budget(container: str) -> int:
    return MAX_ROWS_BY_CONTAINER.get(as_text(container), MAX_RENDERED_ROWS)

#: Slot values that are references resolve to another document and draw ITS viewscope
#: inline. Bounded to one hop: a profile drawing a boundary is the composition the brief
#: asks for; a profile drawing a profile drawing a boundary is a cycle waiting to happen.
MAX_REFERENCE_DEPTH = 1


def _document_from_payload(document_id: str, payload: dict[str, Any]) -> AuthoritativeDatumDocument:
    parts = document_id.split(".")
    name = parts[3] if len(parts) > 4 else document_id
    sandbox = parts[2] if len(parts) > 4 else ""
    return AuthoritativeDatumDocument(
        document_id=document_id,
        source_kind=as_text(payload.get("source_kind")) or "sandbox_source",
        document_name=f"{name}.json",
        relative_path=f"{sandbox}/{name}.json",
        canonical_name=name,
        tool_id=sandbox,
        is_anchor=False,
        rows=tuple(
            AuthoritativeDatumDocumentRow(
                datum_address=as_text(item.get("datum_address")), raw=item.get("raw")
            )
            for item in payload.get("rows", ())
        ),
        document_metadata=payload.get("document_metadata") or {},
    )


def read_document(store: Any, *, tenant_id: str, document_id: str) -> AuthoritativeDatumDocument | None:
    """One document, from its own semantics row. Never the catalog."""
    identity = store.read_document_version_identity(tenant_id=tenant_id, document_id=document_id)
    if not identity:
        return None
    return _document_from_payload(document_id, identity.get("canonical_payload") or {})


def _row_values(head: list[Any], *, namespace: str) -> dict[str, list[str]]:
    """``field -> its cells`` for one row head, folded in ``namespace``.

    A NAMESPACE, not a sandbox — the parameter was called `sandbox` until 2026-08-27 and
    the two are the same word only for a sandbox exactly one instance can hold. Eight
    instances keep a core sandbox called `system`; six of those speak REGISTRAR, one
    SYSTEM, one FARM, and they put `title` at 3-1-3, 3-1-5 and 3-1-2. Folding by the name
    does not error, it returns cells belonging to other fields.

    Callers holding an msn should resolve the pair first
    (`field_registry.namespace_for_sandbox(sandbox, msn_id=...)`). The tools that pass a
    bare sandbox token still read correctly for every sandbox whose name IS its namespace,
    which is what each of them addresses today — the rename is what makes the assumption
    visible at their call sites instead of hidden in this signature.
    """
    """``logical field -> its decoded magnitudes``, in row order.

    A list per field because a run is a run: a polygon's coordinates and a person's name
    parts both arrive as several cells of one field, and collapsing them to the first would
    silently drop the rest.
    """
    values: dict[str, list[str]] = {}
    for marker, magnitude in iter_marker_pairs(head):
        name = ash._field_name(as_text(marker), sandbox=namespace)
        values.setdefault(name, []).append(decode_label(magnitude))
    return values


def rows_for_archetype(
    document: Any, archetype: Any, *, namespace: str
) -> Iterator[tuple[Any, dict[str, list[str]]]]:
    """Every row of ``document`` that ``archetype`` covers, paired with its folded values.

    The one loop three readers had written out separately — the viewscope's `matched`, the
    jobs table and the jobs synopsis. They agreed, which is the only reason nothing had
    diverged yet; a document that holds rows of SEVERAL archetypes is now ordinary (a job
    document is a `job` header plus N `job_service` rows), so this is about to be the
    common case rather than a coincidence.

    ``values`` is :func:`_row_values` over the row's head, so a run field arrives as a
    LIST. That is what `job_service`'s optional `nominal` run needs: `driveway` carries no
    counter, `story_siding_wash` carries one, and a service measured two ways carries two —
    collapsing to the first would silently drop a quantity the job is priced on.

    A NAMESPACE, not a sandbox, for the reason :func:`_row_values` gives. This passes the
    caller's argument STRAIGHT THROUGH rather than resolving a pair here: resolving would
    quietly change what `job_manager` and `job_synopsis` read, both of which hand a bare
    sandbox token — correct only for a sandbox whose name IS its namespace, which is what
    they address today. Making that assumption visible at their call sites is the point of
    the rename; changing it is a different change with its own evidence.

    The head is read with :func:`archetype_shape._row_head`, the SAFE spelling. `row.raw[0]`
    raises on a row whose raw is not a list of lists, where `_row_head` answers ``[]``; the
    two can only differ on rows this never yields, because `row_shape` folds that same
    malformed row to layer ``"?"`` and no archetype declares that layer. The safe form is
    used so that stays true if `covers` is ever widened.

    ``getattr(document, "rows", ())`` because `job_manager._job_rows` is handed
    `read_document`'s result with no None check: a sandbox with no job log has to read as
    no rows, not as an AttributeError inside a table renderer.

    NOT for the writer's pre-write check in `job_document_runtime.create_job_document`.
    That loop walks rows it just built (no document), picks a DIFFERENT archetype per row
    index, and a row its archetype does not cover is a refusal carrying the folded shape —
    not a skip. Filtering there would turn a guard into a silent drop, which is the one
    thing a check written because "a row the viewscope cannot fold is written and gone"
    must never become.
    """
    if archetype is None:
        return
    for row in getattr(document, "rows", ()) or ():
        if not archetype.covers(ash.row_shape(row.raw, sandbox=namespace)):
            continue
        yield row, _row_values(ash._row_head(row.raw), namespace=namespace)


def _ring(cells: list[str]) -> list[list[float]]:
    """A run of HOPS coordinate tokens -> ``[[lon, lat], ...]``.

    Decoded from the cells the FOLD identified as `coordinate`, not by hunting for a
    marker literal. `datum_resolve.resolve_coordinate` does the latter — it matches
    `Markers.COORDINATE`, which is `rf.3-1-3`, the FARM marker — so it decodes the two farm
    profiles and none of the 469 registrar boundaries, whose coordinate is `rf.3-1-1`. That
    is the same namespace blindness `hops_geospatial_filament` has, one layer down: a
    geometry decoder keyed on a physical marker can only read one anchor's geometry.
    """
    points: list[list[float]] = []
    for cell in cells:
        decoded = decode_hops_coordinate_token(cell)
        if decoded:
            points.append(
                [decoded["longitude"]["value"], decoded["latitude"]["value"]]
            )
    return points


def _sandbox_radices(
    store: Any, *, tenant_id: str, sandbox: str, msn_id: str = ""
) -> dict[str, str]:
    """How this sandbox encodes each field, from its OWN anchor. ``{}`` when unreadable.

    Empty means "nothing is writable", which is the safe direction: an unreadable anchor
    must not hand out inputs for values nobody can say how to encode.

    ``msn_id`` narrows to WHOSE anchor. Eight instances hold a sandbox called `system`,
    so without it this returned whichever one the store yielded first and every other
    instance was told how somebody else's anchor encodes its fields.
    """
    from micyte.core.datum_ops import viewscope_edit as ve

    try:
        for document in store.read_documents_by_sandbox(
                tenant_id=tenant_id, sandbox=sandbox, msn_id=as_text(msn_id)):
            if getattr(document, "is_anchor", False):
                return ve.backing_radices(document)
    except Exception:
        return {}
    return {}


#: What an INSTANCE may say it is. Two answers, because that is the whole of the
#: registrar's concern: a party is a legal entity or a natural one.
#:
#: The registrar's own `entity_class` branch carries four — `administrative` alone is
#: cited 57 times, by the counties and municipalities the registrar must obviously keep,
#: and `informal` 3 times. Those are classifications of PLACES and PARTIES in the
#: registry, not of instances. `seed_instance_kind_vocabulary` mirrored the branch
#: wholesale, so every client's profile offered "administrative" as something it could
#: declare itself to be.
#:
#: The finer classification of a legal entity — producer, orchard, food hub — belongs to
#: the AGNET channel, which builds those profiles over msn_ids it already assumes are
#: legal entities carrying the registrar's own type indicator. That is the first place
#: the distinction is relevant, and it is not here.
#:
#: Enforced by NARROWING THE OFFER rather than by pruning the trees. The lcl-SAMRAS
#: contiguity rule refuses a delete that leaves a gap, so removing `informal` would mean
#: removing `natural` first and re-adding it — which renumbers it, and three instances
#: store their kind as that exact address.
INSTANCE_KIND_BRANCH = "kind"
INSTANCE_KINDS: tuple[str, ...] = ("legal", "natural")


def lcl_options(store: Any, *, tenant_id: str, sandbox: str, namespace: str,
                msn_id: str = "", branch: str = "") -> list[dict[str, str]]:
    """``[{value, label}]`` — the nodes under the ``branch`` this sandbox's domain defines.

    What an lcl-addressed slot may be set to, and it is a BRANCH, not the whole tree. The
    first cut offered every node in the local domain, so the `kind` slot on a client's
    profile listed `Anchor`, `documents`, `icons` and `Local domain log` beside the four
    real answers — a picker whose options are mostly not answers to the question asked.

    The branch is the SLOT'S OWN LABEL. A viewscope slot says what it means ("kind"), and
    the domain answers with the branch of that name — so making a slot settable is a matter
    of naming a branch after it, in the Domain editor, with no code here. `job_manager`
    reaches the same place from the other side: its job types are the sandbox's own lcl
    children, and an instance that adds "gutter cleaning" gets it in the form.

    ``[]`` when the domain has no such branch, which the caller turns into a stated reason
    rather than an empty dropdown.

    Narrowed by the PAIR. Eight instances hold a sandbox called `system`, and offering one
    instance's vocabulary on another's form would let a client file itself under a node its
    own domain does not define — which the writer then refuses, so the operator would meet
    a dropdown whose every option is rejected.
    """
    from micyte.core.datum_ops import local_domain as ld
    from micyte.core.instance_baseline import is_local_domain
    from micyte.core.instance_scope import use_instance

    wanted = as_text(branch).lower()
    if not wanted:
        return []
    try:
        with use_instance(msn_id):
            documents = list(store.read_documents_by_sandbox(
                tenant_id=tenant_id, sandbox=sandbox, msn_id=msn_id))
    except Exception:
        return []
    log = None
    for document in documents:
        if is_local_domain(as_text(getattr(document, "canonical_name", ""))):
            log = ld.read_log(document)
            break
    if log is None:
        return []
    root = next((node for node, entry in log.entries.items()
                 if as_text(entry.label).lower() == wanted), "")
    if not root:
        return []
    children = [(node, as_text(entry.label))
                for node, entry in log.entries.items()
                if ld.parent_of(node) == root and as_text(entry.label)]
    children.sort(key=lambda pair: [int(part) for part in pair[0].split("-")])
    if wanted == INSTANCE_KIND_BRANCH:
        # See INSTANCE_KINDS. The nodes stay in the tree — they cannot be removed without
        # renumbering a sibling three instances cite — but they stop being offered.
        children = [pair for pair in children if pair[1].lower() in INSTANCE_KINDS]
    return [{"value": node, "label": label} for node, label in children]


def _slot_payload(
    slot: vs.Slot,
    values: dict[str, list[str]],
    names=EMPTY_INDEX,
    per_row: list[dict[str, list[str]]] | None = None,
    *,
    namespace: str = "",
    radices: dict[str, str] | None = None,
    options: Any = None,
) -> dict[str, Any]:
    from micyte.core.datum_ops import field_registry as fr
    from micyte.core.datum_ops import viewscope_edit as ve

    cells = values.get(slot.field, [])
    # Whether this slot can be typed into, and — when it cannot — WHY. The SAME question
    # the write runtime asks, asked through the same function: the primitive alone marked
    # `utc` and `price` editable, so the surface offered a text box for a HOPS token and a
    # price in cents, and the save refused both. A reader and a writer that disagree about
    # what is editable meet the operator as a form that does not work.
    try:
        address = fr.address(namespace, slot.field) if namespace else ""
    except KeyError:
        address = ""
    reason = ve.refusal_for(
        primitive=slot.primitive, address=address, radices=radices or {}
    )
    payload = {
        "field": slot.field,
        "label": slot.display_label,
        "primitive": slot.primitive,
        "values": cells,
        "present": bool([c for c in cells if c]),
        "editable": not reason,
        "not_editable_because": reason,
    }
    # A slot whose value is a NODE is chosen, not typed. The options travel with it so the
    # form can offer them; a text box for a node address invites a value the writer will
    # refuse, and the operator would meet the refusal after typing rather than before.
    if not reason and radices and radices.get(address) == ve.LCL_RADIX:
        # The slot's own LABEL names the branch it draws from — see `lcl_options`.
        branch = slot.display_label or slot.field
        payload["choices"] = list(options(branch) if callable(options) else (options or []))
        payload["choice_of"] = branch
        # The LABEL beside the address, never instead of it. A client chooses "natural"
        # and the row stores `2-1-4`, so a panel showing only the address shows them
        # something they did not pick; one showing only the label hides the value that is
        # actually stored, which is the thing a re-key changes. Both, the way a node chip
        # already carries `names` beside its cells.
        by_value = {option["value"]: option["label"] for option in payload["choices"]}
        resolved = [by_value.get(cell, "") for cell in cells]
        if any(resolved):
            payload["names"] = resolved
        if not payload["choices"]:
            # An empty vocabulary is not an empty field. Said out loud, or the form draws
            # a dropdown with nothing in it and the reason looks like a bug.
            payload["editable"] = False
            payload["not_editable_because"] = (
                f"this sandbox's local domain has no {branch!r} branch to choose from — "
                f"add one in the Domain editor and its children become the options here"
            )
    # A chip or a reference names a NODE; showing the address where the old viewer
    # showed "city_of_akron" is not a replacement for it. Resolved names ride BESIDE
    # the addresses rather than replacing them, so the renderer can show the name and
    # the operator can still see what it is a name for.
    if slot.primitive == "map_ring":
        # One ring PER ROW, never one merged ring. A farm profile holds four parcels in
        # four rows; merging their coordinates draws a single polygon whose edges cross
        # the gaps between them — a shape that exists nowhere on the ground.
        sources = per_row if per_row is not None else [values]
        rings = [r for r in (_ring(source.get(slot.field, [])) for source in sources) if r]
        if rings:
            points = [point for ring in rings for point in ring]
            lons = [p[0] for p in points]
            lats = [p[1] for p in points]
            payload["rings"] = rings
            # The bbox travels with the geometry so the renderer can draw without knowing a
            # projection: an SVG viewBox over the rings' own extent is the whole map.
            payload["bounds"] = [min(lons), min(lats), max(lons), max(lats)]
            payload["undecoded"] = len([c for c in cells if c]) - len(points)
    if slot.primitive == "symbol":
        # An icon_ref is a leaflet STEM, not a URL. The prefix travels with the slot so the
        # renderer never has to know where the shared pool is mounted — the same contract
        # `renderTypeIcon` already reads for the taxonomy tree, rather than a second one.
        payload["icon_url_prefix"] = ICON_URL_PREFIX
    if slot.primitive in ("node_chip", "reference"):
        resolved = [names.name_for(cell) for cell in cells]
        if any(resolved):
            payload["names"] = resolved
    return payload


def _document_identity(document_id: str) -> tuple[str, str, str]:
    """``(msn, sandbox, name)`` from a canonical id, without touching the store.

    Through the canonical parser rather than by splitting on dots, so a malformed id
    yields empties instead of three plausible-looking segments — the same rule
    :func:`~archetype_shape.sandbox_of` follows, and for the same reason: a guessed
    namespace is the failure this program cannot detect afterwards.

    Reading these off the id is what lets the address-space branch decide before the 27 MB
    read rather than after it.

    The MSN joined on 2026-08-27, and it is the half that makes the sandbox usable. A
    sandbox is addressed by the PAIR, and everything below needs the pair for two
    different questions: which documents to read, and which numbering to read their
    markers with.
    """
    try:
        parsed = parse_canonical_document_id(as_text(document_id))
    except Exception:
        return "", "", ""
    return as_text(parsed.msn_id), as_text(parsed.sandbox), as_text(parsed.name)


def build_viewscope_payload(
    *,
    authority_db_file: Path | None,
    tenant_id: str = TENANT_DEFAULT,
    document_id: str,
    archetype: str = "",
    depth: int = 0,
    space_root: str = "",
) -> dict[str, Any]:
    """The ``panel_payload`` for one document, or an envelope saying why there is none."""
    def empty(reason: str, **extra: Any) -> dict[str, Any]:
        return {"schema": SCHEMA, "container": "", "document_id": document_id,
                "reason": reason, **extra}

    if authority_db_file is None:
        return empty("authority database not configured")
    # Lazy, matching `_archetype.read_sandbox_catalog`: keeps the tools layer free of an
    # adapter import at module scope.
    from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

    store = SqliteSystemDatumStoreAdapter(authority_db_file)

    # The sandbox comes off the ID, not out of the document, so everything below can be
    # decided without reading it. `address_nodes` is 27 MB and 203 MB of row objects; the
    # old order read it and THEN refused it, which is the most expensive way to say no.
    msn_id, sandbox, document_name = _document_identity(document_id)
    if not sandbox:
        return empty("document id is not canonical, so its namespace cannot be resolved")
    # WHICH SANDBOX and WHICH NUMBERING are two questions, and this module answered both
    # with the one token until 2026-08-27.
    #
    # `sandbox` stays the sandbox: it is what the store is read by. `namespace` is what a
    # marker is resolved through, and for a sandbox only one instance can hold they are
    # the same word — which is why nothing noticed. They are not the same for the eight
    # instances that each keep a core sandbox called `system`: six of those speak
    # REGISTRAR, one SYSTEM, one FARM, and they put `title` at 3-1-3, 3-1-5 and 3-1-2.
    #
    # Measured on a client's `msn_profile`, folded by the NAME: `matched_rows: 0`, every
    # slot empty, and the editability reason reading "this sandbox's anchor declares no
    # babelette at 3-1-5" — an address from a numbering that instance does not speak. The
    # document rendered as a blank grid and said nothing was wrong with it.
    #
    # Resolved from the PAIR, which the document id already carries. For every sandbox
    # whose name did answer — registrar, taxonomy, agnet, archetype, glyph, grantor — the
    # pair has no claim and the name is still the answer, so this can only fix.
    from micyte.core.datum_ops import field_registry as _fr

    try:
        namespace = _fr.namespace_for_sandbox(sandbox, msn_id=msn_id)
    except KeyError:
        namespace = sandbox
    library = store.read_documents_by_sandbox(tenant_id=tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
    registry = arc.registry_for(library)
    # How this sandbox ENCODES each field, read from its own anchor. The reader needs it
    # because `editable` has to mean exactly what the writer means: the primitive alone
    # marked `utc` and `price` editable, so the surface offered a text box for a HOPS
    # token and the save then refused it. Two answers to one question, and the operator
    # met both of them.
    radices = _sandbox_radices(
        store, tenant_id=tenant_id, sandbox=sandbox, msn_id=msn_id)
    # PER SLOT, because the branch a slot offers is the slot's own label — memoized on
    # the branch name so two slots asking the same question still walk the domain once.
    _branch_cache: dict[str, list[dict[str, str]]] = {}

    def node_choices(branch: str) -> list[dict[str, str]]:
        if branch not in _branch_cache:
            _branch_cache[branch] = lcl_options(
                store, tenant_id=tenant_id, sandbox=sandbox, namespace=namespace,
                msn_id=msn_id, branch=branch)
        return _branch_cache[branch]
    viewscopes, problems = vs.load_viewscopes(library)
    names = name_index_for(store, tenant_id=tenant_id, sandbox=sandbox, registry=registry)

    space = _address_space_payload(
        store, tenant_id=tenant_id, document_id=document_id, sandbox=sandbox,
        document_name=document_name, names=names, viewscopes=viewscopes, root=space_root,
    )
    if space is not None:
        space["warnings"] = list(problems)
        return space

    document = read_document(store, tenant_id=tenant_id, document_id=document_id)
    if document is None:
        return empty("document not found")

    # A document can be several things at once. `<a_farm>/farm_profile` is a
    # `geospatial_polygon` by row count AND holds three `sited_feature` rows, and the two
    # are different views of it — the boundary and the things standing on it. So a caller
    # may NAME which archetype to draw; without one the primary wins, which is what an
    # operator opening the document raw should see.
    available = list(registry.archetypes_for(document, sandbox=namespace))
    primary = as_text(archetype) or registry.primary_archetype(
        document, sandbox=namespace)
    if archetype and primary not in available:
        return empty(f"this document has no {primary!r} rows", archetypes=available)
    if not primary:
        # A document can DECLARE what its rows will be before it has any. Provisioning
        # seeds a baseline document structurally — one row carrying its address and no
        # field markers, so it cannot be misread as a record of some other kind — which
        # means nothing about its rows says what it is. Its metadata does.
        #
        # Without this a freshly provisioned `msn_profile` or `calendar` renders as "no
        # archetype matches this document's rows", which is true and useless: the operator
        # is told the document is unrecognisable when it is simply EMPTY, and the form it
        # is waiting for is already declared.
        declared = as_text((document.document_metadata or {}).get("archetype"))
        if declared and registry.get(declared) is not None:
            primary = declared
            available = available or [declared]
        else:
            return empty("no archetype matches this document's rows", archetypes=available)
    archetype = registry.get(primary)
    # Specific beats general: this archetype's own viewscope, else the nearest CLASS up its
    # lineage that declares slots. Before the class layer, the four archetypes no viewscope
    # named simply did not draw — an operator opening one got a sentence where a document
    # should be.
    classes, class_problems = ac.load_classes(library)
    problems = [*problems, *class_problems]
    scope, scope_source = vs.resolve_viewscope(
        primary, viewscopes, classes,
        declared_fields=archetype.declared_fields if archetype is not None else None,
    )
    if scope is None:
        return empty(
            f"{primary} has no viewscope, and no class draws it either", archetype=primary)

    # The DECLARATION is per archetype; the CONTAINER also depends on how many rows of that
    # archetype the document holds. `administrative_entity_profile` declares a slot_grid —
    # right for one jurisdiction — but `registrar/administrative_entity` holds 53 of them,
    # and a grid showing the first would silently hide 52. A document with many rows of one
    # archetype is a DIRECTORY of it.
    #
    # Geometry is the exception: several rings are layers of one drawing, not lines of a
    # list, so a viewscope carrying a map_ring keeps its grid and merges the rows.
    budget = _row_budget(scope.container)
    if len(document.rows) > budget:
        return empty(
            f"{len(document.rows)} rows — more than a {scope.container} draws ({budget}); "
            "the raw grid pages, a viewscope would not",
            archetype=primary,
        )

    # AFTER the budget refusal, because folding is what the refusal exists to avoid. The
    # filter used to run first and cost only a `row_shape` per row; pairing each row with
    # its values costs a fold as well, and running that over the 26,670-row market log on
    # the way to declining to draw it is exactly the read this module's header is about.
    matched = list(rows_for_archetype(document, archetype, namespace=namespace))

    geometry = any(s.primitive == "map_ring" for s in scope.slots)
    container = scope.container
    if container == "slot_grid" and len(matched) > 1 and not geometry:
        container = "record_line"

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "container": f"viewscope_{container}",
        "declared_container": scope.container,
        "document_id": document_id,
        "document_name": document.canonical_name,
        "sandbox": sandbox,
        "archetype": primary,
        "archetypes_available": available,
        "archetype_note": (archetype.note if archetype else ""),
        # "written for this archetype" and "inherited from the profile class" are different
        # facts about a rendering, and an operator looking at a wrong-looking document needs
        # to know which one is on screen before they go looking for the declaration.
        "viewscope_source": scope_source,
        "archetype_class": classes.class_of(primary),
        "row_count": len(document.rows),
        "matched_rows": len(matched),
        "warnings": list(problems),
        "names_indexed": len(names),
    }

    if container == "glyph_canvas":
        # The document IS the drawing, so nothing here reads slots or matched rows: the
        # whole row set decodes through the codec or the surface says why it did not. A
        # half-drawn glyph is worse than a stated refusal — it looks like a drawing.
        from micyte.core.datum_ops import glyph as gl

        payload["view_box"] = gl.VIEW_BOX
        try:
            drawing = gl.glyph_of(document.rows)
        except gl.GlyphError as error:
            payload["paths"] = []
            payload["glyph_error"] = str(error)
            return payload
        payload["paths"] = [
            {"d": path.to_text(), "fill": bool(path.fill)} for path in drawing.paths
        ]
        payload["glyph_error"] = ""
        return payload

    if container == "record_line":
        payload["columns"] = [
            {"field": s.field, "label": s.display_label, "primitive": s.primitive}
            for s in scope.slots
        ]
        payload["lines"] = [
            {
                "datum_address": row.datum_address,
                "slots": [_slot_payload(s, values, names, namespace=namespace,
                                       radices=radices, options=node_choices)
                          for s in scope.slots],
            }
            for row, values in matched
        ]
        return payload

    if container == "tree":
        payload.update(_tree_payload(scope, matched, namespace=namespace, names=names,
                                     radices=radices))
        return payload

    # slot_grid — the FIRST matching row is the document's identity. A slot_grid over many
    # rows would be a list with extra steps, and the archetypes that use it (profiles,
    # boundaries) are one-subject documents by construction.
    # Merge every matching row: one row for a profile, several rings for a boundary.
    per_row = [values for _row, values in matched]
    values: dict[str, list[str]] = {}
    for row_values in per_row:
        for field, cells in row_values.items():
            values.setdefault(field, []).extend(cells)
    payload["groups"] = [
        {
            "name": group,
            "slots": [
                _slot_payload(s, values, names, per_row, namespace=namespace,
                              radices=radices, options=node_choices)
                for s in scope.slots_in(group)
            ],
        }
        for group in scope.groups
    ]
    payload["datum_address"] = matched[0][0].datum_address if matched else ""

    if depth < MAX_REFERENCE_DEPTH:
        _resolve_references(payload, store=store, tenant_id=tenant_id, sandbox=sandbox, depth=depth)
    return payload


def viewscope_pane(
    authority_db_file: Path | None,
    *,
    sandbox: str,
    names: tuple[str, ...],
    archetype: str = "",
    tenant_id: str = TENANT_DEFAULT,
) -> dict[str, Any]:
    """A viewscope payload for the first of ``names`` that exists in ``sandbox``.

    One helper, because six panes each doing their own resolution is six chances to resolve
    a different document than the viewer they replace did. `names` is a list rather than a
    name because a pane's subject is not always spelled the same: `local_domain` reads
    `lcl` in four sandboxes and `txa` in `taxonomy`.

    Resolution is by NAME, deliberately. The viewers resolved by archetype and fell through
    to "the first document in the sandbox" when none matched — which is how `planting_map`
    came to render a sandbox's ANCHOR in four of seven sandboxes. A pane that cannot find
    its subject should say so, not draw whatever was first.
    """
    if authority_db_file is None:
        return {"schema": SCHEMA, "container": "", "reason": "authority database not configured"}
    from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

    store = SqliteSystemDatumStoreAdapter(Path(authority_db_file))
    for name in names:
        if True:
            found = store.document_id_for(
                tenant_id=tenant_id, sandbox=as_text(sandbox), name=as_text(name))
            row = {"document_id": found} if found else None
            if row is not None:
                return build_viewscope_payload(
                    authority_db_file=Path(authority_db_file),
                    tenant_id=tenant_id,
                    document_id=row["document_id"],
                    archetype=archetype,
                )
    return {
        "schema": SCHEMA, "container": "",
        "reason": f"{sandbox} has no {' or '.join(names)} document",
    }


#: Fields whose value is a SAMRAS node address, and so can carry a hierarchy. The tree
#: nests on the FIRST of these a viewscope declares.
TREE_KEY_FIELDS: tuple[str, ...] = ("txa_id", "lcl_id", "msn_id")


def _address_space_payload(
    store: Any,
    *,
    tenant_id: str,
    document_id: str,
    sandbox: str,
    document_name: str,
    names: Any,
    viewscopes: dict[str, Any],
    root: str = "",
) -> dict[str, Any] | None:
    """Browse a name table too large to LIST, or ``None`` if this is not one.

    A name table over a SAMRAS address space has a hierarchy already in its keys, so a
    document that cannot be a list can still be a tree — and the tree does not have to be
    built from the document. :mod:`._address_space` folds it out of the name index, which
    is memoized on the store's mtime and holds every address in the sandbox.

    Two things follow, and both matter:

    * **The document is never read.** Whether to browse rather than list is answered by a
      b-tree count and a lookup in :attr:`NameIndex.tables`, both of which cost under
      12 ms against `address_nodes`' 5.5 s and 203 MB.
    * **The space is MERGED across name tables, not per document**, which is why a street
      address hangs under a named city. `address_nodes` names 41,998 leaves and
      `registrar/administrative` names the 2,690 nodes above them; a tree of either alone
      is a tree of orphans. The contributing tables ride in the payload so the operator can
      see which documents the space is made of.
    """
    table = next(
        (t for t in getattr(names, "tables", ()) if t.sandbox == sandbox and t.name == document_name),
        None,
    )
    if table is None or table.key_field not in TREE_KEY_FIELDS:
        return None
    scope = viewscopes.get(table.archetype)
    budget = _row_budget(scope.container if scope is not None else "")
    rows = store.count_document_rows(tenant_id=tenant_id, document_id=document_id)
    # Under the budget it is a list, and a list of 66 lcl classes is the better view. The
    # address space is what a document earns by being too big to draw as itself.
    if rows <= budget and not as_text(root):
        return None

    from ._address_space import address_space_for

    space = address_space_for(names, key_field=table.key_field)
    view = space.tree(as_text(root))
    contributors = [
        {"source": t.source, "archetype": t.archetype, "named": t.named}
        for t in names.tables
        if t.key_field == table.key_field
    ]
    return {
        "schema": SCHEMA,
        "container": "viewscope_tree",
        "declared_container": "tree",
        "document_id": document_id,
        "document_name": document_name,
        "sandbox": sandbox,
        "archetype": table.archetype,
        "archetypes_available": [table.archetype],
        "archetype_note": (
            f"{rows} rows is past what a list draws ({budget}), and an "
            f"{table.key_field} IS a path — so this is the address space, browsed."
        ),
        "address_space": True,
        "key_field": table.key_field,
        "columns": [],
        "row_count": rows,
        "matched_rows": table.named,
        "space_total": len(space),
        "space_sources": contributors,
        "names_indexed": len(names),
        **view,
    }


def _tree_payload(
    scope: vs.Viewscope, matched: list, *, namespace: str, names,
    radices: dict[str, str] | None = None,
) -> dict[str, Any]:
    """One node per matching row, nested by the address its key field holds.

    ``matched`` is :func:`rows_for_archetype`'s ``(row, values)`` pairs — the fold is done
    once by the caller, for every container, rather than a third time here.

    A SAMRAS address IS its path — ``1-1-3-3-5-8`` sits under ``1-1-3-3-5`` — so the
    hierarchy needs no declaring; it is already in the data. Nothing here reads a
    parent/child edge from anywhere else, which is why a taxonomy, an lcl class tree and an
    msn address space all nest with one rule.

    A node whose exact parent is absent attaches to its NEAREST PRESENT ancestor rather
    than becoming a root. Documents are sparse — `taxonomy/txa` defines cultivars whose
    intermediate ranks it does not — and promoting a deep node to the top would say the
    document claims something it does not.
    """
    key = next((s.field for s in scope.slots if s.field in TREE_KEY_FIELDS), "")
    if not key:
        return {"nodes": [], "reason": f"no tree key among {[s.field for s in scope.slots]}"}
    columns = [s for s in scope.slots if s.field != key]

    entries: dict[str, dict[str, Any]] = {}
    for row, values in matched:
        address = next((v for v in values.get(key, ()) if v), "")
        if not address or address in entries:
            continue
        entries[address] = {
            "address": address,
            "datum_address": row.datum_address,
            "label": names.label(address),
            # A tree is a navigation view and never edits, but it asks the same question
            # anyway: a slot reporting "no address in this anchor" because nobody passed
            # the sandbox is a reason that is not true.
            "slots": [
                _slot_payload(s, values, names, namespace=namespace, radices=radices)
                for s in columns
            ],
        }

    def nearest_ancestor(address: str) -> str:
        parts = address.split("-")
        for cut in range(len(parts) - 1, 0, -1):
            candidate = "-".join(parts[:cut])
            if candidate in entries:
                return candidate
        return ""

    def sort_key(address: str) -> tuple:
        return tuple(int(p) if p.isdigit() else p for p in address.split("-"))

    children: dict[str, list[str]] = {}
    for address in entries:
        children.setdefault(nearest_ancestor(address), []).append(address)
    for bucket in children.values():
        bucket.sort(key=sort_key)

    nodes: list[dict[str, Any]] = []
    # Iterative, not recursive: a 4,119-node taxonomy is deep enough that a recursive walk
    # is a stack risk for no gain, and the flat list with a depth is what the renderer wants
    # anyway — it can hide a subtree without re-walking anything.
    stack = [(address, 0) for address in reversed(children.get("", []))]
    while stack:
        address, depth = stack.pop()
        entry = entries[address]
        kids = children.get(address, ())
        nodes.append({**entry, "depth": depth, "children": len(kids)})
        stack.extend((child, depth + 1) for child in reversed(kids))

    return {
        "key_field": key,
        "columns": [
            {"field": s.field, "label": s.display_label, "primitive": s.primitive}
            for s in columns
        ],
        "nodes": nodes,
        "roots": len(children.get("", [])),
        "max_depth": max((n["depth"] for n in nodes), default=0),
    }


def _resolve_references(
    payload: dict[str, Any], *, store: Any, tenant_id: str, sandbox: str, depth: int
) -> None:
    """Draw a referenced document's own viewscope inside the slot that names it.

    This is the composition the brief describes: an ``administrative_entity_profile``
    carries ``region_polygon_ref``, so a jurisdiction shows its boundary without a bespoke
    map viewer — the boundary draws itself, exactly as it would if opened directly.
    """
    for group in payload.get("groups", ()):
        for slot in group.get("slots", ()):
            if slot.get("primitive") != "reference":
                continue
            target = next((v for v in slot.get("values", ()) if v), "")
            if not target:
                continue
            resolved = _document_named(store, tenant_id=tenant_id, sandbox=sandbox, name=target)
            if resolved is None:
                slot["reference_reason"] = f"no document named {target!r} in {sandbox}"
                continue
            slot["reference"] = build_viewscope_payload(
                authority_db_file=store._db_file,
                tenant_id=tenant_id,
                document_id=resolved,
                depth=depth + 1,
            )


def _document_named(
    store: Any, *, tenant_id: str, sandbox: str, name: str, msn_id: str = ""
) -> str:
    """The id of the document named ``name`` in ``sandbox``, or ``""``.

    A ``region_polygon_ref`` holds an msn node address, and the registrar names its boundary
    documents for exactly that address — ``registrar/3-2-3-17-85`` IS Wayne County's node.
    So the reference resolves by NAME, which is a denotation, rather than by scanning every
    document for one that mentions it.

    A name denotes within ONE instance, though, and every instance's core sandbox is called
    ``system`` — so the lookup goes through ``document_id_for``, which applies the request's
    instance scope when the sandbox name is held by more than one msn and leaves shared
    sandboxes like ``registrar`` alone.
    """
    return store.document_id_for(
        tenant_id=tenant_id, sandbox=sandbox, name=as_text(name), msn_id=msn_id)


def local_domain_document_id(
    store: Any, *, tenant_id: str, sandbox: str, msn_id: str = ""
) -> str:
    """The id of a sandbox's LOCAL DOMAIN, under whichever name it is stored.

    One function so the six readers of the local domain cannot disagree about what it is
    called while the 2026-08-20 rename crosses the corpus. Canonical first, so a sandbox
    that somehow held both would resolve to the current one rather than to whichever the
    catalog yielded.
    """
    from micyte.core.instance_baseline import LOCAL_DOMAIN_NAMES

    for name in LOCAL_DOMAIN_NAMES:
        found = _document_named(
            store, tenant_id=tenant_id, sandbox=sandbox, name=name, msn_id=msn_id)
        if found:
            return found
    return ""


__all__ = ["MAX_RENDERED_ROWS", "SCHEMA", "build_viewscope_payload", "read_document",
           "rows_for_archetype", "viewscope_pane"]
