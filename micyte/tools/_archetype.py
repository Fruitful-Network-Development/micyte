"""Shared archetype recognition + tool↔document resolution for WorkbenchTools.

Single-sources the "does this document match this tool?" question used by both the
palette eligibility runtime and the tools that resolve a sandbox-singleton document
(farm_profile, contracts). Resolving by archetype — never a hardcoded document id —
is the TASK-2026-06-02-008 principle; this module is where it lives.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from micyte.core.datum_ops import field_registry as _field_registry
from micyte.core.datum_ops.refs import NODE_REF_MARKERS as _NODE_ID_MARKERS
from micyte.core.instance_scope import active_instance_msn as _active_msn
from micyte.core.instances import default_farm_sandbox

from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head

#: The coordinate marker, PER NAMESPACE. It was a single literal — ``rf.3-1-3``, the FARM
#: numbering — which meant the scan below found the two farm profiles and none of the 469
#: registrar boundaries, whose coordinate is ``rf.3-1-1``. Measured: 2 documents where 471
#: hold geometry, so every tool declaring `hops_geospatial_filament` was ineligible for
#: 99.6% of the geometry in the store.
#:
#: Fixed together with `datum_resolve.resolve_coordinate`, which had the same blindness one
#: layer down. Widening one alone would have offered four tools against rings they cannot
#: decode, which is worse than not offering them.
_HOPS_COORD_MARKER = "rf.3-1-3"


def _coordinate_markers(sandbox: str) -> set[str]:
    """The marker that means `coordinate` HERE — the sandbox's own, or the farm literal.

    The literal is a fallback for a sandbox the decoder ring does not know, NOT an addition
    to every namespace. Keeping it everywhere would put the overloading bug back one door
    along: `rf.3-1-3` is `title` in the registrar, so three of them in a family-4 row is
    three titles, and calling that a polygon ring is the same class of wrong answer this
    fix exists to remove.
    """
    if sandbox:
        try:
            return {_field_registry.marker(sandbox, "coordinate")}
        except KeyError:
            pass
    return {_HOPS_COORD_MARKER}


def document_sandbox(doc: Any) -> str:
    """Sandbox token from a canonical id ``lv.<msn>.<sandbox>.<name>.<hash>``."""
    parts = _as_text(getattr(doc, "document_id", "")).split(".")
    return parts[2] if len(parts) > 4 else ""


#: Legacy scan token -> the derived archetypes that mean the same thing.
#:
#: Measured against the live corpus by
#: ``evidence/archetype-viewscope/phase2/scan_parity.py``:
#:
#: * ``samras_taxonomy`` is **not one archetype**. The scan below keys on
#:   ``NODE_REF_MARKERS`` as a set, with no namespace, so it cannot tell a txa node from an
#:   lcl node — ``rf.3-1-1`` is ``txa_id`` in taxonomy and ``coordinate`` in the registrar,
#:   and ``registrar/lcl`` defines lcl classes, not taxa. The registry separates them; the
#:   union reproduces the scan's 9 documents and adds ``<a_farm>/object_profiles``, which is
#:   genuinely classification-shaped.
#: * ``hops_geospatial_filament`` now has EXACT parity — 471 documents both ways — since
#:   the scan resolves its coordinate marker through the decoder ring instead of the
#:   ``rf.3-1-3`` literal. It found 2 before, and the 469 it missed were the registrar
#:   boundaries carrying ``rf.3-1-1``. `datum_resolve.resolve_coordinate` was corrected in
#:   the same commit, because widening the scan alone would have offered four tools against
#:   rings they still could not decode.
#:
#: The scans still run and the registry is unioned in when a caller supplies one. Keeping
#: both is not indecision: the aliases are what let a tool keep declaring
#: `applies_to_archetype` while the registry becomes the thing that answers.
ARCHETYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "samras_taxonomy": ("taxon_record", "class_record"),
    "hops_geospatial_filament": ("geospatial_polygon",),
}


def document_archetypes(doc: Any, *, registry: Any = None) -> set[str]:
    """Recognize a document's tool-eligibility archetypes by ARCHETYPE/SHAPE,
    never by a hardcoded document id (TASK-2026-06-02-008).

    ``registry`` is an optional :class:`micyte.core.archetypes.ArchetypeRegistry`. When
    given, the archetypes the document's rows match are unioned in, so a document is
    described by the library rather than by the two shapes this module happens to know.
    Omitted — which is every caller today — the result is exactly what it always was.

    Sources:
      * metadata ``datum_template_archetype`` / ``samras_family``;
      * the ``schema`` / ``datum_template_schema`` token (so schema-typed docs —
        contracts/invoices/taxonomy — are addressable by their schema);
      * STRUCTURAL scans (shape, never a hand-stamped token — the convention lenses use
        via hyphae). Two shapes are recognized:
          - ``hops_geospatial_filament``: a family-4 ring row (``4-*``) carrying at least
            THREE coordinate markers — a real polygon ring, where "coordinate" is resolved
            per namespace (``rf.3-1-1`` in the registrar, ``rf.3-1-3`` in a farm). The
            bare-single form is rejected: the marker is OVERLOADED (it also appears once as
            a node-reference in entity docs and as an encoded value), so "≥3 coords in one
            family-4 row" is what actually identifies a HOPS filament.
          - ``samras_taxonomy``: a ``4-2-*`` row whose head is a titled id-pair
            definition (``[addr, <node-ref marker>, node, <title marker>, title]``,
            node-ref per ``datum_ops.refs.NODE_REF_MARKERS`` — rf.3-1-1/3-1-5 in
            agro_erp, rf.3-1-13 in mycelium_network) — i.e. the doc *defines*
            taxonomy nodes. This is what makes txa recognizable WITHOUT stamping it
            (txa carries no metadata archetype; lcl does — both have the shape).
    """
    archetypes: set[str] = set()
    coordinate_markers = _coordinate_markers(document_sandbox(doc))
    metadata = getattr(doc, "document_metadata", None)
    if isinstance(metadata, dict):
        for key in ("datum_template_archetype", "samras_family", "schema", "datum_template_schema"):
            token = _as_text(metadata.get(key))
            if token:
                archetypes.add(token)
    found_hops = False
    found_taxonomy = False
    for row in getattr(doc, "rows", ()) or ():
        addr = _as_text(getattr(row, "datum_address", ""))
        head = _row_head(row)
        if not found_hops and addr.startswith("4-") and (
            sum(1 for tok in head if _as_text(tok) in coordinate_markers) >= 3
        ):
            archetypes.add("hops_geospatial_filament")
            found_hops = True
        if (
            not found_taxonomy
            and addr.startswith(("4-2-", "4-3-", "4-4-"))
            and len(head) >= 5
            and _as_text(head[1]).lower() in _NODE_ID_MARKERS
        ):
            # Require a real title blob (≥8 binary bits) so this matches a genuine titled
            # definition (txa/lcl), not a bare 4-2 reference row that merely reuses the
            # rf.3-1-1 marker (matches datum_ops `is_title_blob` / `_is_definition_head`).
            # `4-3-*` too: a local domain node that denotes a document keeps its
            # definition row in that family, and a tree made entirely of them is still a
            # SAMRAS taxonomy (micyte.core.datum_ops.local_domain).
            title = _as_text(head[4])
            if len(title) >= 8 and set(title) <= {"0", "1"}:
                archetypes.add("samras_taxonomy")
                found_taxonomy = True
        if found_hops and found_taxonomy:
            break
    if registry is not None:
        archetypes.update(registry.archetypes_for(doc))
    return archetypes


def tool_matches_document(tool: Any, doc: Any) -> bool:
    """True when ``doc`` matches the tool's applies_to_archetype / source_kind.

    A tool with no applies_to_* lists is universal (matches every doc) — same
    semantics the palette already uses for the menubar search.
    """
    tool_archetypes = set(getattr(tool, "applies_to_archetype", ()) or ())
    tool_source_kinds = set(getattr(tool, "applies_to_source_kind", ()) or ())
    if not tool_archetypes and not tool_source_kinds:
        return True
    if tool_archetypes & document_archetypes(doc):
        return True
    source_kind = _as_text(getattr(doc, "source_kind", ""))
    return bool(source_kind and source_kind in tool_source_kinds)


def resolve_tool_sandbox(sandbox_id: Any, *, doc: Any = None, docs: Any = ()) -> str:
    """The sandbox a panel should render against, without naming one.

    In order: what the caller asked for; the sandbox of a document already
    resolved (it knows its own); the store's first farm by shape. ``""`` when
    nothing resolves, and the caller must then error rather than render.

    Every tool used to spell this `sandbox_id or "<a_farm_sandbox>"`. That is not
    a default, it is a guess — and since the instance model landed it is a guess
    across an instance boundary: a request that omitted the sandbox was answered
    with one particular farm's data. Callers of these panels do pass a sandbox
    today, so this is about what happens when one stops.
    """
    token = _as_text(sandbox_id)
    if token:
        return token
    if doc is not None:
        owned = document_sandbox(doc)
        if owned:
            return owned
    return default_farm_sandbox(list(docs or ())) or ""


def scoped_to_instance(documents: Any, *, msn_id: str = "") -> list[Any]:
    """The catalog as ONE instance sees it: its own core sandbox, plus every shared one.

    Twenty tools read the whole catalog and then filter it with ``parsed.sandbox ==
    sandbox``. That was decisive while a sandbox NAME identified one sandbox. Once every
    instance keeps its core sandbox under the name ``system``, the same filter returns four
    instances' documents, and each tool then picks one by position — which is how the client instance's
    portal came to render one farm's ``farm_profile``, its 473 ``sources`` and somebody
    else's ``object_profiles``, all reported as its own.

    Fixing twenty filters would be twenty chances to miss one. Scoping the catalog they all
    read makes them right by construction, and it is the same rule the store applies to a
    sandbox read:

    * **Disambiguate, never narrow.** A sandbox name that only ONE instance holds passes
      through untouched — so a tool scoped to the client instance still reads ``registrar``, ``taxonomy``,
      ``agnet`` and ``archetype``, which are FND's and which everything depends on.
    * **Only a name several instances hold is filtered**, and then to the scoped instance.
    * **No scope, no filtering.** A script or a test outside a request sees the whole
      catalog, exactly as before.

    One pass over the catalog's ids; nothing is parsed or read.
    """
    scoped = _as_text(msn_id) or _active_msn()
    if not scoped:
        return list(documents or ())
    holders: dict[str, set[str]] = {}
    listed = list(documents or ())
    for doc in listed:
        holders.setdefault(document_sandbox(doc), set()).add(_document_msn(doc))
    return [
        doc for doc in listed
        if len(holders.get(document_sandbox(doc), ())) <= 1
        or _document_msn(doc) == scoped
    ]


#: ONE sandbox's documents, remembered per store version. Keyed on the store's identity
#: (resolved path + mtime_ns), the tenant, the sandbox and the msn scope the read resolved
#: under. A write is a new mtime and a new key; the superseded key for the same store and
#: sandbox is dropped on insert, and so is a key whose store no longer exists — the rule
#: `_GLOBAL_CATALOG_CACHE` follows. Two entries: the live process asks for `registrar` and,
#: rarely, one more. The registrar is 566 documents / 46 MB of JSON on the live store;
#: parsing it per render is ~1.5 s, so the two surfaces that read it (the network map, the
#: profile's registrar face) share one parse until the store changes. The documents are
#: dataclasses with tuple rows; readers do not mutate them.
_SANDBOX_DOCS_LOCK = threading.Lock()
_SANDBOX_DOCS: OrderedDict[tuple[str, int, str, str, str], tuple[Any, ...]] = OrderedDict()
_SANDBOX_DOCS_MAX = 2


def _store_identity(authority_db_file: Any) -> tuple[str, int]:
    path = Path(str(authority_db_file))
    try:
        return (str(path.resolve()), int(path.stat().st_mtime_ns))
    except OSError:
        return (str(path), 0)


def _remember_sandbox_docs(key: tuple[str, int, str, str, str], docs: tuple[Any, ...]) -> None:
    with _SANDBOX_DOCS_LOCK:
        for stale in [k for k in _SANDBOX_DOCS
                      if (k[0] == key[0] and k[2:] == key[2:] and k[1] != key[1])
                      or not Path(k[0]).exists()]:
            _SANDBOX_DOCS.pop(stale, None)
        _SANDBOX_DOCS[key] = docs
        _SANDBOX_DOCS.move_to_end(key)
        while len(_SANDBOX_DOCS) > _SANDBOX_DOCS_MAX:
            _SANDBOX_DOCS.popitem(last=False)


def read_sandbox_catalog(
    authority_db_file: Any, *, tenant_id: str = "fnd", msn_id: str = "", sandbox: str = ""
) -> tuple[list[Any], str]:
    """Open the authority store and return ``(documents, error)``.

    Single-sources the db-guard → adapter → ``read_authoritative_datum_documents``
    preamble that was copy-pasted across every WorkbenchTool. ``error`` is ``""`` on
    success; a non-empty string (the message) on failure, with an empty ``documents``
    list. Lazy imports keep this leaf module free of an adapter import cycle.

    The result is scoped to the requesting instance — see :func:`scoped_to_instance` for
    what that does and, more importantly, what it deliberately does not.

    ``sandbox`` names ONE sandbox to read, through the store's per-document door
    (``read_documents_by_sandbox``) rather than the whole-tenant catalog blob — the
    138 MB parse that costs the process ~290 MiB to look at one sandbox's share of it. A
    tool that knows which sandbox it draws (the network map draws ``registrar``; so does
    the profile's registrar face) names it and pays for that sandbox alone, once per store
    version (``_SANDBOX_DOCS``). Without it, the read is what it always was.
    """
    if authority_db_file is None:
        return [], "authority database not configured"
    if _as_text(sandbox):
        return _read_one_sandbox(authority_db_file, tenant_id=tenant_id, msn_id=msn_id,
                                 sandbox=_as_text(sandbox))
    try:
        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter
        from micyte.ports.datum_store import AuthoritativeDatumDocumentRequest

        store = SqliteSystemDatumStoreAdapter(authority_db_file)
        catalog = store.read_authoritative_datum_documents(
            AuthoritativeDatumDocumentRequest(tenant_id=tenant_id)
        )
    except Exception as exc:  # pragma: no cover — defensive
        return [], f"datum store unavailable: {exc}"
    return scoped_to_instance(getattr(catalog, "documents", ()) or (), msn_id=msn_id), ""


def read_sandboxes_catalog(
    authority_db_file: Any, *, tenant_id: str = "fnd", msn_id: str = "", sandboxes: Any = (),
) -> tuple[list[Any], str]:
    """``(documents, error)`` for a NAMED set of sandboxes — each through the per-sandbox
    door and its memo — for a tool that reads its own sandbox and one shared one (a farm's
    products beside the taxonomy). A blank name in the set means the whole catalog, as
    :func:`read_sandbox_catalog` with no sandbox does."""
    names = [_as_text(n) for n in (sandboxes or ())]
    if not names or not all(names):
        return read_sandbox_catalog(authority_db_file, tenant_id=tenant_id, msn_id=msn_id)
    out: list[Any] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        documents, error = read_sandbox_catalog(
            authority_db_file, tenant_id=tenant_id, msn_id=msn_id, sandbox=name)
        if error:
            return [], error
        out.extend(documents)
    return out, ""


def _read_one_sandbox(
    authority_db_file: Any, *, tenant_id: str, msn_id: str, sandbox: str
) -> tuple[list[Any], str]:
    scope = _as_text(msn_id) or _active_msn()
    store_path, store_mtime = _store_identity(authority_db_file)
    key = (store_path, store_mtime, _as_text(tenant_id), sandbox, scope)
    with _SANDBOX_DOCS_LOCK:
        hit = _SANDBOX_DOCS.get(key)
        if hit is not None:
            _SANDBOX_DOCS.move_to_end(key)
    if hit is not None:
        return list(hit), ""
    try:
        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

        store = SqliteSystemDatumStoreAdapter(authority_db_file)
        docs = tuple(store.read_documents_by_sandbox(
            tenant_id=tenant_id, sandbox=sandbox, msn_id=msn_id))
    except Exception as exc:  # pragma: no cover — defensive
        return [], f"datum store unavailable: {exc}"
    # Remember only what the store still IS — a write between the stat and the read would
    # park the new content under the old version.
    if _store_identity(authority_db_file) == (store_path, store_mtime):
        _remember_sandbox_docs(key, docs)
    return list(docs), ""


def _document_name(doc: Any) -> str:
    """Authoritative short name from a canonical id ``lv.<msn>.<sandbox>.<name>.<hash>``."""
    parts = _as_text(getattr(doc, "document_id", "")).split(".")
    return parts[3] if len(parts) > 4 else ""


def _document_msn(doc: Any) -> str:
    """The msn segment of a canonical id ``lv.<msn>.<sandbox>.<name>.<hash>``."""
    parts = _as_text(getattr(doc, "document_id", "")).split(".")
    return parts[1] if len(parts) > 4 else ""


def find_local_domain(docs: Any, *, sandbox: str, msn_id: str = "") -> Any | None:
    """The sandbox's LOCAL DOMAIN document, under whichever name it is stored.

    One resolver, because seven readers looked it up by the literal ``"lcl"`` and every one
    of them fails the same silent way after the 2026-08-20 rename: `find_named_document`
    returns ``None``, `cached_index(None)` is an index of nothing, and the surface draws
    every label blank without raising. The SAMRAS tree did exactly that on the live portal
    — 35 nodes, right addresses, right previews, and `(undefined)` on every one.
    """
    from micyte.core.instance_baseline import LOCAL_DOMAIN_NAMES

    for name in LOCAL_DOMAIN_NAMES:
        found = find_named_document(docs, sandbox=sandbox, name=name, msn_id=msn_id)
        if found is not None:
            return found
    return None


def find_named_document(
    docs: Any, *, sandbox: str, name: str, msn_id: str = ""
) -> Any | None:
    """First doc of ``(msn, sandbox)`` named ``name`` (sandbox '' = any).

    Matches the doc's ``canonical_name`` OR its authoritative document-id name segment: the
    ex-``agro_erp`` farm docs (invoices/contracts/farm_profile/contacts) still carry the legacy
    full-id canonical_name ``lv.<msn>.agro_erp.<name>`` while their document-id name is the short
    ``<name>`` — matching either keeps the lookup working before a write normalizes the name.

    The msn half matters because a sandbox NAME stopped identifying one sandbox: every
    instance keeps its core sandbox under the name ``system``, so filtering on the name alone
    returns whichever instance's document happens to come first in the catalog. This is the
    widest shared lookup in the tools layer, which is why the scope is applied HERE rather
    than in each of its callers — explicit ``msn_id`` wins, else the request's instance.
    """
    from micyte.core.instance_scope import active_instance_msn

    candidates = [
        doc for doc in docs
        if (_as_text(getattr(doc, "canonical_name", "")) == name or _document_name(doc) == name)
        and (not sandbox or document_sandbox(doc) == sandbox)
    ]
    if not candidates:
        return None
    # DISAMBIGUATE, never narrow. An explicit msn is a filter; the request scope is only a
    # tie-break, because it must not reach the SHARED sandboxes — a tool scoped to the client instance's
    # instance still reads `registrar`, which is FND's, to resolve a customer's name.
    # Filtering those by its msn is what turned its 43 jobs into none.
    wanted = _as_text(msn_id)
    if wanted:
        return next((d for d in candidates if _document_msn(d) == wanted), None)
    if len(candidates) == 1:
        return candidates[0]
    scoped = active_instance_msn()
    if scoped:
        # None, not `candidates[0]`. More than one candidate means the sandbox name is one
        # several instances hold, and under a scope "no candidate is mine" is the answer
        # "this instance does not hold it" — not "here is somebody else's". Falling back to
        # the first is what showed the client instance a farm_profile: it has none, so the tool
        # rendered the farm instance's farm on its portal and reported it as its own.
        return next((d for d in candidates if _document_msn(d) == scoped), None)
    return candidates[0]


def find_anchor(docs: Any, *, sandbox: str, msn_id: str = "") -> Any | None:
    """A sandbox's ANCHOR, whatever it is called.

    `anchor` in most sandboxes and `anthology` in a system sandbox — both reserved for
    anchors and for nothing else, per the naming contract. Fifteen call sites asked for the
    literal `"anchor"`, which was right while that was the only name one could have; the
    moment an instance's documents move into `system` its anchor is `anthology` and every
    one of them finds nothing, so the tool reports the sandbox as having no clock, no
    namespace, and no fields.
    """
    from micyte.core.document_naming import ANCHOR_DOCUMENT_NAMES

    for name in sorted(ANCHOR_DOCUMENT_NAMES):
        found = find_named_document(docs, sandbox=sandbox, name=name, msn_id=msn_id)
        if found is not None:
            return found
    return None


def resolve_tool_document(
    docs: Any,
    *,
    tool: Any,
    sandbox: str,
    document_id: str,
    canonical_name: str | None = None,
) -> Any | None:
    """Resolve the document a sandbox-singleton tool should render.

    Honors the selected document only when it actually matches the tool; otherwise
    falls back to the first sandbox document that matches (by archetype, or by
    ``canonical_name`` when given). This is the fix for the empty-render bug: the
    workbench auto-selects the first sandbox doc (e.g. the geometry-less ``anchor``),
    and a wrong-but-present selection must NOT win over the real target document.
    """
    document_id = _as_text(document_id)

    def _matches(doc: Any) -> bool:
        if tool_matches_document(tool, doc):
            return True
        return bool(canonical_name and _as_text(getattr(doc, "canonical_name", "")) == canonical_name)

    selected = (
        next((d for d in docs if _as_text(getattr(d, "document_id", "")) == document_id), None)
        if document_id
        else None
    )
    if selected is not None and (not sandbox or document_sandbox(selected) == sandbox):
        # When a canonical_name is given it is AUTHORITATIVE: honor the selection only
        # if the selected doc IS that named doc; otherwise ignore it and fall through to
        # name-first resolution. (Without this, a selected doc that merely shares the
        # tool's archetype — e.g. lcl selected while opening the txa-named tool, both
        # `samras_taxonomy` — would wrongly win over the named doc.) The sandbox guard
        # keeps a selection from a DIFFERENT sandbox that happens to share the
        # canonical_name/archetype from winning (reachable when the workbench auto-selects
        # a foreign-sandbox doc); every other resolution path below is sandbox-scoped, so
        # the selected branch must be too.
        if canonical_name:
            if _as_text(getattr(selected, "canonical_name", "")) == canonical_name:
                return selected
        elif _matches(selected):
            return selected
    # Prefer an exact canonical_name match in the sandbox BEFORE archetype matching.
    # Several agro_erp docs share an archetype (txa AND lcl are both `samras_taxonomy`),
    # so archetype-first would return whichever iterates first and mis-resolve a named
    # tool (e.g. lcl_structure getting txa). When a canonical_name is given it is
    # authoritative; archetype is only the fallback for unnamed/by-shape tools.
    if canonical_name:
        for doc in docs:
            if sandbox and document_sandbox(doc) != sandbox:
                continue
            if _as_text(getattr(doc, "canonical_name", "")) == canonical_name:
                return doc
    for doc in docs:
        if sandbox and document_sandbox(doc) != sandbox:
            continue
        if tool_matches_document(tool, doc):
            return doc
    return None


__all__ = [
    "document_archetypes",
    "document_sandbox",
    "find_named_document",
    "read_sandbox_catalog",
    "read_sandboxes_catalog",
    "resolve_tool_document",
    "tool_matches_document",
]
