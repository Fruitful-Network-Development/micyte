"""Product-document viewer — the first content-resolving Plan-v2 visualizer.

Renders an agro_erp ``product_profiles`` document (value-group-9 PAIRS rows) as a
human-readable product table: each row's ``product_id`` (an LCL product-leaf node
address) is resolved to the product NAME via a cross-document index over the
``lcl`` document, the ``taxonomy_id`` is resolved to its taxon title via ``txa``,
and the four classification references + the two unit magnitudes (gestation in
seconds, spacing in centimetres) are surfaced with their field labels.

This is the concrete proof of the "tools = a library of UI objects that view the
visualized target datum" convention: it composes a panel payload purely from the
sandbox's own documents, including the **cross-document** product_id→name lookup
that the document-local recognition layer does not perform. The resolver
(:class:`~micyte.core.datum_ops.datum_resolve.NameIndex`) is memoized per (document_id) so the 1.6k-entry binary
decode is not repeated per render.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core.datum_ops.datum_resolve import NameIndex, cached_index, decode_label
from micyte.core.datum_ops.units import parse_quantity
from micyte.ports.datum_store import (
    AuthoritativeDatumDocument,
)
from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._archetype import document_sandbox, find_local_domain, read_sandbox_catalog
from ._requirements import FARM
from ._shared.utilities import as_text as _as_text

_TENANT_DEFAULT = "fnd"
_SCHEMA = "mycite.v2.portal.workbench.tool.product_document.v1"

# Field labels for the 9 value-group pairs, in head order. Mirrors the
# product_profile.yaml value_group_reference_design (kept in sync there).
_PAIR_FIELDS: tuple[str, ...] = (
    "product_id",
    "taxonomy_id",
    "rotation_group",
    "propagule",
    "genesis",
    "ownership",
    "raunkiaerality",
    "gestation",
    "spacing",
    "singular_unit_weight",
    "shelf_life",         # vg-11: seconds (unit_ref 2-1-1) — receival + shelf_life = days-until-bad
    "propagule_density",  # vg-12: "N units/g" — mass × density = total unit count
)
# Which fields resolve against which sibling document's node→label index.
_LCL_FIELDS = {"product_id", "rotation_group", "propagule", "genesis", "ownership", "raunkiaerality"}
_TXA_FIELDS = {"taxonomy_id"}
# Unit-magnitude scalars: gestation is seconds (unit_ref 2-1-1), spacing is cm (2-1-3).
_UNIT_FIELDS = {"gestation", "spacing"}
# Nominal (136-bit ASCII) fields → decode to text (e.g. "0.07 g").
_NOMINAL_FIELDS = {"singular_unit_weight", "propagule_density"}
_SECONDS_PER_DAY = 86400
_SECOND_UNIT_REF = "2-1-1"  # `second` unit abstraction (gestation + shelf_life magnitudes)
#: The shortest head this positional reader can honestly parse: the template's NINE pairs
#: plus the row's own address. A `product_profiles` document may hold `offering_record`
#: rows too — that is what FND's `agnet.product_profiles` is, all 217 of them, and since
#: 2026-09-02 it is what `ledger_write_runtime.add_product` appends for a client. Those
#: rows carry four pairs and agree with this shape on the first two (`rf.3-1-5` product,
#: `rf.3-1-1` taxon) and diverge on the third, so read positionally an `offering_record`'s
#: title babelette lands under `rotation_group` and its `hyphae_ref` under `propagule` —
#: the "two subtly different row shapes in one document" failure `record_spec` names.
#: A reader of a fixed positional format cannot parse a head too short to carry it, so it
#: skips one rather than labelling its cells with the wrong field names. The catalog reads
#: the same document by SHAPE (`ledger_books.product_rows`), which is the question that
#: actually separates them.
_MIN_AGRO_ERP_HEAD = 2 * 9 + 1


def _shelf_nominal_to_seconds(magnitude: str) -> int:
    """Legacy shelf_life nominal (136-bit "N days") → seconds; 0 when it can't be parsed."""
    try:
        days, _unit = parse_quantity(decode_label(magnitude))
        return round(days) * _SECONDS_PER_DAY
    except Exception:
        return 0


def _product_row_prefix(rows: list[Any]) -> str:
    """The value-group row family of the product rows: the highest ``4-K-`` present.

    Product_profiles has grown by trailing appends (vg-9 → vg-10 unit-weight → vg-12
    shelf-life/density), each re-familying every row. Following the highest 4-K present
    keeps the reader working across the migration without a code/data deploy-order hazard.
    """
    best = 0
    for r in rows:
        parts = _as_text(getattr(r, "datum_address", "")).split("-")
        if len(parts) >= 2 and parts[0] == "4":
            try:
                best = max(best, int(parts[1]))
            except ValueError:
                pass
    return f"4-{best}-" if best else "4-10-"


def _rows(document: AuthoritativeDatumDocument) -> list[Any]:
    out = []
    for r in getattr(document, "rows", ()) or ():
        if hasattr(r, "datum_address"):
            out.append(r)
        elif isinstance(r, dict):
            out.append(type("Row", (), {"datum_address": r.get("datum_address", ""), "raw": r.get("raw")})())
    return out


class ProductDocumentViewer:
    """Resolve an agro_erp ``product_profiles`` doc into a labelled product table."""

    tool_id = "product_document"
    label = "Product Document Viewer"
    summary = "Products with names, taxonomy, classification and unit magnitudes resolved from the sandbox."
    route = WORKBENCH_UI_TOOL_ROUTE
    #: Scoped to the instance kind this belongs to — see tools/_requirements.
    requires = FARM

    applies_to_archetype: tuple[str, ...] = ("agro_erp_product_profile_row",)
    # Intentionally NOT source-kind-matched: the product viewer is specific to the
    # product_profile archetype, not to every sandbox_source document. (The match
    # predicate ORs archetype/source_kind, so declaring sandbox_source here would
    # make the viewer eligible for anchor/txa/lcl too.)
    applies_to_source_kind: tuple[str, ...] = ()

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str,
        document_id: str,
        datum_address: str,
    ) -> dict[str, Any]:
        docs, err = read_sandbox_catalog(authority_db_file, tenant_id=_TENANT_DEFAULT, sandbox=_as_text(sandbox_id))
        if err:
            return _error(err)
        # The sandbox is resolved BEFORE the document, and an absent one fails closed.
        # This used to scan the whole catalog for a matching document_id and only then
        # ask which sandbox to render against — so a document_id from another farm was
        # answered with that farm's rows, and the lcl/txa indexes below were built from
        # whichever sandbox the caller's token named. That is the cross-instance leak
        # DatumDocTool spells out (micyte/tools/_contract.py): "No sandbox -> fail
        # closed." The id belongs to the caller; the sandbox is the boundary, so the
        # boundary is checked first and the id is only honoured inside it.
        sandbox = _as_text(sandbox_id)
        if not sandbox:
            return _error("no sandbox specified")
        product_doc = next(
            (
                d
                for d in docs
                if _as_text(getattr(d, "document_id", "")) == _as_text(document_id)
                and document_sandbox(d) == sandbox
            ),
            None,
        )
        if product_doc is None:
            # fall back to the named product_profiles doc in the SAME sandbox
            product_doc = _find_named(docs, sandbox, "product_profiles")
        if product_doc is None:
            return _error("product_profiles document not found")

        lcl_index = cached_index(find_local_domain(docs, sandbox=sandbox))
        txa_index = cached_index(_find_named(docs, sandbox, "txa"))

        products = build_product_rows(product_doc, lcl_index=lcl_index, txa_index=txa_index)

        return {
            "schema": _SCHEMA,
            "sandbox_id": sandbox,
            "document_id": _as_text(getattr(product_doc, "document_id", "")),
            "selected_row_address": _as_text(datum_address),
            "columns": list(_PAIR_FIELDS),
            "product_count": len(products),
            "lcl_index_size": len(lcl_index),
            "products": products,
        }


def build_product_rows(
    product_doc: AuthoritativeDatumDocument,
    *,
    lcl_index: NameIndex,
    txa_index: NameIndex,
) -> list[dict[str, Any]]:
    """Resolve every ``4-9-*`` vg-9 row into a labelled product dict (pure)."""
    all_rows = _rows(product_doc)
    prefix = _product_row_prefix(all_rows)  # follows the current vg family (4-10-, 4-12-, …)
    products: list[dict[str, Any]] = []
    for row in all_rows:
        addr = _as_text(row.datum_address)
        if not addr.startswith(prefix):
            continue
        raw = row.raw
        if not (isinstance(raw, list) and raw and isinstance(raw[0], list)):
            continue
        head = raw[0]
        if len(head) < _MIN_AGRO_ERP_HEAD:
            continue
        product_name = ""
        if len(raw) > 1 and isinstance(raw[1], list) and raw[1]:
            product_name = _as_text(raw[1][0])
        fields: list[dict[str, Any]] = []
        # head = [addr, (ref, mag) x 9]; pair i -> _PAIR_FIELDS[i]
        for i, field in enumerate(_PAIR_FIELDS):
            mag_index = 2 + 2 * i
            if mag_index >= len(head):
                break
            magnitude = _as_text(head[mag_index])
            marker = _as_text(head[mag_index - 1])
            resolved = ""
            if field in _LCL_FIELDS:
                resolved = lcl_index.resolve(magnitude)
            elif field in _TXA_FIELDS:
                resolved = txa_index.resolve(magnitude)
            elif field == "shelf_life":
                # Seconds scalar (unit_ref 2-1-1); the legacy rf.3-1-7 "N days" nominal is
                # normalized to seconds so the reader is correct across the migration. Branch on
                # the MARKER (the nominal's 136-bit magnitude is all 0/1 digits, so magnitude
                # shape can't tell them apart).
                resolved = magnitude if marker == _SECOND_UNIT_REF else str(_shelf_nominal_to_seconds(magnitude))
            elif field in _NOMINAL_FIELDS:
                resolved = decode_label(magnitude)  # 136-bit ASCII nominal → "0.07 g"
            elif field in _UNIT_FIELDS:
                resolved = magnitude  # already a scalar count
            if field == "product_id" and resolved:
                product_name = resolved
            fields.append({"field": field, "magnitude": magnitude, "resolved": resolved})
        products.append({
            "datum_address": addr,
            "product_name": product_name,
            "fields": fields,
        })
    return products


def _find_named(docs: list[Any], sandbox_id: str, name: str) -> AuthoritativeDatumDocument | None:
    marker = f".{sandbox_id}."
    for d in docs:
        did = _as_text(getattr(d, "document_id", ""))
        parts = did.split(".")
        if marker in did and len(parts) > 3 and parts[3] == name:
            return d
    return None


def _error(message: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "error": message, "products": [], "product_count": 0}


# register(ProductDocumentViewer())  # retired TASK-2026-08-14-002 Phase 1: renders a
# document's own values, which is a viewscope's job. The module survives as a library —
# build_product_rows feeds record_synopsis, _consumption and taxa_product_table, and
# local_domain_viewer's product table constructs the class directly.
