"""Workbook ⇄ WORKBOOK-YAML bridge.

Thin adapters between the in-memory :class:`Workbook` (sandbox = named sheets)
and the ``datum_io`` multi-sheet workbook envelope — the standardized,
interface-ready YAML form tools/lenses/UI consume. Transport only; never
persisted (MOS-only storage rule).
"""

from __future__ import annotations

from micyte.core.datum_io import workbook_from_yaml, workbook_to_yaml
from micyte.core.document_naming import (
    CanonicalNameError,
    parse_canonical_document_id,
)

from .ops import Workbook, order_sheets


def to_yaml(workbook: Workbook) -> str:
    """Serialize a Workbook to multi-sheet WORKBOOK YAML (anchor-first sheet order)."""
    return workbook_to_yaml(workbook.sandbox, [workbook.sheet(n) for n in order_sheets(workbook.names())])


def _sheet_key(doc) -> str:
    """Sheet key = the canonical name segment of the document id (matches
    ``datum_workbook_apply.load_workbook``); falls back to ``document_name``."""
    try:
        return parse_canonical_document_id(doc.document_id).name
    except CanonicalNameError:
        return doc.document_name or doc.document_id


def from_yaml(text: str) -> Workbook:
    """Reconstruct a Workbook from WORKBOOK YAML (sheets keyed by canonical name)."""
    sandbox, documents = workbook_from_yaml(text)
    return Workbook(sandbox=sandbox, sheets={_sheet_key(d): d for d in documents})
