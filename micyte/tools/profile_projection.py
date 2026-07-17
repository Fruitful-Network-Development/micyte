"""Profile-card base projection — the standardized "profile" that the ``profile_card`` tool
loads and that ``farm_profile`` (and future profile-bearing tools) build ON TOP of.

A *profile* is a single value-group-0 "collecting" datum that references three instances:

  1. a **SAMRAS id**  (msn / lcl / txa node)           — marker ``rf.3-1-1`` or ``rf.3-1-5``
  2. a **title**      (nominal-256-64 ascii babelette)  — marker ``rf.3-1-2``
  3. a **visual**     (a datum usable as a picture)      — marker ``rf.3-1-11`` (0-0-11
                                                          json-file-unit), OPTIONAL

``build_profile_projection`` reads that collecting datum when a document has one, and otherwise
falls back to the document's identity metadata (``title`` / ``msn_node``) so existing documents
still project a profile unchanged — the spec's "the standardization … can proceed as it exists
now". This is the base contract a ``farm_profile`` EXTENDS: it composes this projection for the
farm's identity and then adds the filament's fields/plots on top.
"""
from __future__ import annotations

from typing import Any

from micyte.core.datum_ops.datum_resolve import decode_label

from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head
from ._shared.utilities import row_tail_label as _row_tail_label

PROFILE_PROJECTION_SCHEMA = "mycite.v2.portal.profile.projection.v1"
# The datum archetype a deliberately-authored profile collecting datum carries.
PROFILE_ARCHETYPE = "mycite.v2.datum.agro_erp.profile.v1"

_SAMRAS_MARKERS = ("rf.3-1-1", "rf.3-1-5")  # NODE_ID / LCL_ID
_TITLE_MARKER = "rf.3-1-2"
_VISUAL_MARKER = "rf.3-1-11"  # 0-0-11 json-file-unit reference (the "visual")


def _is_value_group_zero(row: Any) -> bool:
    """A profile is a *value-group-0* collecting datum: address ``<layer>-0-<iteration>``."""
    vg = getattr(row, "value_group", None)
    if vg is not None:
        try:
            return int(vg) == 0
        except (TypeError, ValueError):
            pass
    parts = _as_text(getattr(row, "datum_address", "")).split("-")
    return len(parts) == 3 and parts[1] == "0"


def _ref_after(head: list[str], marker: str) -> str:
    for i in range(len(head) - 1):
        if head[i] == marker:
            return head[i + 1]
    return ""


def find_profile_datum(doc: Any) -> Any | None:
    """The vg0 collecting datum: a value-group-0 row whose head references a SAMRAS id AND a title."""
    for row in getattr(doc, "rows", ()) or ():
        if not _is_value_group_zero(row):
            continue
        head = [_as_text(t) for t in _row_head(row)]
        if any(m in head for m in _SAMRAS_MARKERS) and _TITLE_MARKER in head:
            return row
    return None


def build_profile_projection(doc: Any, *, visual_url: str = "") -> dict[str, Any]:
    """Project the standardized profile (samras id + title + visual) from ``doc``.

    Prefers an explicit vg0 collecting datum; falls back to identity metadata. ``visual_url``
    overrides/supplies the picture when a caller resolves one out-of-band (e.g. a logo leaflet).
    """
    metadata = getattr(doc, "document_metadata", None) or {}
    canonical = _as_text(getattr(doc, "canonical_name", ""))
    profile_row = find_profile_datum(doc)
    if profile_row is not None:
        head = [_as_text(t) for t in _row_head(profile_row)]
        samras_node = ""
        for marker in _SAMRAS_MARKERS:
            samras_node = _ref_after(head, marker)
            if samras_node:
                break
        title = _row_tail_label(profile_row) or decode_label(_ref_after(head, _TITLE_MARKER)) or canonical
        visual = visual_url or _ref_after(head, _VISUAL_MARKER)
        source = "datum"
        datum_address = _as_text(getattr(profile_row, "datum_address", ""))
    else:
        samras_node = _as_text(metadata.get("msn_node"))
        title = _as_text(metadata.get("title")) or canonical
        visual = visual_url
        source = "metadata"
        datum_address = ""
    return {
        "schema": PROFILE_PROJECTION_SCHEMA,
        "title": title,
        "samras_node": samras_node,
        "samras_label": samras_node,
        "visual_url": _as_text(visual),
        "has_visual": bool(_as_text(visual)),
        "source": source,
        "datum_address": datum_address,
    }
