"""Export rows to CSV — the one surface where data LEAVES.

Everything else in this program renders inside the portal. A CSV is different in kind: it
is copied to a spreadsheet, mailed, uploaded. Three things follow, and they are what this
module is:

1. **Preview first.** :func:`preview` and :func:`to_csv` are given the SAME rows, so what
   the operator approves is what leaves. A download that recomputed its own rows could
   differ from the preview in exactly the case that matters — a filter the operator got
   wrong.
2. **Columns are LOGICAL fields.** Never ``rf.3-1-N``, which is `title` in the registrar
   and `coordinate` in a farm. An export keyed on the literal would silently ship a
   different column per sandbox.
3. **A cell is data, not a formula.** A name beginning ``=``, ``+``, ``-`` or ``@`` is
   executed by Excel, Sheets and LibreOffice on open. Cells here come from an operator's
   own contact list, so this is not a hypothetical: it is the ordinary way a CSV export
   turns a stored name into code running on whoever opens it.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any

from micyte.core.datum_ops import archetype_shape as ash
from micyte.core.datum_ops.datum_resolve import as_text, decode_label

from ._viewscope import _row_values

#: Ceiling on one export. Bounded for the same reason every buffer here is, and reported
#: exactly: a truncated export and a small result set look identical in a spreadsheet, and
#: only one of them means "this is all of them".
MAX_EXPORT_ROWS = 20_000

#: Fields whose value is a node address and which therefore EXPAND to a readable trail.
#: Read off the tree key fields rather than listed, so a new address space expands too.
ADDRESS_FIELDS: tuple[str, ...] = ("msn_id", "site_msn", "lcl_id", "txa_id")

#: The characters a spreadsheet treats as the start of a formula.
#:
#: Tab and carriage return belong on this list in the abstract — Excel treats a cell
#: beginning with either as a formula — and they are deliberately NOT here: every value
#: passes through `as_text`, which strips surrounding whitespace, so a leading tab cannot
#: reach a cell at all. Listing them would claim a defence that never fires and hide the
#: one that does.
FORMULA_LEADERS = ("=", "+", "-", "@")


def neutralize(value: str) -> str:
    """Make a cell that a spreadsheet would EXECUTE into one it will only display.

    Prefixed with a single quote rather than stripped: the value is the operator's data
    and an export that quietly edited it would be lying about what is stored. ``-12`` is
    left alone — a negative number is not a formula, and mangling every minus sign would
    make a pay column unreadable.
    """
    token = as_text(value)
    if not token or not token.startswith(FORMULA_LEADERS):
        return token
    if token[0] == "-" and token[1:].replace(".", "", 1).isdigit():
        return token
    return "'" + token


@dataclass(frozen=True)
class ExportSpec:
    """What to take out, said in logical terms so it means the same in every sandbox."""

    archetype: str
    columns: tuple[str, ...]
    #: ``logical field -> the value a row must carry``. Your `friend` flag is a cell like
    #: any other; nothing here knows what it means.
    filters: dict[str, str] = field(default_factory=dict)
    #: Address fields to render as a readable trail as WELL as the address.
    expand: tuple[str, ...] = ()
    limit: int = MAX_EXPORT_ROWS


def mailing_address(space: Any, address: str, *, depth: int = 4) -> str:
    """A node address as the trail a person would write on an envelope.

    ``AddressSpace.path`` already returns every present ancestor outermost-first, so this
    is a join that exists rather than one this module invents. Reversed and cut to the
    innermost ``depth`` steps: a mailing address is a house, a street, a town and a
    county, not the northwest hemisphere.
    """
    trail = [step["label"] for step in space.path(as_text(address))]
    if not trail:
        return ""
    return ", ".join(reversed(trail[-depth:]))


def _cell(values: dict[str, list[str]], field_name: str) -> str:
    cells = [v for v in values.get(field_name, ()) if v]
    if not cells:
        return ""
    if field_name in ("title", "note", "common_name", "name"):
        return " · ".join(decode_label(c) for c in cells)
    return " · ".join(cells)


def rows_for(
    document: Any,
    spec: ExportSpec,
    *,
    sandbox: str,
    registry: Any,
    names: Any = None,
    space: Any = None,
) -> tuple[list[dict[str, str]], int]:
    """``(rows, matched)`` — the rows the spec selects, and how many matched before the cap.

    ``matched`` is counted before truncation so the caller can say "20,000 of 31,412"
    rather than presenting a cut-off list as the whole answer.
    """
    archetype = registry.get(spec.archetype)
    if archetype is None:
        return [], 0
    out: list[dict[str, str]] = []
    matched = 0
    for row in getattr(document, "rows", ()) or ():
        shape = ash.row_shape(row.raw, sandbox=sandbox)
        if not archetype.covers(shape):
            continue
        values = _row_values(ash._row_head(row.raw), namespace=sandbox)
        if any(_cell(values, k) != as_text(v) for k, v in spec.filters.items()):
            continue
        matched += 1
        if len(out) >= max(0, spec.limit):
            continue
        record: dict[str, str] = {}
        for column in spec.columns:
            raw_cell = _cell(values, column)
            if column in ADDRESS_FIELDS and names is not None:
                key = "msn_id" if column in ("msn_id", "site_msn") else column
                named = names.name_for(raw_cell, key_field=key)
                record[column] = named or raw_cell
            else:
                record[column] = raw_cell
            if column in spec.expand and space is not None:
                record[f"{column}_address"] = mailing_address(space, raw_cell)
        out.append(record)
    return out, matched


def header(spec: ExportSpec) -> list[str]:
    """Column order, with each expansion sitting beside the column it expands."""
    out: list[str] = []
    for column in spec.columns:
        out.append(column)
        if column in spec.expand:
            out.append(f"{column}_address")
    return out


def to_csv(spec: ExportSpec, rows: list[dict[str, str]]) -> str:
    """The bytes that leave. Given the SAME rows the preview showed."""
    columns = header(spec)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore",
                            lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: neutralize(row.get(k, "")) for k in columns})
    return buffer.getvalue()


#: Where a TABLE's own CSV comes from, as opposed to a document's.
#:
#: :class:`ExportSpec` takes a document apart by logical field, which is right when the
#: question is "everything this archetype holds". It cannot express what an operator is
#: actually looking at in the jobs table: `customer` is resolved from the *contacts*
#: document, `when` is a HOPS token decoded against the sandbox's own clock, and `pay` is
#: cents rendered as dollars. None of the three is a field on the row.
#:
#: So the table exports itself. The route rebuilds the tool's payload from the same
#: parameters the screen was built from and writes the columns it is showing — which makes
#: `export_manager`'s rule exact rather than approximate: there is no second selection that
#: could disagree, because there is no second selection.
TABLE_CSV_ROUTE = "/portal/api/v2/tools/table.csv"


def table_export(tool_id: str, *, label: str = "Export CSV") -> dict[str, str]:
    """The export descriptor an ``editable_table`` carries. Declared by the tool itself.

    A tool that does not call this is not exportable, and the route refuses it by id. That
    is the whole permission model here and it is deliberately small: a route that can
    serialize any registered tool's payload must not be pointable at one that never agreed
    to leave the building.
    """
    return {"route": TABLE_CSV_ROUTE, "tool_id": as_text(tool_id), "label": as_text(label)}


def table_csv(columns: list[str], rows: list[dict[str, Any]]) -> str:
    """A displayed table as the bytes that leave, one column per visible column.

    Same neutralization as :func:`to_csv` — a cell beginning ``=``, ``+``, ``-`` or ``@`` is
    executed by Excel, Sheets and LibreOffice on open, and these cells are the operator's own
    contact names.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), extrasaction="ignore",
                            lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: neutralize(as_text((row or {}).get(c))) for c in columns})
    return buffer.getvalue()


__all__ = [
    "ADDRESS_FIELDS",
    "FORMULA_LEADERS",
    "MAX_EXPORT_ROWS",
    "TABLE_CSV_ROUTE",
    "ExportSpec",
    "header",
    "mailing_address",
    "neutralize",
    "rows_for",
    "table_csv",
    "table_export",
    "to_csv",
]
