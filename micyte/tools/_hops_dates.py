"""Decode an agro HOPS-UTC receival token back to a calendar date (tools-layer, read-only).

The write path (:mod:`agro_write_runtime`) ENCODES a calendar day into a HOPS-UTC token via the
agro anchor's ``1-1-6`` chronology; this is the inverse used by read tools (the Inventory Manager)
to show a readable receival date and to compute *days-until-bad*. Kept in the tools layer so a
read tool need not import the heavier write runtime; the chronology-authority construction mirrors
``agro_write_runtime._hops_day``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from micyte.agro.doc_lib import (
    ANCHOR_HOPS_CHRONO_MAG,
    ANCHOR_TIME_PRIMITIVE,
    _as_rows,
    build_chronology_authority,
    schema_from_anchor_payload,
)
from micyte.core.structures.hops.chronology import decode_hops_as_utc_datetime


def chrono_authority(anchor_doc: Any) -> Any | None:
    """Build the agro chronology authority from an anchor doc's ``1-1-6`` chrono row (or None)."""
    if anchor_doc is None:
        return None
    rows = {r.datum_address: r.raw for r in _as_rows(anchor_doc)}
    t = rows.get(ANCHOR_HOPS_CHRONO_MAG)
    if not (t and isinstance(t[0], list) and len(t[0]) > 2):
        return None
    schema = schema_from_anchor_payload(
        {"1-1-1": [["1-1-1", ANCHOR_TIME_PRIMITIVE, str(t[0][2])], ["HOPS-chronological"]]})
    return build_chronology_authority(
        schema_payload=schema,
        quadrennium_payload={"3-1-1": [["3-1-1", "~", "0"], ["quadrennium"]]},
        cosmological_prefix=(0, 0))


def hops_token_to_date(authority: Any, token: str) -> date | None:
    """Decode a HOPS-UTC token to a ``date`` using a prebuilt ``authority`` (None on failure)."""
    token = (token or "").strip()
    if not token or authority is None:
        return None
    try:
        return decode_hops_as_utc_datetime(token, authority=authority).date()
    except Exception:
        return None
