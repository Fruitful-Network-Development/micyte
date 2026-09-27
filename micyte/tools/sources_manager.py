"""``sources_manager`` — what this sandbox reads from other sandboxes, and whether it still can.

A sandbox is isolated: anything it needs from another sandbox must be **declared** in its
``sources`` manifest, one row per document, each pinning that document's content hash. That
relationship has been real in the data since the mycelium-network work and invisible in the
interface ever since — an operator could not see what a sandbox declared, could not tell a
current pin from one that had drifted, and had no way to change either without a script.

This is that surface. It shows every declared source with a verdict:

* **fresh** — the document is exactly what the row pinned;
* **stale** — the document changed and nobody re-pinned the row. A fault with a mechanical
  fix, so the row offers to re-pin;
* **missing** — the declared document is gone. The fix is a decision (retire the row, or
  republish the document), so the row offers removal and nothing else;
* **unverifiable** — the row pins nothing, or its kind names no known hash family.

It also shows what the manifest does NOT declare: the documents available in the sandboxes it
already references, each addable in one click. Reporting only the rows would repeat the defect
the SAMRAS structure viewer had — a surface that iterates a list can never show what the list
is missing, which is how the registrar's lcl showed 53 of its 66 nodes with nothing anywhere
saying so.

A CORE tool: it is about the sandbox, not about a document in focus, so it is reachable with
nothing selected and supplies its own context. Verification runs at ``verify=True`` here
because an operator asking "is this current?" is exactly the question worth paying for; the
hot paths that merely READ through the manifest resolve without it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core.document_naming import parse_canonical_document_id
from micyte.core.sources import (
    MANIFEST_DOCUMENT,
    SOURCE_FAULTS,
    resolve_sources,
)
from micyte.ports.datum_write_policy import DeclaredWrite
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._archetype import read_sandbox_catalog
from ._registry import register
from ._shared.utilities import as_text as _as_text

TOOL_ID = "sources_manager"
CONTAINER = "sources_panel"
_SCHEMA = "mycite.v2.portal.workbench.tool.sources_manager.v1"
_TENANT_DEFAULT = "fnd"

#: The registrar's manifest predates the reserved name; every other sandbox uses ``sources``.
LEGACY_MANIFESTS = {"registrar": "network_sources"}


def manifest_name_for(sandbox: str) -> str:
    return LEGACY_MANIFESTS.get(sandbox, MANIFEST_DOCUMENT)


def _notice(message: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "tool_id": TOOL_ID, "container": CONTAINER, "notice": message}


def build_sources_payload(
    documents: list[Any], *, sandbox: str, verify: bool = True, msn: str = "",
) -> dict[str, Any]:
    """Pure: the panel's payload from documents already read.

    ``msn`` says WHOSE manifest and log this is. Eight instances each hold a sandbox
    called ``system``; keyed on the name alone, whichever instance's log the catalog
    lists last answers for all of them, and an operator reads another instance's pins
    as their own (the 2026-08-17 manifest collapse, again, for the log).
    """
    if not sandbox:
        return _notice("no sandbox in focus, so there are no sources to show")

    index = None
    if verify:
        # Only the bitstream family needs it, but building it once is cheaper than
        # deciding per row whether this manifest happens to contain one.
        try:
            from micyte.core.mss.document_adapter import build_catalog_index

            index = build_catalog_index_from(documents, build_catalog_index)
        except Exception:
            index = None

    resolution = resolve_sources(documents, sandbox=sandbox, msn=msn,
                                 manifest_name=manifest_name_for(sandbox),
                                 verify=verify, mss_index=index)

    rows = [{
        "address": resolved.row.address,
        "declared_name": resolved.row.declared_name,
        "sandbox": resolved.row.sandbox,
        "document_name": resolved.row.document_name,
        "kind": resolved.row.kind,
        "hash_family": resolved.row.hash_family,
        "recorded_hash": resolved.row.recorded_hash,
        "status": resolved.status,
        "detail": resolved.detail,
        "is_fault": resolved.is_fault,
        # WHERE the pin lives. A manifest row's address is in the `sources` document; a
        # local-domain pin's is a definition row in the log (`4-4-N`, since 2026-09-08).
        # The surface says which, because the two are re-pinned by different writers.
        "pinned_in": ("local_domain"
                      if resolved.row.address.rsplit("-", 1)[0] in ("4-3", "4-4")
                      else "manifest"),
        # A stale row can be re-pinned mechanically; a missing one cannot, because
        # there is nothing to re-pin it to. Wherever the pin lives: the writer's
        # `repin_source` rewrites a manifest row's `rf.3-1-12` or a log pin's hash cell
        # in place, and the surface routes both through the one button.
        "can_repin": resolved.status in SOURCE_FAULTS or resolved.status == "unverifiable",
    } for resolved in resolution.sources]

    manifest_id = ""
    for document in documents:
        try:
            parsed = parse_canonical_document_id(_as_text(document.document_id))
        except Exception:
            continue
        if parsed.sandbox == sandbox and parsed.name == manifest_name_for(sandbox):
            manifest_id = _as_text(document.document_id)
            break

    return {
        "schema": _SCHEMA,
        "tool_id": TOOL_ID,
        "container": CONTAINER,
        "sandbox_id": sandbox,
        "manifest_document": manifest_name_for(sandbox),
        "manifest_document_id": manifest_id,
        "manifest_present": resolution.manifest_present,
        "rows": rows,
        # Addable: present in a sandbox this manifest already references, undeclared here.
        "undeclared": list(resolution.undeclared),
        "coverage": resolution.coverage(),
        "verified": verify,
    }


def build_catalog_index_from(documents: list[Any], builder: Any) -> Any:
    """``build_catalog_index`` takes a catalog, not a document list.

    The panel is handed documents (so it stays testable without a store), so wrap them
    in the minimal shape the builder reads rather than re-reading the store.
    """
    class _Catalog:
        def __init__(self, docs: list[Any]) -> None:
            self.documents = docs
            self.tenant_id = _TENANT_DEFAULT

    return builder(_Catalog(documents))


class SourcesManagerViewer:
    """The sandbox's declared cross-sandbox reads, with verdicts and configuration."""

    tool_id = TOOL_ID
    writes = (
        DeclaredWrite(document_kind="sources", action="add_source"),
        DeclaredWrite(document_kind="sources", action="remove_source"),
        DeclaredWrite(document_kind="sources", action="repin_source"),
        # ON THE TREE, for a sandbox that holds no manifest at all — every sandbox has a
        # sources branch, and until 2026-09-12 only `apply_convention` ever wrote a pin
        # into one. "Bind a taxonomy source first" is a refusal two writers hand out; this
        # is the act it names.
        DeclaredWrite(document_kind="lcl_domain", action="pin_document"),
    )
    label = "Sources"
    # UI copy: the rail hover, one sentence (the could-declare-but-does-not half
    # is the surface's own content, not the tooltip's).
    summary = "What this sandbox reads from other sandboxes, and whether each pin still matches."
    route = WORKBENCH_UI_TOOL_ROUTE
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    # Demoted from the rail (calendar-only rail, 2026-08-16): sources are a fact
    # about the SANDBOX in view, so they show as the control panel's Sources
    # section on every workbench render; its "Manage sources" opens this tool in
    # the workbench (?tool=sources_manager).
    core = False
    #: Follows the instance switcher: sources are a property of whichever sandbox is open.

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str,
        document_id: str,
        datum_address: str,
        extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del datum_address
        documents, err = read_sandbox_catalog(authority_db_file, tenant_id=_TENANT_DEFAULT)
        if err:
            return _notice(err)
        sandbox = _as_text(sandbox_id)
        if not sandbox and document_id:
            try:
                sandbox = _as_text(parse_canonical_document_id(_as_text(document_id)).sandbox)
            except Exception:
                sandbox = ""
        from micyte.core.instance_scope import resolve_msn

        return build_sources_payload(list(documents), sandbox=sandbox, msn=resolve_msn())


register(SourcesManagerViewer())
