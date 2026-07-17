"""Reader for the agro_erp ``object_profiles`` doc — typed farm objects.

Each ``4-1-k`` row binds an object's lcl node (rf.3-1-5) to a name (rf.3-1-2) plus a kind and
free-form attributes carried as rf.3-1-7 ``key=value`` nominals. Written by
``agro_write_runtime.create_object`` / ``save_object`` / ``delete_object``. This pure reader is
consumed by the editable object profile page (TASK-006) and the farm summary hub (TASK-007).
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops.datum_resolve import decode_label

_LCL_MARKER = "rf.3-1-5"
_TITLE_MARKER = "rf.3-1-2"
_NOMINAL_MARKER = "rf.3-1-7"

# Structure kinds carry drawn geometry (in farm_profile); the rest are store-only.
STRUCTURE_KINDS = ("barn", "greenhouse", "tunnel", "custom_area")


def build_object_rows(doc: Any) -> list[dict[str, Any]]:
    """Project an object_profiles doc → [{node, name, kind, attrs, is_geo}]."""
    out: list[dict[str, Any]] = []
    for r in (getattr(doc, "rows", ()) or ()):
        addr = r.datum_address if hasattr(r, "datum_address") else r["datum_address"]
        raw = r.raw if hasattr(r, "raw") else r["raw"]
        if not str(addr).startswith("4-1-"):
            continue
        head = raw[0]
        node = name = kind = ""
        attrs: dict[str, str] = {}
        for i in range(1, len(head) - 1):
            marker = str(head[i])
            if marker == _LCL_MARKER:
                node = str(head[i + 1])
            elif marker == _TITLE_MARKER:
                name = decode_label(str(head[i + 1]))
            elif marker == _NOMINAL_MARKER:
                key, sep, val = decode_label(str(head[i + 1])).partition("=")
                if not sep:
                    continue
                if key == "kind":
                    kind = val
                elif key:
                    attrs[key] = val
        if node:
            out.append({"node": node, "name": name or node, "kind": kind,
                        "attrs": attrs, "is_geo": kind in STRUCTURE_KINDS})
    return out
