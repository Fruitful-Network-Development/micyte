"""Mint a new msn node under an existing one.

Nothing minted an address before this. ``create_ag_profile`` attaches a profile to a node
that already exists, and every node in the live space was bootstrapped by a script — so
"a customer at an address the registrar has never heard of" had no path at all.

The whole operation is two decisions and one append:

1. **Which address?** The next free child of the parent, read off the ADDRESS SPACE.
2. **Into which document?** The name table that already names the parent's other children,
   so a new street address lands beside its siblings rather than in a document of its own.
3. Then :meth:`~micyte.adapters.sql.datum_store.SqliteSystemDatumStoreAdapter.append_document_rows`,
   which does not touch the 138 MB catalog blob — see its docstring for why that matters.

**An msn_id is a POSITION, not an identifier.** Read off three live entities:

    <city> / <street> / <house> / <entity>

Three live entities were read off to establish that shape. Their addresses are not
reproduced here: the SHAPE is the fact this docstring needs, and printing a real entity
beside its street address turns an example into a directory entry.

city -> street -> house -> ENTITY. A business is an OCCUPANT of a house, at the same depth
as the people there. Minting one as a child of a city puts a company where a street
belongs — which is what happened to a client's sandbox on 2026-08-08, and it made
the sandbox's whole address chain a lie before anything read it.

So the caller chooses the PARENT, and the parent is a claim. `mint_child` cannot check it
— an address space has no types — which is exactly why the caller has to know the rule.

**The next free child is not `len(children) + 1`.** A gap in the sequence is a DELETION,
not a vacancy: reusing `3-2-3-17-18-1-7` because nothing occupies it re-points every
reference to whatever used to be there — an invoice, a job, a boundary — at a new place,
silently and irreversibly. So the next address is one past the highest ever used, and the
highest is read from the space rather than from a row count.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from micyte.core.datum_documents import AuthoritativeDatumDocumentRow
from micyte.core.datum_ops import field_registry as _fr
from micyte.core.datum_ops.datum_resolve import as_text
from micyte.core.datum_ops.labels import encode_label_bits

from .directory import SANDBOX

#: The archetypes whose rows ARE an msn name table, in the order a new child prefers them.
#: `address_nodes` first because that is where depth-8 street addresses live and it is
#: where the overwhelming majority of children go; `administrative` names the region nodes
#: above them. Both are `record`, so neither is distinguishable by shape — which document
#: a row belongs in is a CONVENTION, and this is where it is written down.
PREFERRED_TABLES: tuple[str, ...] = ("address_nodes", "administrative")


class MintRefused(ValueError):
    """A mint that would have been wrong, refused with the reason."""


@dataclass(frozen=True)
class Minted:
    address: str
    title: str
    document_id: str
    prior_document_id: str
    document_name: str


def next_child(space: Any, parent: str) -> str:
    """The next address under ``parent`` that has never been used.

    One past the highest existing sibling — NOT the first gap. See the module docstring:
    a gap is a deletion, and handing it out re-points every reference that named it.
    """
    token = as_text(parent)
    if token and token not in space.depth_of:
        raise MintRefused(f"{token!r} is not an address the space holds")
    siblings = space.children.get(token, ())
    highest = 0
    for sibling in siblings:
        tail = sibling.rsplit("-", 1)[-1]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return f"{token}-{highest + 1}" if token else str(highest + 1)


def _table_for(names: Any, parent: str, key_field: str = "msn_id") -> tuple[str, str]:
    """``(sandbox, document_name)`` for the table a child of ``parent`` belongs in.

    Preference is by where the parent's existing children already are — a sibling is the
    best evidence of the convention — and only then by :data:`PREFERRED_TABLES`. A new
    address in a document none of its siblings occupy is not wrong, but it is a second
    place to look for the same kind of thing, which is how a corpus stops being legible.
    """
    tables = [t for t in getattr(names, "tables", ()) if t.key_field == key_field]
    if not tables:
        raise MintRefused(f"no name table over {key_field!r} to append to")
    by_name = {t.name: t for t in tables}
    for preferred in PREFERRED_TABLES:
        if preferred in by_name:
            return by_name[preferred].sandbox, preferred
    biggest = max(tables, key=lambda t: t.named)
    return biggest.sandbox, biggest.name


def mint_child(
    store: Any,
    *,
    tenant_id: str,
    parent: str,
    title: str,
    names: Any,
    space: Any,
    sandbox: str = SANDBOX,
) -> Minted:
    """Give ``parent`` a new named child, and return where it landed.

    Refuses rather than guesses, three ways:

    * a parent the space does not hold — minting under an address nobody has named puts
      the child somewhere the browser cannot reach;
    * a title a sibling already carries — two children of one parent with one name make
      the label ambiguous exactly where an operator picks from a list;
    * an empty title — an unnamed node renders as its own address, which is what this
      whole path exists to stop.
    """
    parent_token = as_text(parent)
    label = as_text(title)
    if not label:
        raise MintRefused("a node needs a name; an unnamed one renders as its address")
    if parent_token and parent_token not in space.depth_of:
        raise MintRefused(f"{parent_token!r} is not an address the space holds")

    siblings = space.children.get(parent_token, ())
    for sibling in siblings:
        if names.name_for(sibling) == label:
            raise MintRefused(f"{parent_token or 'the top'} already has a child named {label!r}")

    address = next_child(space, parent_token)
    table_sandbox, document_name = _table_for(names, parent_token)
    document_id = _document_id(store, tenant_id=tenant_id, sandbox=table_sandbox, name=document_name)
    if not document_id:
        raise MintRefused(f"{table_sandbox}/{document_name} is not in the store")

    row = _record_row(
        store, tenant_id=tenant_id, document_id=document_id,
        sandbox=table_sandbox, address=address, title=label,
    )
    result = store.append_document_rows(
        tenant_id=tenant_id, document_id=document_id, rows=[row]
    )
    return Minted(
        address=address, title=label, document_id=result["document_id"],
        prior_document_id=result["prior_document_id"], document_name=document_name,
    )


def _document_id(store: Any, *, tenant_id: str, sandbox: str, name: str) -> str:
    return store.document_id_for(tenant_id=tenant_id, sandbox=sandbox, name=name)


def _record_row(
    store: Any, *, tenant_id: str, document_id: str, sandbox: str, address: str, title: str,
    msn_id: str = "",
) -> AuthoritativeDatumDocumentRow:
    """One `record` row: ``[self, msn_id, <address>, title, <encoded label>]``.

    The markers come from the decoder ring for THIS sandbox, never as literals: `rf.3-1-3`
    is `title` in the registrar and `coordinate` in a farm, and writing the literal is the
    mistake that hid 469 of 471 geometry documents. The title is babelette-encoded because
    that is how every other row in these documents carries one — an unencoded label would
    read back as itself through `decode_label` and still be the only row that is different.
    """
    namespace = _fr.namespace_for_sandbox(sandbox, msn_id=msn_id)
    msn_marker = "rf." + _fr.address(namespace, "msn_id")
    title_marker = "rf." + _fr.address(namespace, "title")
    datum_address = _next_datum_address(store, tenant_id=tenant_id, document_id=document_id)
    return AuthoritativeDatumDocumentRow(
        datum_address=datum_address,
        raw=[[datum_address, msn_marker, address, title_marker, encode_label_bits(title)]],
    )


def _next_datum_address(store: Any, *, tenant_id: str, document_id: str) -> str:
    """The next free ROW address in the document — its position, not its content.

    Two separate questions, and the first cut of this got both wrong by answering them
    with one loop — it took the family from whichever row SQLite returned last and the
    iteration from the highest anywhere, and put a name-table row at ``5-0-42008``:

    * **Which family?** The DOMINANT one, by count. `registrar/address_nodes` is 41,998
      rows of ``4-2`` and 2 of ``5-0``; a new name row belongs with the 41,998.
    * **Which iteration?** One past the highest in THAT FAMILY. Until 2026-09-17 this was
      one past the highest in the whole document, on the reasoning that ``4-2`` tops out
      at 42007 and ``5-0`` at 42008 so a family-scoped count "would hand back an
      iteration the document has already used elsewhere" — but ``4-2-42008`` and
      ``5-0-42008`` are different addresses, and a document-wide counter is exactly what
      leaves the gaps the engine's I8 (``core/mss/invariants.py``) refuses at the door:
      an appended row lands one past ITS family's highest, which is what
      ``row_address.next_row_address`` has minted for every other writer since 09-11.

    This is deliberately NOT ``node_ops._def_family_next_address``, which refuses this
    document outright ("sheet has no definition family"): that rule is for lcl definition
    sheets, whose heads carry the structural edge. A name table is a different kind of
    document and gets a different rule, rather than a widened one that would blur both.

    Read from ``datum_row_semantics`` — one indexed row per address — rather than from the
    document, because the point of the append path is not loading the document to decide
    where to put things.
    """
    from collections import Counter

    with store._connect() as connection:
        rows = connection.execute(
            "SELECT datum_address FROM datum_row_semantics WHERE tenant_id=? AND document_id=?",
            (tenant_id, document_id),
        ).fetchall()
    families: Counter = Counter()
    highest: dict[str, int] = {}
    for row in rows:
        parts = as_text(row["datum_address"]).split("-")
        if len(parts) == 3 and parts[2].isdigit():
            family = f"{parts[0]}-{parts[1]}"
            families[family] += 1
            highest[family] = max(highest.get(family, 0), int(parts[2]))
    if not families:
        raise MintRefused(f"{document_id!r} has no rows to append after")
    family = families.most_common(1)[0][0]
    return f"{family}-{highest[family] + 1}"


__all__ = ["PREFERRED_TABLES", "MintRefused", "Minted", "mint_child", "next_child"]
