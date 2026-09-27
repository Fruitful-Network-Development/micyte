"""What a record of a given VIEW looks like — the shape both the writer and the form need.

An lcl type node carrying an ``rf.3-1-8`` VIEW marker is an instance container: the marker
names which record table the node opens. This says the rest — which document those records live
in, which datum-address family they occupy, and which fields a record carries.

It sits in ``core`` because two sides need the same answer and must not disagree: the write path
(``lcl_write_runtime.create_instance``) builds a row from it, and the editor surface
(``lcl_editor``) builds the form from it. A form offering a field the writer would reject, or a
writer accepting one the form never shows, is the class of bug this placement removes. It also
keeps the MiCyte→FND boundary intact — the tools layer cannot import ``fnd_app``.

Markers resolve through :mod:`micyte.core.datum_ops.field_registry` rather than being written
literally, because a marker means different things in different anchors: ``rf.3-1-2`` is the
title in a farm namespace and the msn join in the registrar.

**The Python table below is the built-in floor, not the whole vocabulary.** A tenant declares
its own record types in a ``record_spec`` datum document, read by :func:`load_specs` and merged
by :func:`specs_for`; the second half of this module is that format, written and read in one
place so the two directions cannot drift. The built-ins WIN a name clash on purpose — each one
is read positionally by a bespoke viewer, and data that redefined its shape would leave that
viewer reading the right document with the wrong columns.

A type node's ``rf.3-1-8`` VIEW marker is the node -> shape edge, so the spec is keyed by TOKEN
rather than by node address: two containers that hold the same kind of record (the two farms
both hold ``contacts``) share one declaration, and no declaration is stranded if a node moves.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

from . import field_registry as _fr
from .datum_resolve import Markers, as_text, decode_label, iter_marker_pairs

RF_TITLE = _fr.marker(_fr.FARM, "title")  # rf.3-1-2


@dataclasses.dataclass(frozen=True)
class Field:
    """One slot of a record row: a logical name, the marker it rides, whether it is required."""

    name: str
    marker: str
    required: bool = False
    label: str = ""

    @property
    def display(self) -> str:
        return self.label or self.name.replace("_", " ").title()


@dataclasses.dataclass(frozen=True)
class RecordSpec:
    """Where a record of some VIEW lives and what its row looks like.

    ``row_family`` is the datum-address family the reader scans (``contacts`` reads ``4-5-*``).
    ``fields`` are appended to the head in order, after the id-pair naming the lcl node — which
    is what makes the record findable FROM the tree, and is what "datum documents organized
    foremost by lcl node address" means in practice.

    The built-in families are allocated ACROSS the agro sandbox, not per document: 4-5
    contacts, 4-6 contracts, 4-7 invoices, 4-8 sales, 4-9 offering. So the family identifies
    the row SHAPE wherever it is read, and a new bespoke record type takes the next one
    rather than reusing a number that already means something else somewhere.
    """

    document: str
    row_family: str
    fields: tuple[Field, ...]
    title_field: str

    def field(self, name: str) -> Field | None:
        return next((f for f in self.fields if f.name == name), None)


#: VIEW token -> record shape.
RECORD_SPEC: dict[str, RecordSpec] = {
    "contacts": RecordSpec(
        document="contacts",
        row_family="4-5",
        title_field="name",
        fields=(
            Field("name", RF_TITLE, required=True, label="Name"),
            Field("email", RF_TITLE, label="Email"),
            Field("phone", RF_TITLE, label="Phone"),
            Field("website", RF_TITLE, label="Website"),
        ),
    ),
}

#: VIEW tokens whose records a bespoke route already owns. Refused by name, never reimplemented:
#: invoice and contract rows carry HOPS date stamps, minted batch nodes and amount nominals, and
#: product rows are a fixed nine-pair vg-9 shape mixing node references, unit abstractions and
#: nominals. A second writer for one document is how two subtly different row shapes appear in it.
OWNED_ELSEWHERE: dict[str, str] = {
    # The ledger tokens stay REFUSED after the old-model pane cleanup retired their
    # bespoke lcl-record writers: these kinds live in the MODERN ledger's own documents
    # (archetype rows via `/portal/api/v2/ledger`), and an lcl record of the same name
    # beside them would be the two-subtly-different-shapes failure this table refuses.
    "invoice": "the modern ledger (add_supply — invoice rows in `invoices`)",
    "sale": "the modern ledger (add_sale — invoice-shaped rows in `sales`)",
    "offering": "the modern ledger (set_offer — offer rows in `offering`)",
    "planting": "the modern planting book (add_planting — a declared type named "
                "planting would write a second, subtly different shape into `plantings`)",
    "contract": "the modern planting book (add_planting — `planting` rows in `plantings`, drawing down a supply batch by address)",
    # Was "the product ingest", which named a script that no longer exists in this
    # tree. `add_product` is the reachable writer (2026-09-02) and the reason the
    # token stays refused here is unchanged: `build_product_rows` parses this
    # document POSITIONALLY, so a data-declared `product` type would write a third
    # shape into rows two readers already disagree about how to read.
    "product": "the product catalog (add_product — `offering_record` rows in `product_profiles`)",
}


def spec_for(view: str) -> RecordSpec | None:
    return RECORD_SPEC.get(str(view or "").strip())


def owner_of(view: str) -> str:
    return OWNED_ELSEWHERE.get(str(view or "").strip(), "")


# --------------------------------------------------------------------------- #
# The spec as DATA — the `record_spec` datum document
#
# Everything above is the built-in floor. A tenant declares its own record types in a datum
# document, and this half is the format: how it is written, how it is read back, and which
# declarations are refused. Both directions live here on purpose — a reader and a writer of the
# same rows in two modules is how a format drifts.
# --------------------------------------------------------------------------- #

#: The per-sandbox document holding tenant-declared record shapes.
SPEC_DOCUMENT = "record_spec"

#: Row families within it. A record type header, then its fields, in order.
SPEC_TYPE_FAMILY = "4-1"
SPEC_FIELD_FAMILY = "4-2"

#: The datum-address family a data-defined type's own records occupy, in its own document.
#: Mirrors `contacts` (own document, one family) rather than sharing one document across types.
DATA_ROW_FAMILY = "4-1"

#: Logical field-registry names a declared field may ride. Deliberately short: every one of
#: these has to be a thing `create_instance` can encode from a text input and a reader can
#: decode back. `title` is the label-babelette every declared field uses today — the same slot
#: the four built-in contacts fields ride. Anything outside this is refused rather than written
#: on a marker whose namespace may not define it at all.
MARKER_FIELDS: tuple[str, ...] = ("title",)

#: Document names a record type may never claim: the sandbox spine, plus this document itself.
#: A tenant type named `lcl` would otherwise write records into the node tree.
RESERVED_DOCUMENTS: frozenset[str] = frozenset(
    {"anchor", "lcl", "txa", "farm_profile", "channel_profile", "object_profiles",
     "sources", SPEC_DOCUMENT}
)


def reserved_token(view: str) -> str:
    """Why this token may not be declared in data, or ``""`` if it may.

    A built-in spec and an ``OWNED_ELSEWHERE`` route both mean a bespoke reader is already
    parsing those rows POSITIONALLY. Letting data redeclare the shape would leave that reader
    reading the right document with the wrong columns — the failure is silent and looks like
    data corruption rather than a rejected write.
    """
    token = str(view or "").strip()
    if token in OWNED_ELSEWHERE:
        return f"{token!r} records are written by {OWNED_ELSEWHERE[token]}"
    if token in RECORD_SPEC:
        return f"{token!r} is a built-in record type read by its own viewer"
    return ""


def parse_field_lines(text: str) -> tuple[tuple[Field, ...], list[str]]:
    """``name* | Label`` per line -> fields, plus the reasons any line was rejected.

    One line per field is the smallest syntax that survives a plain textarea, and a textarea is
    the smallest thing that lets a tenant declare an arbitrary number of fields without a
    bespoke repeating-row form. A trailing ``*`` on the name marks it required; the label after
    ``|`` is optional and defaults to the humanized name.

    Problems are RETURNED, never raised and never silently dropped: a tenant who mistypes a
    field name has to be told which line, not handed a record type quietly missing a column.
    """
    fields: list[Field] = []
    problems: list[str] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(str(text or "").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        name_part, _, label_part = line.partition("|")
        name = name_part.strip()
        required = name.endswith("*")
        if required:
            name = name[:-1].strip()
        slug = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")
        while "__" in slug:
            slug = slug.replace("__", "_")
        if not slug:
            problems.append(f"line {lineno}: no field name")
            continue
        if slug in seen:
            problems.append(f"line {lineno}: duplicate field {slug!r}")
            continue
        seen.add(slug)
        fields.append(Field(slug, RF_TITLE, required=required, label=label_part.strip()))
    return tuple(fields), problems


def spec_from_declaration(
    token: str, fields: tuple[Field, ...], *, namespace: str = _fr.FARM
) -> RecordSpec:
    """The RecordSpec a declared token + field list produces — its own document, family, title.

    The first field is the title field: it is what names the record's lcl node, so something
    has to be, and "the first thing the tenant listed" is the one rule that needs no extra UI.
    """
    return RecordSpec(
        document=token,
        row_family=DATA_ROW_FAMILY,
        title_field=fields[0].name if fields else "",
        fields=tuple(
            dataclasses.replace(f, marker=_fr.marker(namespace, "title")) for f in fields
        ),
    )


def build_spec_rows(
    spec: RecordSpec, token: str, *, type_start: int = 0, field_start: int = 0
) -> list[tuple[str, list]]:
    """``(datum_address, raw)`` pairs declaring ``spec`` — the WRITE half of the format.

    The two starts are the live counts of each family already in the document, so declaring a
    second record type appends beside the first instead of overwriting it.
    """
    from .labels import encode_label_bits

    def _bits(value: str) -> str:
        return encode_label_bits(str(value or ""))

    view = Markers.VIEW
    rows: list[tuple[str, list]] = []
    address = f"{SPEC_TYPE_FAMILY}-{type_start + 1}"
    rows.append((address, [
        [address, view, _bits(token),
         RF_TITLE, _bits(spec.document),
         RF_TITLE, _bits(spec.row_family),
         RF_TITLE, _bits(spec.title_field)],
        [token],
    ]))
    for index, field in enumerate(spec.fields, start=1):
        address = f"{SPEC_FIELD_FAMILY}-{field_start + index}"
        rows.append((address, [
            [address, view, _bits(token),
             RF_TITLE, _bits(field.name),
             RF_TITLE, _bits(field.label),
             RF_TITLE, _bits("title"),
             RF_TITLE, _bits("required" if field.required else "")],
            [field.name],
        ]))
    return rows


def load_specs(
    document: Any | None, *, namespace: str = _fr.FARM
) -> tuple[dict[str, RecordSpec], list[str]]:
    """Read a ``record_spec`` document into specs, plus the reasons any row was ignored.

    The READ half of :func:`build_spec_rows`. A row whose token is reserved is ignored with a
    reason rather than merged, so a spec document written before a token became built-in cannot
    quietly take over a bespoke reader's rows.
    """
    problems: list[str] = []
    if document is None:
        return {}, problems

    headers: dict[str, tuple[str, str, str]] = {}
    fields: dict[str, list[Field]] = {}
    title_marker = _fr.marker(namespace, "title")

    for row in getattr(document, "rows", ()) or ():
        address = as_text(getattr(row, "datum_address", ""))
        head = _spec_head(row)
        if head is None:
            continue
        pairs = list(iter_marker_pairs(head))
        if not pairs or pairs[0][0] != Markers.VIEW:
            continue
        token = decode_label(pairs[0][1]).strip()
        values = [decode_label(magnitude) for _marker, magnitude in pairs[1:]]
        if not token:
            problems.append(f"{address}: row declares no view token")
            continue
        if address.startswith(SPEC_TYPE_FAMILY + "-"):
            document_name, row_family, title_field = [*values, "", "", ""][:3]
            headers[token] = (document_name, row_family, title_field)
        elif address.startswith(SPEC_FIELD_FAMILY + "-"):
            name, label, marker_field, required = [*values, "", "", "", ""][:4]
            if not name:
                problems.append(f"{address}: field row has no name")
                continue
            if marker_field and marker_field not in MARKER_FIELDS:
                problems.append(f"{address}: field {name!r} rides unsupported marker {marker_field!r}")
                continue
            fields.setdefault(token, []).append(
                Field(name, title_marker, required=(required == "required"), label=label)
            )

    specs: dict[str, RecordSpec] = {}
    for token, (document_name, row_family, title_field) in headers.items():
        why = reserved_token(token)
        if why:
            problems.append(f"{token}: ignored — {why}")
            continue
        declared = tuple(fields.get(token, ()))
        if not declared:
            problems.append(f"{token}: declared with no fields")
            continue
        specs[token] = RecordSpec(
            document=document_name or token,
            row_family=row_family or DATA_ROW_FAMILY,
            title_field=title_field or declared[0].name,
            fields=declared,
        )
    for token in fields:
        if token not in headers:
            problems.append(f"{token}: fields declared with no record type row")
    return specs, problems


def specs_for(
    documents: Mapping[str, Any], *, sandbox_id: str = "", msn_id: str = ""
) -> dict[str, RecordSpec]:
    """Every record shape this sandbox knows — the built-in floor plus what its data declares.

    ``documents`` is short-name -> datum document (what the write path already holds and what
    a tool can build from the catalog). Built-ins WIN: a data row that names one is refused on
    write and ignored here, because a bespoke viewer is reading those rows positionally.
    """
    # Through the RESOLVER so `(msn, sandbox)` is consulted; the FARM default is kept
    # for a sandbox neither table knows, which is what it always meant.
    try:
        namespace = _fr.namespace_for_sandbox(str(sandbox_id or ""), msn_id=str(msn_id or ""))
    except KeyError:
        namespace = _fr.FARM
    declared, _problems = load_specs((documents or {}).get(SPEC_DOCUMENT), namespace=namespace)
    return {**declared, **RECORD_SPEC}


def _spec_head(row: Any) -> list | None:
    raw = getattr(row, "raw", None)
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return raw[0]
    return None


# --------------------------------------------------------------------------- #
# The RECORD ROW — what a spec describes
#
# The spec says what a record looks like; this is the row itself. Written by create, rewritten
# by save, read by the form that prefills an edit and by the lookup that decides whether a node
# already has content. Four call sites, one definition, for the same reason the spec format has
# one: positional pairs read in one module and written in another drift silently.
# --------------------------------------------------------------------------- #

#: The marker a record row LEADS with, naming the lcl node the record is. This pair is what
#: makes a datum document "organized foremost by lcl node address" in practice — every reader
#: of these documents keys on it, and it is why a record is reachable FROM the tree.
RF_RECORD_ID = _fr.marker(_fr.FARM, "lcl_id")  # rf.3-1-5


def build_record_head(spec: RecordSpec, *, address: str, node: str,
                      values: Mapping[str, Any]) -> list:
    """The head of one record row: the id-pair naming the node, then the fields IN ORDER.

    Position is the field identity here — several fields ride the same title marker, exactly as
    the built-in contacts row does — so a field the caller omits still occupies its slot with an
    empty magnitude rather than shifting everything after it.
    """
    from .labels import encode_label_bits

    head: list[Any] = [address, RF_RECORD_ID, node]
    for field in spec.fields:
        head += [field.marker, encode_label_bits(str(values.get(field.name, "") or ""))]
    return head


def record_rows(document: Any | None, spec: RecordSpec) -> list[tuple[str, str, dict[str, str]]]:
    """Every row of this spec's family as ``(datum_address, node, {field: value})``.

    The single inverse of :func:`build_record_head`. Everything that needs to know what is in a
    record document goes through here — the adoption check, the edit-form prefill and the
    duplicate check — so there is exactly one parser for a format whose fields are positional.

    A row written under a SHORTER spec than the current one (a field added after the fact) reads
    back with the new field empty rather than failing: the values are positional, so a short row
    is a short row, not a broken one.
    """
    out: list[tuple[str, str, dict[str, str]]] = []
    for row in (getattr(document, "rows", ()) or ()) if document is not None else ():
        address = as_text(getattr(row, "datum_address", ""))
        head = _spec_head(row)
        if head is None or not address.startswith(spec.row_family + "-"):
            continue
        pairs = list(iter_marker_pairs(head))
        if not pairs or pairs[0][0] != RF_RECORD_ID:
            continue
        node = as_text(pairs[0][1])
        if not node:
            continue
        magnitudes = [decode_label(magnitude) for _marker, magnitude in pairs[1:]]
        out.append((address, node, {
            field.name: (magnitudes[index] if index < len(magnitudes) else "")
            for index, field in enumerate(spec.fields)
        }))
    return out


def record_addresses(document: Any | None, spec: RecordSpec) -> dict[str, str]:
    """lcl node -> the datum address of the row recording it.

    ``setdefault`` keeps the FIRST row for a node: a second one is a corruption, and a reader
    should show what has been there rather than let a later duplicate win silently.
    """
    out: dict[str, str] = {}
    for address, node, _values in record_rows(document, spec):
        out.setdefault(node, address)
    return out


def read_record(document: Any | None, spec: RecordSpec, node: str) -> tuple[str, dict[str, str]] | None:
    """``(datum_address, {field: value})`` for a node's record row, or ``None``."""
    wanted = as_text(node)
    for address, found, values in record_rows(document, spec):
        if found == wanted:
            return address, values
    return None


def validate_values(spec: RecordSpec, values: Mapping[str, Any]) -> str:
    """``""`` when ``values`` fit ``spec``, else why not — shared by create and save.

    An unknown field is refused rather than dropped: silently discarding it would leave the
    caller believing it was stored.
    """
    missing = [f.name for f in spec.fields if f.required and not str(values.get(f.name, "") or "").strip()]
    if missing:
        return f"record needs {', '.join(missing)}"
    unknown = sorted(set(values) - {f.name for f in spec.fields})
    if unknown:
        return f"record has no field(s) {', '.join(unknown)}"
    return ""
