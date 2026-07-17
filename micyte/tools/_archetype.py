"""Shared archetype recognition + tool↔document resolution for WorkbenchTools.

Single-sources the "does this document match this tool?" question used by both the
palette eligibility runtime and the tools that resolve a sandbox-singleton document
(farm_profile, contracts). Resolving by archetype — never a hardcoded document id —
is the TASK-2026-06-02-008 principle; this module is where it lives.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops.refs import NODE_REF_MARKERS as _NODE_ID_MARKERS
from micyte.core.instances import default_farm_sandbox

from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head

_HOPS_COORD_MARKER = "rf.3-1-3"


def document_sandbox(doc: Any) -> str:
    """Sandbox token from a canonical id ``lv.<msn>.<sandbox>.<name>.<hash>``."""
    parts = _as_text(getattr(doc, "document_id", "")).split(".")
    return parts[2] if len(parts) > 4 else ""


def document_archetypes(doc: Any) -> set[str]:
    """Recognize a document's tool-eligibility archetypes by ARCHETYPE/SHAPE,
    never by a hardcoded document id (TASK-2026-06-02-008).

    Sources:
      * metadata ``datum_template_archetype`` / ``samras_family``;
      * the ``schema`` / ``datum_template_schema`` token (so schema-typed docs —
        contracts/invoices/taxonomy — are addressable by their schema);
      * STRUCTURAL scans (shape, never a hand-stamped token — the convention lenses use
        via hyphae). Two shapes are recognized:
          - ``hops_geospatial_filament``: a family-4 ring row (``4-*``) carrying at least
            THREE rf.3-1-3 coordinate markers — a real polygon ring. The bare-single
            rf.3-1-3 form is rejected: that marker is OVERLOADED (it also appears once as a
            node-reference in entity docs and as an encoded value), so "≥3 coords in one
            family-4 row" is what actually identifies a HOPS filament (e.g. farm_profile).
          - ``samras_taxonomy``: a ``4-2-*`` row whose head is a titled id-pair
            definition (``[addr, <node-ref marker>, node, <title marker>, title]``,
            node-ref per ``datum_ops.refs.NODE_REF_MARKERS`` — rf.3-1-1/3-1-5 in
            agro_erp, rf.3-1-13 in mycelium_network) — i.e. the doc *defines*
            taxonomy nodes. This is what makes txa recognizable WITHOUT stamping it
            (txa carries no metadata archetype; lcl does — both have the shape).
    """
    archetypes: set[str] = set()
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
            sum(1 for tok in head if _as_text(tok) == _HOPS_COORD_MARKER) >= 3
        ):
            archetypes.add("hops_geospatial_filament")
            found_hops = True
        if (
            not found_taxonomy
            and addr.startswith("4-2-")
            and len(head) >= 5
            and _as_text(head[1]).lower() in _NODE_ID_MARKERS
        ):
            # Require a real title blob (≥8 binary bits) so this matches a genuine titled
            # definition (txa/lcl), not a bare 4-2 reference row that merely reuses the
            # rf.3-1-1 marker (matches datum_ops `is_title_blob` / `_is_definition_head`).
            title = _as_text(head[4])
            if len(title) >= 8 and set(title) <= {"0", "1"}:
                archetypes.add("samras_taxonomy")
                found_taxonomy = True
        if found_hops and found_taxonomy:
            break
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

    Every tool used to spell this `sandbox_id or "trapp_family_farm"`. That is not
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


def read_sandbox_catalog(authority_db_file: Any, *, tenant_id: str = "fnd") -> tuple[list[Any], str]:
    """Open the authority store and return ``(documents, error)``.

    Single-sources the db-guard → adapter → ``read_authoritative_datum_documents``
    preamble that was copy-pasted across every WorkbenchTool. ``error`` is ``""`` on
    success; a non-empty string (the message) on failure, with an empty ``documents``
    list. Lazy imports keep this leaf module free of an adapter import cycle.
    """
    if authority_db_file is None:
        return [], "authority database not configured"
    try:
        from micyte.adapters.sql import SqliteSystemDatumStoreAdapter
        from micyte.ports.datum_store import AuthoritativeDatumDocumentRequest

        store = SqliteSystemDatumStoreAdapter(authority_db_file)
        catalog = store.read_authoritative_datum_documents(
            AuthoritativeDatumDocumentRequest(tenant_id=tenant_id)
        )
    except Exception as exc:  # pragma: no cover — defensive
        return [], f"datum store unavailable: {exc}"
    return list(getattr(catalog, "documents", ()) or ()), ""


def _document_name(doc: Any) -> str:
    """Authoritative short name from a canonical id ``lv.<msn>.<sandbox>.<name>.<hash>``."""
    parts = _as_text(getattr(doc, "document_id", "")).split(".")
    return parts[3] if len(parts) > 4 else ""


def find_named_document(docs: Any, *, sandbox: str, name: str) -> Any | None:
    """First doc in ``sandbox`` named ``name`` (sandbox '' = any).

    Matches the doc's ``canonical_name`` OR its authoritative document-id name segment: the
    ex-``agro_erp`` trapp docs (invoices/contracts/farm_profile/contacts) still carry the legacy
    full-id canonical_name ``lv.<msn>.agro_erp.<name>`` while their document-id name is the short
    ``<name>`` — matching either keeps the lookup working before a write normalizes the name."""
    for doc in docs:
        if _as_text(getattr(doc, "canonical_name", "")) == name or _document_name(doc) == name:
            if not sandbox or document_sandbox(doc) == sandbox:
                return doc
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
    "resolve_tool_document",
    "tool_matches_document",
]
