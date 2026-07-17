"""Shared, dependency-free helpers for WorkbenchTools (audit Theme E consolidation).

These were copy-pasted across the tool modules (`_as_text` ×6, `_row_head` ×2,
`_row_tail_label`). Single-sourced here so a fix lands once. No imports beyond typing →
no risk of an import cycle with the tools that use it.
"""

from __future__ import annotations

from typing import Any


def as_text(value: object) -> str:
    """Normalize any value to a stripped string ('' for None)."""
    return "" if value is None else str(value).strip()


def row_head(row: Any) -> list[Any]:
    """The head token list of a datum row.

    Rows are ``[[addr, ...markers], [label]]`` (nested) — return the head; for a flat
    ``[...]`` raw, return it as-is; otherwise ``[]``.
    """
    raw = getattr(row, "raw", None)
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return raw[0]
    if isinstance(raw, list):
        return raw
    return []


def row_tail_label(row: Any) -> str:
    """The plain tail label of a datum row (``raw[1][0]``), or ''."""
    raw = getattr(row, "raw", None)
    if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], list) and raw[1]:
        return as_text(raw[1][0])
    return ""


__all__ = ["as_text", "row_head", "row_tail_label"]
