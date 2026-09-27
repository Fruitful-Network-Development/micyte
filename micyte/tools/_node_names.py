"""Resolve a node address to the name something calls it.

A viewscope that shows ``3-2-3-17-77-1-1`` where the old viewer showed *city_of_akron* is
not a replacement for it. This is what closes that gap, and the shape of the answer falls
out of the archetype library rather than being invented beside it:

    a `record` document IS an (msn_id -> title) table
    a `taxon_record` document IS a (txa_id -> title) table
    a `class_record` document IS an (lcl_id -> title) table

So "where do names live" is already answered by the archetypes; this reads them. Any
document the registry recognises as one of those kinds contributes, wherever it is and
whatever it is called — no table of blessed document names, which is the thing that goes
stale the first time a sandbox is added.

**Bounded by streaming, not by truncation.** ``registrar/address_nodes`` is 27 MB and
41,999 rows, and the first cut of this module simply refused to read it: a per-document
byte budget kept the peak safe and cost 41,990 of the store's 49,044 names, so most of the
msn address space rendered as addresses. That was the right bound applied to the wrong
quantity. Measured on ``registrar`` + ``taxonomy``:

===========================================  ========  =========  =======
approach                                       time      peak      names
===========================================  ========  =========  =======
4 MB budget (what this module shipped with)     1.0 s    +67 MB     7,054
no budget, documents assembled                  5.8 s   +237 MB    49,044
no budget, payload parsed per document          5.1 s   +216 MB    49,044
**no budget, rows streamed from SQLite**      **3.5 s**  **+70 MB**  **49,044**
===========================================  ========  =========  =======

The memory was never the names — the finished index is **1.0 MB for 41,994 entries**. It
was assembling 42,000 row objects to look at each one once. Streaming pays 2.5 s more
than the truncated read for 41,990 more names, ONCE per store write: the memo below is
keyed on the db mtime, so every render after the first costs nothing (17 ms against
3.6 s for a whole panel, measured on `registrar/msn_registry`).
:meth:`~micyte.adapters.sql.datum_store.SqliteSystemDatumStoreAdapter.iter_document_rows_by_sandbox`
hands the rows back one at a time so the document is never a Python object graph, and the
budget stops being needed. A store that cannot stream still gets the budget, and still
gets the truncated index it implies — see :func:`build_name_index`.

An address no name table claims still renders as an address. The primitive promises exactly
that: *"a chip that resolves to a name when one is known and stays an address when it is
not."* Silence is the honest failure here — a NAME is a claim, and a guessed one is worse
than a number.
"""

from __future__ import annotations

import threading
from collections import Counter, OrderedDict
from dataclasses import dataclass
from typing import Any

from micyte.core import archetypes as arc
from micyte.core.datum_ops import archetype_shape as ash
from micyte.core.datum_ops.datum_resolve import as_text, decode_label, iter_marker_pairs

#: Archetypes that ARE name tables, and which field each keys on. The name is always
#: `title`; what changes is the address space it names.
NAME_TABLE_ARCHETYPES: dict[str, str] = {
    "record": "msn_id",
    "taxon_record": "txa_id",
    "class_record": "lcl_id",
    "legal_entity_profile": "msn_id",
    "administrative_entity_profile": "msn_id",
    "ag_profile": "msn_id",
    "farm_profile_identity": "msn_id",
}

#: The field every name table names things WITH. What changes between archetypes is the
#: address space being named, which is what :data:`NAME_TABLE_ARCHETYPES` records.
NAME_FIELD = "title"

#: Every address space a name table can key on. Read off the archetypes rather than listed,
#: so adding a name-table archetype does not need a second edit here to take effect.
KEY_FIELDS = frozenset(NAME_TABLE_ARCHETYPES.values())

#: Per-document ceiling for a store that cannot stream rows. 4 MB admits `taxonomy/txa`
#: (2.9 MB), `txa_registry` (2.6 MB), `registrar/administrative` (0.75 MB) and every
#: lcl/entity table, and excludes `address_nodes` (27 MB) — at the cost of 41,990 names.
#:
#: This is a floor, not the design. The SQLite adapter streams and ignores it entirely; it
#: exists so a filesystem or in-memory store degrades to a smaller index rather than to an
#: unbounded read. :func:`build_name_index` reports which path it took in
#: :attr:`NameIndex.streamed`, because a silently truncated index and a complete one are
#: different answers and the caller is entitled to know which it holds.
NAME_TABLE_MAX_BYTES = 4_000_000

#: Sandboxes consulted for names, beyond the document's own. `registrar` holds the msn
#: directory and `taxonomy` the txa registry, and both are read by documents in every other
#: sandbox — an lcl_id resolves at home, an msn_id almost never does.
SHARED_NAME_SANDBOXES: tuple[str, ...] = ("registrar", "taxonomy")

#: What a sandbox's own local domain log is called in :class:`NameTable`, and the space it
#: names. Not an archetype name: the log is read through
#: :func:`micyte.core.datum_ops.local_domain.read_log` rather than through the registry,
#: for the reason :func:`_fold_local_domain` gives.
LOCAL_DOMAIN_TABLE = "local_domain_log"
LOCAL_DOMAIN_KEY_FIELD = "lcl_id"


class NameIndex:
    """``address -> name``, with the document's OWN sandbox consulted first.

    A node address is not globally unique. ``1-1-1`` is `legal` in the registrar's lcl and
    `employee` in a farm's — an lcl space is local, which is what the L in lcl means.

    The flat map this replaces got the right answer by ITERATION ORDER: the document's own
    sandbox happened to be read first, and first-writer-wins did the rest. That is a
    property of a loop, not of the design, and it would have inverted the day someone
    sorted the sandboxes. Two maps say it instead: LOCAL wins, GLOBAL fills the gaps — and
    the gaps are real, since a farm's `product_profiles` cites taxonomy txa nodes that only
    `taxonomy/txa` names.
    """

    def __init__(
        self,
        local: dict[str, str],
        shared: dict[str, str] | None = None,
        *,
        tables: tuple[NameTable, ...] = (),
        by_key: dict[str, set[str]] | None = None,
        streamed: bool = False,
        conflicts: tuple[tuple[str, str, str, str, str], ...] = (),
        conflict_count: int = 0,
        failed: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self._local = local
        self._shared = shared or {}
        #: The documents that contributed, each with the archetype it turned out to be and
        #: the address space it keys on. What made this worth keeping: answering "is this
        #: document a name table, and over which field?" from the document itself costs a
        #: 27 MB read; the fold already knew.
        self.tables = tables
        self.sources = tuple(table.source for table in tables)
        self._by_key = by_key or {}
        #: Lazily built by `_address_space.address_space_for`, and held HERE rather than in
        #: a module cache keyed on `id()`: the space is only valid for this index, and this
        #: index is already memoized on the store's mtime. One lifetime, one invalidation.
        self._spaces: dict[str, Any] = {}
        #: True when every name table was read in full. False means a byte budget applied
        #: and some addresses that DO have names will render as addresses — a different
        #: answer, not a slower one.
        self.streamed = streamed
        #: ``(address, kept, kept_source, rejected, rejected_source)`` for addresses two
        #: name tables name differently — capped at :data:`CONFLICT_SAMPLE_MAX`.
        self.conflicts = conflicts
        #: Exact number of such disagreements, whether or not they fit in the sample.
        self.conflict_count = conflict_count
        #: ``(sandbox, error)`` for sandboxes that raised while being folded. An absent
        #: sandbox and a broken one both contribute nothing; only this tells them apart.
        self.failed = failed

    def __len__(self) -> int:
        return len(set(self._local) | set(self._shared))

    def name_for(self, address: object, *, key_field: str = "") -> str:
        """The name for an address, optionally within ONE address space.

        The map is flat, and the spaces overlap. Measured live: `1`, `2`, `3`, `4` are
        named in both the msn and txa spaces; 16 addresses are named in both txa and lcl
        in the registrar and 28 in a farm's. Unqualified, `label("1-1-1")` returns whichever
        table was read first — which is iteration order, not a denotation.

        So a caller that KNOWS which space it is asking about says so, and gets nothing
        rather than a name from the wrong one. Callers that do not qualify keep the old
        behaviour: the tree narrows by key field upstream, and a slot chip has only the
        one address space its archetype declares.
        """
        token = as_text(address)
        space = as_text(key_field)
        if space and token not in self._by_key.get(space, ()):
            return ""
        return self._local.get(token) or self._shared.get(token, "")

    def label(self, address: object, *, key_field: str = "") -> str:
        """The name if there is one, else the address unchanged."""
        token = as_text(address)
        return self.name_for(token, key_field=key_field) or token

    def remember(self, address: object, name: str, *, key_field: str = "") -> None:
        """Name an address this index was built before.

        For the one caller that MINTS: a request that adds a street and then a house under
        it needs the second lookup to see the first, and the index is memoized on the
        store's mtime — which has not changed yet, since the append is still in flight.
        Rebuilding it between the two costs the whole 45,000-node read.

        Deliberately additive and deliberately not persistent. This says what the index
        would say if it were rebuilt right now; it writes nothing, and the next rebuild
        reads the same fact off the document the mint appended to.
        """
        token = as_text(address)
        if not token or not as_text(name):
            return
        self._local[token] = as_text(name)
        space = as_text(key_field)
        if space:
            self._by_key.setdefault(space, set()).add(token)

    def key_fields(self) -> tuple[str, ...]:
        """The address spaces this index names into, most-named first."""
        return tuple(
            sorted(self._by_key, key=lambda k: (-len(self._by_key[k]), k))
        )

    def addresses(self, *, key_field: str = "") -> set[str]:
        """Every address named in one space, or in all of them when unqualified."""
        token = as_text(key_field)
        if token:
            return set(self._by_key.get(token, ()))
        return set(self._local) | set(self._shared)


EMPTY_INDEX = NameIndex({}, {})

#: How many disagreements to keep verbatim. Bounded because a corrupt corpus could produce
#: one per row; the COUNT is always exact, only the sample is capped.
CONFLICT_SAMPLE_MAX = 64


class _Names:
    """``address -> name`` under first-writer-wins, keeping what it turned down.

    Reading `address_nodes` took the registrar's name tables from 7,054 addresses to
    49,044, and with them came the first measured collision: `3-2-3-17-77-2-6-1-1` is
    *one street token* in `address_nodes` and *another* in
    `administrative`. Document-name order settles which one renders — stable and
    reproducible, which is all a tie-break can be — but it does not settle which is TRUE,
    and a resolver that silently picked one would have made a data defect invisible at
    exactly the moment it started mattering. So the loser is kept and counted.
    """

    def __init__(self) -> None:
        self.names: dict[str, str] = {}
        self.sources: dict[str, str] = {}
        #: ``key_field -> the addresses named in that space``. An msn space and an lcl
        #: space share this index and must never share a TREE: `1-1-1` is a legal class in
        #: the registrar's lcl and an employee class in a farm's. Sets of pointers to keys
        #: the names map already holds, so this is ~2 MB for 49,044 addresses.
        self.by_key: dict[str, set[str]] = {}
        self.conflicts: list[tuple[str, str, str, str, str]] = []
        self.conflict_count = 0

    def offer(self, address: str, name: str, *, source: str, key_field: str = "") -> None:
        if key_field:
            self.by_key.setdefault(key_field, set()).add(address)
        held = self.names.get(address)
        if held is None:
            self.names[address] = name
            self.sources[address] = source
            return
        if held == name:
            return
        self.conflict_count += 1
        if len(self.conflicts) < CONFLICT_SAMPLE_MAX:
            self.conflicts.append((address, held, self.sources.get(address, ""), name, source))


def _pick(raw: Any, *, sandbox: str) -> dict[str, str]:
    """The key-field and title cells of one row head, keyed by LOGICAL field name.

    Every field is named through the decoder ring, never by marker literal — ``rf.3-1-3``
    is `title` in the registrar and `coordinate` in the farms, and a reader that forgot
    that hid 469 of 471 geometry documents from every geospatial tool on 2026-08-06.

    The head comes from :func:`~archetype_shape._row_head`, the same function
    :func:`~archetype_shape.row_shape` uses, so a row's picks and its shape can never
    disagree about which cells exist.
    """
    picked: dict[str, str] = {}
    for marker, magnitude in iter_marker_pairs(ash._row_head(raw)):
        field = ash._field_name(as_text(marker), sandbox=sandbox)
        if field in KEY_FIELDS:
            picked.setdefault(field, as_text(magnitude))
        elif field == NAME_FIELD:
            picked.setdefault(NAME_FIELD, decode_label(magnitude))
    return picked


def _names_something(registry: arc.ArchetypeRegistry, shape: ash.RowShape) -> bool:
    """Could a row of this shape ever be part of a name table?

    :func:`_commit` keeps a row only when a name-table archetype covers its shape, so a
    row no such archetype covers cannot survive and need not be picked — its title is
    never decoded and its cells are never held.

    Measured, this is a modest saving and not the reason the fold is affordable: 3,076 of
    56,592 registrar + taxonomy rows are skipped (5.4%), the largest group being
    `registrar/network_sources`' 472. It is kept because it makes the cost proportional to
    NAME-TABLE rows rather than to every row in the sandbox, which is the property that
    holds if a large document of some other kind arrives later.

    The document's own shape census still counts every row: what a document IS depends on
    all of it, including the rows that will be dropped.
    """
    return any(name in NAME_TABLE_ARCHETYPES for name in registry.match_row(shape))


@dataclass(frozen=True)
class NameTable:
    """One document that contributed names, and what it turned out to be.

    Recorded because the fold already knows it. Asking later "is this document a name
    table, and over which address space?" would otherwise mean reading the document —
    which for `address_nodes` is 27 MB and 203 MB of row objects. The address-space
    browser needs exactly this and nothing else from it.
    """

    sandbox: str
    name: str
    archetype: str
    key_field: str
    named: int

    @property
    def source(self) -> str:
        return f"{self.sandbox}/{self.name}"


def _commit(
    shapes: Counter,
    picks: list[tuple[ash.RowShape, dict[str, str]]],
    *,
    registry: arc.ArchetypeRegistry,
    out: _Names,
    sandbox: str,
    name: str,
) -> NameTable | None:
    """Decide what a document IS from its shape census, then keep its names if it names.

    Split from the walk so both read paths — assembled documents and streamed rows —
    commit through one function. Two extraction rules that agreed today would drift, and
    the streaming path exists precisely to produce the SAME index more cheaply.
    """
    archetype_name = registry.primary_archetype_of(shapes)
    key_field = NAME_TABLE_ARCHETYPES.get(archetype_name)
    archetype = registry.get(archetype_name) if key_field else None
    if archetype is None:
        return None
    source = f"{sandbox}/{name}"
    named = 0
    for shape, picked in picks:
        if not archetype.covers(shape):
            continue
        address, title = picked.get(key_field, ""), picked.get(NAME_FIELD, "")
        if address and title:
            out.offer(address, title, source=source, key_field=key_field)
            named += 1
    return NameTable(
        sandbox=sandbox, name=name, archetype=archetype_name, key_field=key_field, named=named
    )


def _index_document(
    document: Any, *, registry: arc.ArchetypeRegistry, out: _Names, name: str = ""
) -> NameTable | None:
    """Fold one ASSEMBLED document. The path a store that cannot stream rows takes."""
    sandbox = ash.sandbox_of(document)
    if not sandbox:
        return None
    shapes: Counter = Counter()
    picks: list[tuple[ash.RowShape, dict[str, str]]] = []
    for row in getattr(document, "rows", ()) or ():
        raw = row.get("raw") if isinstance(row, dict) else getattr(row, "raw", None)
        shape = ash.row_shape(raw, sandbox=sandbox)
        shapes[shape] += 1
        if _names_something(registry, shape):
            picks.append((shape, _pick(raw, sandbox=sandbox)))
    return _commit(
        shapes, picks, registry=registry, out=out, sandbox=sandbox,
        name=name or as_text(getattr(document, "canonical_name", "")),
    )


def _fold_streamed(
    store: Any, *, tenant_id: str, sandbox: str, registry: arc.ArchetypeRegistry,
    out: _Names,
) -> list[NameTable]:
    """Fold a sandbox row by row, committing at each document boundary.

    Rows arrive grouped by document, so at most one document's shape census and picks are
    held at a time — and those are the small half. `address_nodes` folds at +68 MB here
    against +237 MB assembled, which is the whole point.
    """
    tables: list[NameTable] = []
    current = ""
    name = ""
    shapes: Counter = Counter()
    picks: list[tuple[ash.RowShape, dict[str, str]]] = []
    for document_id, document_name, raw in store.iter_document_rows_by_sandbox(
        tenant_id=tenant_id, sandbox=sandbox
    ):
        if document_id != current:
            if current:
                table = _commit(
                    shapes, picks, registry=registry, out=out, sandbox=sandbox, name=name
                )
                if table is not None:
                    tables.append(table)
            current, name = document_id, document_name
            shapes, picks = Counter(), []
        shape = ash.row_shape(raw, sandbox=sandbox)
        shapes[shape] += 1
        if _names_something(registry, shape):
            picks.append((shape, _pick(raw, sandbox=sandbox)))
    if current:
        table = _commit(shapes, picks, registry=registry, out=out, sandbox=sandbox, name=name)
        if table is not None:
            tables.append(table)
    return tables


def _fold_local_domain(
    store: Any, *, tenant_id: str, sandbox: str, msn_id: str, out: _Names,
) -> NameTable | None:
    """The sandbox's OWN local domain log, folded as the lcl name table it already is.

    **Why this is not an entry in** :data:`NAME_TABLE_ARCHETYPES`. `local_domain_log`
    declares ``lcl_id, title, lcl_id``, and only the registrar stack writes that. Which
    field spells a TYPE is a fact about the anchor's namespace, not about the log --
    :func:`micyte.core.datum_ops.local_domain.domain_markers` says it plainly: "the
    farm/taxonomy stack carries a type on ``txa_id`` while the registrar's ``lcl`` is a
    pure vocabulary riding ``lcl_id``". So a farm-stack tree folds to
    ``txa_id,title,txa_id``, which `local_domain_log` does not cover, and adding a second
    archetype for the same rows would mint a twin of a shape that already has a name.

    Measured live 2026-08-25, definition rows covered by `local_domain_log`:

    ========  =======  =============================================================
    registrar  66/72   the registrar stack -- covered
    glyph       1/18   likewise
    grantor     0/36   the farm stack -- NOT covered, and so unnamed
    agnet       0/36   likewise
    ========  =======  =============================================================

    What that cost: nothing in the grantor sandbox named ``1-3-1``, so
    ``label("1-3-1", key_field="lcl_id")`` fell through to the SHARED fill and answered
    **farmers_market** -- the taxonomy's name for a different sandbox's ``1-3-1``. The
    grantor's own log calls it `domain_kept`. An lcl space is local, which is what the L
    in lcl means, and a shared table answering for one is a broken link that looks right.

    So the log is read by the reader that already handles every namespace -- and offered
    LAST, which is the deliberate half of this. Offered FIRST it would OUTRANK the tables
    already naming a sandbox, and measured on the live store that is a visible regression:
    `taxonomy/txa` calls ``1`` *cytota* -- the txa root a browser draws -- while the
    taxonomy's own log calls it *documents*, its meta root. Both are true, of different
    address spaces; the map is flat; and the caller that renders the taxonomy tree does
    not qualify. So the log FILLS what nothing named, which is every farm-stack lcl node
    and nothing else, and changes no label anything already resolved. The disagreements it
    does find are still counted in :attr:`NameIndex.conflicts` -- 98 store-wide before
    this, 100 in `registrar` and 100 in `taxonomy` after, all of them the meta root
    against an msn or txa table.
    """
    from micyte.core.datum_ops import local_domain as ld

    from ._viewscope import local_domain_document_id, read_document

    # Asking for ONE document by name goes through the documents index, which a store has
    # or has not. A store without it contributes nothing, and that is an ABSENCE, not a
    # failure: recording it would make every in-memory store look broken, and the whole
    # point of `failed` is that an empty sandbox and a broken one stop looking alike.
    if not callable(getattr(store, "_connect", None)):
        return None
    document_id = local_domain_document_id(
        store, tenant_id=tenant_id, sandbox=sandbox, msn_id=msn_id)
    if not document_id:
        return None
    log = ld.read_log(read_document(store, tenant_id=tenant_id, document_id=document_id))
    source = f"{sandbox}/{LOCAL_DOMAIN_TABLE}"
    named = 0
    for node, entry in log.entries.items():
        label = as_text(entry.label)
        if not (node and label):
            continue
        out.offer(node, label, source=source, key_field=LOCAL_DOMAIN_KEY_FIELD)
        named += 1
    if not named:
        return None
    return NameTable(sandbox=sandbox, name=LOCAL_DOMAIN_TABLE,
                     archetype=LOCAL_DOMAIN_TABLE, key_field=LOCAL_DOMAIN_KEY_FIELD,
                     named=named)


def _fold_assembled(
    store: Any, *, tenant_id: str, sandbox: str, registry: arc.ArchetypeRegistry,
    out: _Names, max_payload_bytes: int,
) -> list[NameTable]:
    tables: list[NameTable] = []
    documents = store.read_documents_by_sandbox(
        tenant_id=tenant_id, sandbox=sandbox, max_payload_bytes=max_payload_bytes
    )
    for document in documents:
        table = _index_document(
            document, registry=registry, out=out, name=as_text(document.canonical_name)
        )
        if table is not None:
            tables.append(table)
    return tables


#: The folded SHARED sandboxes (`SHARED_NAME_SANDBOXES`), per (tenant, sandbox, store
#: version): the `_Names` partial and the tables it yielded, merged read-only into every
#: index built after. Four: two shared sandboxes for two store versions.
_SHARED_FOLD_LOCK = threading.Lock()
_SHARED_FOLD: OrderedDict[tuple[str, str, int], tuple[Any, list[Any]]] = OrderedDict()
_SHARED_FOLD_MAX = 4


def _shared_fold(tenant_id: str, token: str, store_version: int) -> tuple[Any, list[Any]] | None:
    key = (tenant_id, token, store_version)
    with _SHARED_FOLD_LOCK:
        hit = _SHARED_FOLD.get(key)
        if hit is not None:
            _SHARED_FOLD.move_to_end(key)
    return hit


def _remember_shared_fold(
    tenant_id: str, token: str, store_version: int, partial: Any, found: list[Any]
) -> None:
    key = (tenant_id, token, store_version)
    with _SHARED_FOLD_LOCK:
        for stale in [k for k in _SHARED_FOLD if k[:2] == key[:2] and k != key]:
            _SHARED_FOLD.pop(stale, None)
        _SHARED_FOLD[key] = (partial, list(found))
        _SHARED_FOLD.move_to_end(key)
        while len(_SHARED_FOLD) > _SHARED_FOLD_MAX:
            _SHARED_FOLD.popitem(last=False)


def build_name_index(
    store: Any,
    *,
    tenant_id: str,
    sandbox: str,
    registry: arc.ArchetypeRegistry,
    max_payload_bytes: int = NAME_TABLE_MAX_BYTES,
    msn_id: str = "",
) -> NameIndex:
    """Fold every name table reachable from ``sandbox`` into one address -> name map.

    A store that can stream rows is read in full; one that cannot is read under
    ``max_payload_bytes`` and yields a smaller index, which
    :attr:`NameIndex.streamed` records.

    ``msn_id`` says WHICH sandbox when a name is held by more than one instance -- a
    sandbox is addressed by (msn_id, sandbox), and only the local domain read needs it,
    because it asks for one document by name rather than reading the sandbox whole.
    """
    local: dict[str, str] = {}
    shared: dict[str, str] = {}
    tables: list[NameTable] = []
    by_key: dict[str, set[str]] = {}
    conflicts: list[tuple[str, str, str, str, str]] = []
    conflict_count = 0
    failed: list[tuple[str, str]] = []
    seen: set[str] = set()
    streamed = callable(getattr(store, "iter_document_rows_by_sandbox", None))
    try:
        store_version = int(store._db_mtime_ns()) if streamed else 0
    except Exception:
        store_version = 0
    for token in (sandbox, *SHARED_NAME_SANDBOXES):
        if not token or token in seen:
            continue
        seen.add(token)
        # A SHARED sandbox's fold is the same for every asking sandbox and every instance
        # — `registrar` (address_nodes: ~42,000 rows) and `taxonomy` are read whole and
        # depend on nothing but the store — so it is folded once per store version and
        # merged from memory after that. Measured 2026-09-20: the operator's profile asks
        # for two indexes (its `system` and its `grantor` sandboxes) and each re-folded
        # the registrar, 11.6 s on a cold worker. Only the streamed fold is remembered:
        # the assembled one is bounded by `max_payload_bytes`, a caller's choice.
        remembered = (
            _shared_fold(tenant_id, token, store_version)
            if streamed and token != sandbox and store_version else None
        )
        if remembered is not None:
            partial, found = remembered
        else:
            # Folded aside and merged on success: a sandbox that fails half way through
            # must contribute nothing rather than however much it managed, or the index
            # depends on where the read broke.
            partial = _Names()
            try:
                if streamed:
                    found = _fold_streamed(
                        store, tenant_id=tenant_id, sandbox=token, registry=registry, out=partial
                    )
                else:
                    found = _fold_assembled(
                        store, tenant_id=tenant_id, sandbox=token, registry=registry,
                        out=partial, max_payload_bytes=max_payload_bytes,
                    )
            except Exception as exc:
                # A sandbox that does not exist contributes nothing, and that is fine. A
                # sandbox that BREAKS also contributes nothing, and that is not — it is
                # indistinguishable from an empty one unless it is recorded. Measured: a
                # reader bug that raised on 4 rows of one farm's `lcl` dropped all 63
                # of that sandbox's local names, and the index reported 49,044 either way.
                failed.append((token, f"{type(exc).__name__}: {exc}"[:200]))
                found = []
            else:
                if streamed and token != sandbox and store_version:
                    _remember_shared_fold(tenant_id, token, store_version, partial, found)
        # The sandbox's OWN log, and only its own: an lcl address is LOCAL, so folding
        # another sandbox's log into `shared` would BE the defect this closes.
        #
        # AFTER the archetype fold, so the log fills gaps rather than outranking a table
        # that already named something — and in its OWN guard, because it is its own read.
        # A sandbox whose archetype fold raises (`system` is held by four instances, and a
        # sandbox-wide read of it is ambiguous) would otherwise lose its node names to a
        # failure that has nothing to do with them.
        if token == sandbox:
            try:
                own = _fold_local_domain(
                    store, tenant_id=tenant_id, sandbox=token, msn_id=msn_id, out=partial)
            except Exception as exc:
                failed.append((f"{token}/{LOCAL_DOMAIN_TABLE}",
                               f"{type(exc).__name__}: {exc}"[:200]))
            else:
                if own is not None:
                    found = [*found, own]
        into = local if token == sandbox else shared
        for address, name in partial.names.items():
            into.setdefault(address, name)
        for field_name, found_addresses in partial.by_key.items():
            by_key.setdefault(field_name, set()).update(found_addresses)
        tables.extend(found)
        conflict_count += partial.conflict_count
        conflicts.extend(partial.conflicts[: max(0, CONFLICT_SAMPLE_MAX - len(conflicts))])
    return NameIndex(
        local, shared, tables=tuple(tables), by_key=by_key, streamed=streamed,
        conflicts=tuple(conflicts), conflict_count=conflict_count,
        failed=tuple(failed),
    )


#: Bounded memo, for the reason every cache in this program is bounded: an unbounded one
#: cost +293 MiB per test on 2026-08-05. Keyed on the sandbox and the store's mtime, so any
#: write invalidates it rather than serving a name the store no longer holds.
_INDEX_CACHE: dict[tuple[str, str, int], NameIndex] = {}
_INDEX_CACHE_MAX = 4


def name_index_for(
    store: Any, *, tenant_id: str, sandbox: str, registry: arc.ArchetypeRegistry
) -> NameIndex:
    try:
        mtime = store._db_mtime_ns()
    except Exception:
        mtime = 0
    # The msn is part of the KEY, because a sandbox is addressed by (msn, sandbox) and the
    # index is built from that sandbox's documents. Keyed on the name alone, the first
    # instance to be rendered populated the entry and every other instance was served ITS
    # names — measured: the client instance's job table returned 43 rows alone and 0 when FND rendered
    # first in the same process. A cache keyed less specifically than the thing it caches
    # is a correctness bug that only appears under a particular order.
    from micyte.core.instance_scope import resolve_msn

    msn_id = resolve_msn("")
    key = (tenant_id, msn_id, sandbox, mtime)
    hit = _INDEX_CACHE.get(key)
    if hit is not None:
        return hit
    index = build_name_index(
        store, tenant_id=tenant_id, sandbox=sandbox, registry=registry, msn_id=msn_id)
    if len(_INDEX_CACHE) >= _INDEX_CACHE_MAX:
        _INDEX_CACHE.pop(next(iter(_INDEX_CACHE)))
    _INDEX_CACHE[key] = index
    return index


__all__ = [
    "EMPTY_INDEX",
    "KEY_FIELDS",
    "LOCAL_DOMAIN_KEY_FIELD",
    "LOCAL_DOMAIN_TABLE",
    "NAME_FIELD",
    "NAME_TABLE_ARCHETYPES",
    "NAME_TABLE_MAX_BYTES",
    "SHARED_NAME_SANDBOXES",
    "NameIndex",
    "NameTable",
    "build_name_index",
    "name_index_for",
]
