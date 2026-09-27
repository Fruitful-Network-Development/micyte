"""The AGNET channel — the instance's agricultural network, open to any caller.

First manifestation of the hosted-channel convention (2026-08-02 §4). OPEN
access. Named ``produce_market`` until 2026-08-04, after its first data rather
than after what it is: the surface this instance offers the outside world, which
the network-cooperation convention (2026-08-04) has taking ACCOUNTS. The old
public URL ``micyte.com/channels/produce-market`` redirects; the open session
route moved with the id, because the id IS the route. Its sandbox holds market records for three Ohio produce auctions (the
§2f interim posture: records about entities that have no instance of their own
live in the channel sandbox, keyed on the HOSTING instance's msn, and retire to
sources when the subject claims an instance).

* **SUPPLY** is present and honestly empty: it states what would populate it
  (instance offerings via the ``commerce_offering`` port published to this
  channel as sources) and that no source publishes it yet. An empty tab with a
  stated reason over a hidden tab — coverage is claimed, never implied.
* **DEMAND** renders a per-day pricing view for ONE market at a time, grouped by
  the product each entry resolves to. Each entry is a distinct point (average
  price × quantity, with the low–high spread), never merged — the same-day
  spread is exactly what the histogram exists to show.
* **TAXONOMY** is the txa classification tree the products resolve THROUGH —
  the responsibility absorbed from the ``taxonomy_domain`` tool (2026-08-03).
  A price series is only comparable across reports because both entries name the
  same plant, so the classification belongs beside the prices rather than on a
  website holding a second copy of it. Read through DECLARED sources like every
  other cross-sandbox read here, and built ONLY for its own tab: 4,096 nodes is a
  quarter of a megabyte and the viewer refetches the whole session on every day
  pick.

Two things the demand view refuses to blur (2026-08-03):

**Markets are never pooled.** Four publishers describe three auctions, and two
of them describe the same auction (Mt Hope) over overlapping years. Averaging
County Line's tomatoes with Mt Hope's would compare two markets, and adding the
site's Mt Hope report to USDA's would count one sale twice. A session reads one
market and is told what the others are.

**Grouping is by the resolved product, not by the report's wording.** Entries
carry ``rf.3-1-5``, resolved at ingest against ``product_profiles`` and through
it to a ``taxonomy.txa`` node, which is what collapsed 2,643 County Line strings
into 217 products. An entry that never resolved is still shown, under the
report's own words and marked unaligned — a price nobody could classify is
still a price somebody paid.

The payload STATES its coverage (documents read, lots parsed, lots on the
selected day, exclusions) per the agro_calendar precedent, and cross-checks
the code's declared access class against the sandbox's ``channel_profile`` —
a drift between the two is reported, not resolved silently.

Money never leaves integer cents in this payload; display formatting is the
renderer's job. The fiat marker is DISCOVERED from the channel anchor
(``find_fiat_chain``), never addressed by literal.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from micyte.core.datum_ops.datum_resolve import decode_label
from micyte.core.datum_ops.fiat_datum import find_fiat_chain
from micyte.core.document_naming import parse_canonical_document_id
from micyte.core.sources import resolve_sources

from . import register

SESSION_SCHEMA = "mycite.v2.channel.session.v1"
CONTAINER = "channel_session"
#: The demand view's **resource binary** (convention §5). Versioned separately from the
#: session: the session is a rendering and may change freely, while this is an artifact
#: consumers hold, so a change to its shape is a change every holder must notice.
PROJECTION_SCHEMA = "mycite.v2.channel.demand.projection.v1"
#: ``<sandbox>-demand.mss``. The suffix is part of the NAME, not of the filename: the
#: exporter, ``held_stills()``, the card's allowlist and the serve route
#: ``/__mss/public/stills/<name>.mss`` all key on one identifier, and a still named
#: ``agnet`` must not collide with the projection derived from the same sandbox.
PROJECTION_SUFFIX = "-demand"

_TAXON = "rf.3-1-1"
_TITLE = "rf.3-1-2"
_PRODUCT = "rf.3-1-5"
_NOMINAL = "rf.3-1-7"
# The taxonomy-sandbox babelettes the taxonomy_domain tool reads, by the same
# addresses (field_registry TAXONOMY common_name / icon_ref). Named here for the
# same reason the four above are: this module states the cells it reads.
_COMMON = "rf.3-1-9"
_ICON = "rf.3-1-10"
#: ``observed_by`` (field_registry, uniform across namespaces): the DOCUMENT-LOCAL
#: address of the observer row a record came from. Provenance stopped being a filename
#: on 2026-08-05; this is where it went.
_OBSERVED_BY = "rf.3-1-29"
#: ``<observer>_lot_<yyyymmdd>_<n>``. The observer rides in the label as well as in the
#: cell so the two can disagree — which is the only way a bad rewrite leaves evidence.
_LOT_LABEL_RE = re.compile(r"^(?P<observer>[a-z0-9_]+)_lot_(\d{4})(\d{2})(\d{2})_\d+$")
#: The rudi header every market-record document carries. Documents used to be found by
#: the ``market_lots`` NAME PREFIX, which was never a denotation — it only looked like
#: one because the ingest happened to spell it that way.
_RECORD_RUDI = "market_lots"
_RUDI_ADDRESS = "0-0-1"
_OBSERVER_PREFIX = "4-11-"


def _pretty(title: str) -> str:
    """``lens_esculenta`` -> ``Lens esculenta`` — the tool's own fallback label."""
    text = str(title or "").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else ""


def _lot_rows(document: Any):
    for row in getattr(document, "rows", ()) or ():
        if str(row.datum_address).startswith("4-10-"):
            yield row


def _label_of(row: Any) -> str:
    raw = row.raw
    if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[-1], list) and raw[-1]:
        return str(raw[-1][0])
    return ""


def _lot_day(row: Any) -> str:
    match = _LOT_LABEL_RE.match(_label_of(row))
    return f"{match.group(2)}-{match.group(3)}-{match.group(4)}" if match else ""


def _observed_by(row: Any) -> str:
    """The observer row this record cites, as a document-local address.

    Read from the cell rather than parsed out of the label: the label carries the
    observer too, and the point of two denotations is that neither one is the reader's
    only source. ``verify_entity_profile_derivation`` is where they are checked against
    each other.
    """
    head = row.raw[0] if isinstance(row.raw, list) and row.raw else []
    for i in range(1, len(head) - 1, 2):
        if str(head[i]) == _OBSERVED_BY:
            return str(head[i + 1])
    return ""


def _is_record_document(document: Any) -> bool:
    """Does this document hold market records? Asked of its rudi header, not its name."""
    for row in getattr(document, "rows", ()) or ():
        if str(row.datum_address) == _RUDI_ADDRESS:
            return _label_of(row) == _RECORD_RUDI
    return False


def _observers(document: Any) -> dict[str, dict[str, str]]:
    """``4-11-N`` -> the observer that row denotes.

    An observer is *who published this record*, which is not the same fact as *whose
    auction it is*: two independent parties publish reports about the Mt Hope auction,
    and over 218 shared days 1,689 of their (day, product) pairs agree on price to
    within 1%. Same sale, two observers. Pooling them would count it twice.
    """
    out: dict[str, dict[str, str]] = {}
    for row in getattr(document, "rows", ()) or ():
        address = str(row.datum_address)
        if not address.startswith(_OBSERVER_PREFIX):
            continue
        head = row.raw[0] if isinstance(row.raw, list) and row.raw else []
        titles: list[str] = []
        key = msn = entries = ""
        for i in range(1, len(head) - 1, 2):
            marker, value = str(head[i]), str(head[i + 1])
            if marker == _PRODUCT and not key:
                key = value
            elif marker == _TITLE:
                titles.append(decode_label(value))
            elif marker == "rf.3-1-4" and not msn:
                msn = value
            elif marker == _NOMINAL and not entries:
                entries = decode_label(value)
        if key:
            out[address] = {
                "source_key": key,
                # Positional, per the document's own row_semantics: label, publisher,
                # granularity, provenance.
                "label": titles[0] if titles else key,
                "publisher": titles[1] if len(titles) > 1 else "",
                "granularity": titles[2] if len(titles) > 2 else "",
                "provenance": titles[3] if len(titles) > 3 else "",
                "observer_msn": msn,
                "entries": entries,
            }
    return out


def _decode_lot(row: Any, fiat_marker: str) -> dict[str, Any] | None:
    """One lot row -> {product, size, grade, product_id, quantity, prices}.

    Positional semantics per the ingest's stated row_semantics: titles are
    (item text, pack) and optionally a third (grade); money is (low, high,
    average). ``rf.3-1-5`` carries the market product the entry was resolved to
    and is ABSENT when it did not resolve — which is a fact the payload reports,
    not one it papers over. A row that does not carry the required shape is
    excluded AND COUNTED — never silently skipped.
    """
    head = row.raw[0] if isinstance(row.raw, list) and row.raw else []
    titles: list[str] = []
    nominals: list[str] = []
    money: list[str] = []
    product_id = observed_by = ""
    i = 1
    while i < len(head) - 1:
        marker, value = str(head[i]), head[i + 1]
        if marker == _TITLE:
            titles.append(str(value))
        elif marker == _NOMINAL:
            nominals.append(str(value))
        elif marker == _PRODUCT and not product_id:
            product_id = str(value)
        elif marker == _OBSERVED_BY and not observed_by:
            observed_by = str(value)
        elif marker == fiat_marker:
            money.append(str(value))
        i += 2
    if len(titles) < 2 or not nominals or len(money) != 3:
        return None
    try:
        prices = [int(m) for m in money]
    except ValueError:
        return None
    return {
        "product": decode_label(titles[0]),
        "size": decode_label(titles[1]),
        "grade": decode_label(titles[2]) if len(titles) > 2 else "",
        "product_id": product_id,
        "observed_by": observed_by,
        "quantity": decode_label(nominals[0]),
        "low_cents": prices[0],
        "high_cents": prices[1],
        "average_cents": prices[2],
        "lot": _label_of(row),
    }


def _product_titles(documents: dict[str, Any]) -> dict[str, dict[str, str]]:
    """product_id -> {title, taxon} from the channel's own product_profiles.

    Absent document == an empty map, which makes every entry fall back to the
    report's own words. The view degrades to what it used to be instead of
    failing, and the coverage block says the profiles were not found.
    """
    document = documents.get("product_profiles")
    if document is None:
        return {}
    out: dict[str, dict[str, str]] = {}
    for row in getattr(document, "rows", ()) or ():
        if not str(row.datum_address).startswith("4-12-"):
            continue
        head = row.raw[0] if isinstance(row.raw, list) and row.raw else []
        product_id = taxon = title = ""
        for i in range(1, len(head) - 1, 2):
            marker, value = str(head[i]), str(head[i + 1])
            if marker == _PRODUCT and not product_id:
                product_id = value
            elif marker == _TAXON and not taxon:
                taxon = value
            elif marker == _TITLE and not title:
                title = decode_label(value)
        if product_id:
            out[product_id] = {"title": title or product_id, "taxon": taxon}
    return out


def _entries_by_product(lot_documents: dict[str, Any]) -> dict[str, int]:
    """product_id -> how many of this channel's entries resolved to it.

    Every market, not the selected one: the tree is a statement about what the
    channel holds, not about the day you happen to be looking at. Cheap enough for
    the tab that asks for it (0.1s over 47k rows) because it reads the product cell
    and stops — no decode, no money, no day.
    """
    counts: dict[str, int] = {}
    for document in lot_documents.values():
        for row in _lot_rows(document):
            head = row.raw[0] if isinstance(row.raw, list) and row.raw else []
            for i in range(1, len(head) - 1, 2):
                if str(head[i]) == _PRODUCT:
                    product_id = str(head[i + 1])
                    if product_id:
                        counts[product_id] = counts.get(product_id, 0) + 1
                    break
    return counts


def _scan_markets(
    lot_documents: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[tuple[Any, str]]], list[str]]:
    """``(markets, docs_by_market, notes)`` — who publishes records to this channel.

    Extracted from :func:`build_session_payload` so the session and the resource binary
    cannot disagree about what a market *is*. They are two readers of one channel, and a
    picker that offers three markets against a binary that indexes four is a surface
    where every number is individually right and the pair is wrong.
    """
    markets: dict[str, dict[str, Any]] = {}
    docs_by_market: dict[str, list[tuple[Any, str]]] = {}
    notes: list[str] = []
    for doc in lot_documents.values():
        meta = dict(getattr(doc, "document_metadata", {}) or {})
        subject = str(meta.get("subject") or "")
        subject_msn = str(meta.get("subject_msn") or "")
        found = _observers(doc)
        if not found:
            # A record document with no observer row cannot say who published it. It is
            # reported rather than dropped: an unattributed record is still a record,
            # and a silently missing market is how coverage starts being implied.
            notes.append(f"{doc.document_name!r} declares no observer rows; its "
                         "records are shown as one unattributed market")
            found = {"": {"source_key": subject or doc.document_name,
                          "label": subject or doc.document_name}}
        for address, observer in found.items():
            key = observer["source_key"]
            try:
                declared = int(observer.get("entries") or 0)
            except (TypeError, ValueError):
                declared = 0
            entry = markets.setdefault(key, {
                "source_key": key,
                "label": observer.get("label") or key,
                "publisher": observer.get("publisher", ""),
                "granularity": observer.get("granularity", ""),
                "provenance": observer.get("provenance", ""),
                "observer_msn": observer.get("observer_msn", ""),
                "subject": subject,
                "subject_msn": subject_msn,
                "documents": 0, "entries": 0,
            })
            entry["documents"] += 1
            # A row that does not declare its count gets counted. Trusting the
            # declaration blindly is how a total silently reads zero — the fast path is
            # an optimisation, not a licence to report a number nobody wrote down.
            entry["entries"] += declared or sum(
                1 for row in _lot_rows(doc) if _observed_by(row) == address)
            docs_by_market.setdefault(key, []).append((doc, address))
    return markets, docs_by_market, notes


# --------------------------------------------------------------------------- #
# The resource binary
# --------------------------------------------------------------------------- #
class _Intern:
    """A string table and the indexes into it — the whole compression story.

    The lot columns repeat themselves enormously: 47,569 entries draw on 561 days, 218
    product ids, 3,945 product strings, 67 pack sizes, 12 grades and 2 observers. Storing
    each cell as an index into a table of its distinct values takes the payload from 5.0 MB
    to 1.9 MB, and — the part that matters more — leaves the consumer holding integer
    arrays rather than 47,569 objects, so a day filter is a scan with no allocation.
    """

    def __init__(self) -> None:
        self.values: list[str] = []
        self._index: dict[str, int] = {}

    def __call__(self, value: str) -> int:
        found = self._index.get(value)
        if found is None:
            found = self._index[value] = len(self.values)
            self.values.append(value)
        return found


def build_demand_projection(
    documents: dict[str, Any],
    *,
    source_msn: str,
    sandbox: str,
    name: str,
    created_at: str = "",
) -> dict[str, Any]:
    """The demand view as a **resource binary** — convention §5's "projection of documents".

    Not a still, and the distinction is the whole design. A still carries rows *verbatim*
    so each document's ``version_hash`` re-derives from what it holds; that faithfulness is
    what makes it the right artifact to hand another instance, and it is why this sandbox's
    still is 2.35 MB framed and **76 MB inflated**. No browser can hold that. A projection
    is *derived*: it keeps what the demand view reads and drops everything else, and it is
    identified by the hashes of the documents it was derived FROM rather than by re-deriving
    them. The same data measures 1.9 MB inflated, 0.35 MB framed — less on the wire than the
    still and forty times less in memory.

    **Derived by the same helpers the session builder uses**, deliberately: ``_scan_markets``
    for the markets, ``_decode_lot`` for every entry, ``_lot_day`` for the day,
    ``_product_titles`` for the dictionary, and ``find_fiat_chain`` for the marker prices are
    denominated in. A second implementation of any of those would be a fork with nothing
    gating it, and the consumer reading this binary would slowly stop agreeing with the
    instance that published it.

    Every entry is carried — including the ones that never resolved to a product, for the
    same reason the session shows them. Rows that cannot be decoded at all are COUNTED into
    ``undecodable`` rather than quietly dropped.
    """
    anchor = documents.get("anchor")
    chain = find_fiat_chain(anchor) if anchor is not None else None
    if chain is None:
        raise ValueError(
            f"{sandbox!r} anchor defines no price datum; a demand projection whose money "
            "columns have nothing to say what they measure would be a table of bare "
            "integers"
        )

    lot_documents = {n: doc for n, doc in documents.items() if _is_record_document(doc)}
    markets, docs_by_market, notes = _scan_markets(lot_documents)
    titles = _product_titles(documents)

    market_t, day_t, pid_t = _Intern(), _Intern(), _Intern()
    product_t, size_t, grade_t, qty_t = _Intern(), _Intern(), _Intern(), _Intern()
    cols: dict[str, list[int]] = {k: [] for k in (
        "market", "day", "pid", "product", "size", "grade", "qty", "low", "high", "avg")}
    undecodable = 0

    # Ordered by market then by the document's own row order, so the binary is
    # reproducible: the same documents must produce the same bytes or a consumer's
    # update-check churns on nothing.
    for market_key in sorted(docs_by_market):
        market_ix = market_t(market_key)
        for doc, address in docs_by_market[market_key]:
            for row in _lot_rows(doc):
                if _observed_by(row) != address:
                    continue
                lot = _decode_lot(row, chain.marker)
                if lot is None:
                    undecodable += 1
                    continue
                cols["market"].append(market_ix)
                cols["day"].append(day_t(_lot_day(row)))
                cols["pid"].append(pid_t(lot["product_id"]))
                cols["product"].append(product_t(lot["product"]))
                cols["size"].append(size_t(lot["size"]))
                cols["grade"].append(grade_t(lot["grade"]))
                cols["qty"].append(qty_t(lot["quantity"]))
                cols["low"].append(lot["low_cents"])
                cols["high"].append(lot["high_cents"])
                cols["avg"].append(lot["average_cents"])

    ordered_markets = sorted(markets.values(), key=lambda m: (-m["entries"], m["source_key"]))
    return {
        "schema": PROJECTION_SCHEMA,
        "source_msn": source_msn,
        "sandbox": sandbox,
        "name": name,
        "created_at": created_at,
        # Discovered from the anchor, never hardcoded — and carried so a consumer can say
        # what its money columns MEAN rather than assuming cents.
        "fiat_marker": chain.marker,
        "markets": ordered_markets,
        "products": titles,
        "columns": {
            "market_v": market_t.values, "day_v": day_t.values, "pid_v": pid_t.values,
            "product_v": product_t.values, "size_v": size_t.values,
            "grade_v": grade_t.values, "qty_v": qty_t.values,
            **cols,
        },
        "entries": len(cols["day"]),
        "undecodable": undecodable,
        # The one coverage number a consumer cannot derive from the columns: how many
        # DOCUMENTS these entries were read out of. Everything else the coverage line
        # states — the totals, the product count, the market count — is a count of
        # something the consumer is holding.
        "record_documents": len(lot_documents),
        "notes": notes,
        # What this was derived FROM. §5: "identified by the hash of what it was derived
        # from" — so staleness is answerable against the live catalog without decoding a
        # byte, exactly as the still's manifest makes it answerable.
        "documents": [
            {"name": n,
             "mss_hash": "sha256:" + str(getattr(doc, "document_id", "")).rsplit(".", 1)[-1]}
            for n, doc in sorted(documents.items())
        ],
    }


#: Every column of a projection, and which are indexes into which string table. One
#: statement of the grammar, used by the exporter's self-check and by the reader.
PROJECTION_COLUMNS: dict[str, str] = {
    "market": "market_v", "day": "day_v", "pid": "pid_v", "product": "product_v",
    "size": "size_v", "grade": "grade_v", "qty": "qty_v",
    "low": "", "high": "", "avg": "",
}


def verify_demand_projection(projection: dict[str, Any]) -> list[str]:
    """Grammar check — every column the same length, every index inside its table.

    A ragged column is not a smaller table: it is a silently WRONG one, because the
    columns are joined by position and a short column shifts every row after it. Checked
    at export before the bytes are written, and again by the consumer after decode, because
    a projection read from another instance is read across a trust boundary.
    """
    problems: list[str] = []
    if projection.get("schema") != PROJECTION_SCHEMA:
        problems.append(f"unknown projection schema: {projection.get('schema')!r}")
    columns = projection.get("columns")
    if not isinstance(columns, dict):
        return [*problems, "projection has no columns object"]
    expected = projection.get("entries")
    for column, table in PROJECTION_COLUMNS.items():
        values = columns.get(column)
        if not isinstance(values, list):
            problems.append(f"column {column!r} is missing")
            continue
        if expected is not None and len(values) != expected:
            problems.append(
                f"column {column!r} has {len(values)} entries, declared {expected}")
        if not table:
            continue
        size = len(columns.get(table) or ())
        if values and (min(values) < 0 or max(values) >= size):
            problems.append(f"column {column!r} indexes outside {table} (size {size})")
    return problems


def _taxonomy_section(
    resolution: Any,
    *,
    titles: dict[str, dict[str, str]],
    traded: dict[str, int],
) -> dict[str, Any]:
    """The txa classification tree, read through the channel's DECLARED sources.

    The responsibility this channel absorbed from the ``taxonomy_domain`` tool. The
    tool reaches into the ``taxonomy`` sandbox by module constant; a channel may not
    — it resolves ``taxonomy_txa_registry`` (the node set and its scientific titles)
    and ``taxonomy_txa`` (common names and produce icons) by the names its manifest
    declares, or it does not get them. An undeclared source is a STATED gap here, in
    ``missing_documents``, exactly as the profiles tab states its own.

    Topology is DERIVED from the dotted txa address (parent = strip the last
    segment), the same derivation the tool and the site's tree both make, so nothing
    invents a parent column the datum does not carry.

    What makes this the *market's* tree rather than a transplanted one: every node
    that a product resolves to is marked ``traded`` and carries the products (with
    the entry counts that put them there), and ``expand_to`` opens the tree along
    exactly those lineages.
    """
    registry = resolution.document("taxonomy_txa_registry")
    source = resolution.document("taxonomy_txa")
    missing = [name for name, doc in (("taxonomy_txa_registry", registry),
                                      ("taxonomy_txa", source)) if doc is None]
    if registry is None:
        return {"loaded": True, "nodes": [], "expand_to": [], "totals": {},
                "missing_documents": missing, "sources": resolution.coverage()}

    scientific: dict[str, str] = {}
    for row in getattr(registry, "rows", ()) or ():
        if not str(row.datum_address).startswith("4-2-"):
            continue
        head = row.raw[0] if isinstance(row.raw, list) and row.raw else []
        node_id = title = ""
        for i in range(1, len(head) - 1, 2):
            marker, value = str(head[i]), str(head[i + 1])
            if marker == _TAXON and not node_id:
                node_id = value
            elif marker == _TITLE and not title:
                title = decode_label(value)
        if node_id:
            scientific[node_id] = title

    common: dict[str, str] = {}
    icons: dict[str, str] = {}
    for row in getattr(source, "rows", ()) or ():
        if not str(row.datum_address).startswith("4-2-"):
            continue
        head = row.raw[0] if isinstance(row.raw, list) and row.raw else []
        node_id = ""
        for i in range(1, len(head) - 1, 2):
            marker, value = str(head[i]), str(head[i + 1])
            if marker == _TAXON and not node_id:
                node_id = value
            elif marker == _COMMON and node_id and node_id not in common:
                common[node_id] = decode_label(value)
            elif marker == _ICON and node_id and node_id not in icons:
                # Babelette-encoded like every other label cell. Carrying the raw
                # 136 bits would have shipped a 512-byte string per node — 1.7 MB
                # of the tree — and built an image URL out of "0110…".
                icons[node_id] = decode_label(value)

    # Products hang off the taxon they resolved to. A product with an empty taxon
    # (mixed baskets, honey, metal art) is deliberately not forced onto a node.
    products_by_taxon: dict[str, list[dict[str, Any]]] = {}
    untaxed = 0
    for product_id, profile in titles.items():
        taxon = profile.get("taxon", "")
        if not taxon:
            untaxed += 1
            continue
        products_by_taxon.setdefault(taxon, []).append({
            "product_id": product_id,
            "title": profile.get("title") or product_id,
            "entries": traded.get(product_id, 0),
        })
    for entries in products_by_taxon.values():
        entries.sort(key=lambda p: (-int(p["entries"]), p["title"].lower()))

    nodes: list[dict[str, Any]] = []
    named = 0
    for node_id in sorted(scientific, key=lambda a: [int(s) if s.isdigit() else 0
                                                     for s in a.split("-")]):
        latin = scientific[node_id]
        label = common.get(node_id) or _pretty(latin) or node_id
        if node_id in common:
            named += 1
        entry: dict[str, Any] = {"id": node_id, "label": label}
        # The binomial rides along ONLY when it says something the headline does
        # not. On the 3,649 nodes with no common name the label IS the prettied
        # title, and carrying both doubled the tree to 2.2 MB to repeat itself.
        pretty_latin = _pretty(latin)
        if pretty_latin and pretty_latin.lower() != label.lower():
            entry["scientific_name"] = pretty_latin
        if node_id in products_by_taxon:
            entry["traded"] = True
            entry["products"] = products_by_taxon[node_id]
        nodes.append(entry)

    # expand_to: every PROPER ancestor of a traded taxon. The tree opens along what
    # this market actually sells and stays closed everywhere else — 188 of 4,096
    # nodes, so a cold pane is that path and nothing more.
    known = set(scientific)
    expand_to: set[str] = set()
    for taxon in products_by_taxon:
        cursor = taxon
        while "-" in cursor:
            cursor = cursor.rsplit("-", 1)[0]
            if cursor in known:
                expand_to.add(cursor)

    return {
        "loaded": True,
        "nodes": nodes,
        "expand_to": sorted(expand_to, key=lambda a: (a.count("-"), a)),
        # The BINDINGS, not the result. The tool's closest-ancestor rule spreads 65
        # icons over 3,366 nodes, and stamping the answer onto each one cost 235 KB
        # to say the same thirteen things — the reader walks its own ancestors,
        # which is what the site's hierarchical image lookup already does.
        "icons": {node_id: ref for node_id, ref in icons.items() if node_id in scientific},
        # Empty on purpose: the icon leaflets live under the portal's /assets, and
        # a cross-origin reader has no business guessing that they are reachable.
        # A host that serves them sets this; the renderer draws nothing without it.
        "icon_url_prefix": "",
        "totals": {
            "nodes": len(nodes),
            "named": named,
            "unnamed": len(nodes) - named,
            "traded_taxa": len(products_by_taxon),
            "products": len(titles),
            "products_without_taxon": untaxed,
        },
        "missing_documents": missing,
        "sources": resolution.coverage(),
    }


def _live_instance_nodes(authority_db_file: Path | None) -> set[str]:
    """The msn nodes holding a live install, from this instance's contract records.

    I/O at the edge: the derivation itself is ``references.live_instance_nodes``, the
    same one the public registry feed uses, so the channel and the feed cannot disagree
    about who has an instance. A missing contracts directory yields the empty set — the
    hosting instance is added separately, because an instance serving this session is
    self-evidently running.
    """
    import json

    from micyte.core.references import live_instance_nodes

    if authority_db_file is None:
        return set()
    directory = Path(authority_db_file).parent / "contracts"
    if not directory.is_dir():
        return set()
    payloads = []
    for path in sorted(directory.glob("contract-*.json")):
        try:
            payloads.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return live_instance_nodes(payloads)


def _published_binary(authority_db_file: Path | None, sandbox: str,
                      documents: dict[str, Any], *,
                      artifact: str = "", export_hint: str = "") -> dict[str, Any]:
    """A published artifact of this channel, and whether it still says what the
    documents say.

    Convention §5: *a resource binary is a projection of documents, never an origin — it
    is derivable, re-derivable, and identified by the hash of what it was derived from.*

    Two artifacts, one reporter. The channel publishes both a **still** (``agnet.mss`` —
    the documents carried verbatim, the instance-to-instance snapshot, 2.35 MB framed and
    76 MB inflated) and a **projection** (``agnet-demand.mss`` — the demand view derived
    and columnar, 0.35 MB framed and 1.9 MB inflated, which is what the viewer actually
    reads). Their manifests, allowlist entries and staleness arithmetic are identical, so
    they share this function; two copies would be two places for the arithmetic to drift,
    and the one that drifted would be the one nobody was looking at.

    What this adds is the last clause of §5: *staleness a reportable fault rather than an
    invisible drift.* Each manifest lists the version hash of every document it was built
    from, so "is the published binary current" is answerable by comparing hashes — no
    decode, no re-derivation, and no second source of truth: the manifest is written by
    the same export that writes the bytes.

    Absent is not an error. A channel that has published nothing says so, exactly as the
    supply tab does — coverage is claimed, never implied.
    """
    import json

    stem = artifact or sandbox
    if authority_db_file is None:
        return {"published": False, "reason": "no authority store configured"}
    manifest_path = Path(authority_db_file).parent / "stills" / f"{stem}.manifest.json"
    if not manifest_path.is_file():
        return {"published": False,
                "reason": export_hint or (
                    f"no still published for {sandbox!r} — export_registry_still "
                    f"--sandbox {sandbox} --all --name {sandbox}")}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {"published": False, "reason": f"{stem} manifest unreadable: {error}"}

    live = {n: str(getattr(doc, "document_id", "")).rsplit(".", 1)[-1]
            for n, doc in documents.items()}
    published = {str(entry.get("name")): str(entry.get("mss_hash", ""))
                 .removeprefix("sha256:") for entry in manifest.get("documents", ())}
    stale = sorted(n for n, digest in published.items()
                   if live.get(n) and live[n] != digest)
    missing = sorted(set(live) - set(published))
    name = str(manifest.get("name") or stem)
    # HELD is not SERVED. Exporting a still writes bytes into the instance's stills
    # directory; the contact card's allowlist is what makes them fetchable, and it is a
    # separate act on purpose — "the allowlist is the only thing standing between a
    # request and the bytes". So the citation says which of the two is true rather than
    # advertising a URL that answers 404.
    #
    # ``path`` is a route on THIS INSTANCE, to be resolved against the origin the session
    # was fetched from — not against the page holding the viewer. The two differ whenever
    # the channel is engaged cross-origin, which is the ordinary case (micyte.com's vhost
    # does not proxy the portal), and resolving it against the page is how a citation
    # becomes a 404 on a host that never had the bytes.
    served = False
    card_path = Path(authority_db_file).parent / "contact_card.json"
    if card_path.is_file():
        try:
            card = json.loads(card_path.read_text(encoding="utf-8"))
            served = any(str(entry.get("name")) == name
                         for entry in (card.get("public_stills") or ()))
        except (OSError, ValueError):
            served = False
    return {
        "published": True,
        "name": name,
        "artifact": str(manifest.get("artifact", "")),
        "served": served,
        "path": f"/__mss/public/stills/{manifest.get('artifact', '')}" if served else "",
        "sha256": str(manifest.get("sha256", "")),
        "bytes": int(manifest.get("bytes") or 0),
        "created_at": str(manifest.get("created_at", "")),
        "documents": len(published),
        "current": not stale and not missing,
        "stale_documents": stale,
        "unpublished_documents": missing,
    }


def _profiles_section(
    documents: list[Any], *, live_nodes: set[str], resolution: Any,
) -> dict[str, Any]:
    """Legal-entity profiles grouped by entity kind, split by instance vs record.

    The split the channel exists to make legible: an entity either has an INSTANCE to
    reach for its own information, or it is a profile the registrar keeps about it —
    present and useful, but a record rather than an operator.

    Both halves come from the same registry card document, so nothing here is a second
    directory. The model is built only from documents the channel's manifest declares:
    when the manifest stops declaring one, the group it fed disappears from the payload
    and the coverage block says which source went missing — a stated gap, never a silent
    one.

    Liveness is never PROBED here. Reachability is a port, and a session builder that
    opened sockets would make rendering a page depend on the network.
    """
    from micyte.domains.registry.directory import build_directory_model

    model = build_directory_model(documents)
    groups: dict[str, dict[str, Any]] = {}
    reachable_total = 0
    for node in model.nodes:
        kind = node.entity_kind or ""
        label = node.entity_kind_label or ("unclassified" if not kind else kind)
        group = groups.setdefault(kind, {
            "entity_kind": kind, "entity_kind_label": label,
            "instances": [], "records": [],
        })
        entry = {
            "msn_id": node.msn_id,
            "title": decode_label(node.title) if node.title else node.msn_id,
            "website": node.website or node.dns,
            "region": node.region_label,
            "county": node.county_label,
            "ag_profiles": list(node.ag_profiles),
        }
        if node.msn_id in live_nodes:
            entry["reach"] = "instance"
            group["instances"].append(entry)
            reachable_total += 1
        else:
            # A record with curated detail is not the same as a bare directory line, and
            # the difference is derivable — it is whether anything beyond the card says
            # something about this node.
            entry["reach"] = "record"
            entry["curated"] = bool(node.ag_profiles)
            group["records"].append(entry)

    for group in groups.values():
        group["instances"].sort(key=lambda e: e["title"].lower())
        group["records"].sort(key=lambda e: e["title"].lower())
        group["node_count"] = len(group["instances"]) + len(group["records"])

    ordered = sorted(groups.values(), key=lambda g: (-g["node_count"],
                                                     g["entity_kind_label"].lower()))
    total = sum(g["node_count"] for g in ordered)
    return {
        "groups": ordered,
        "totals": {
            "nodes": total,
            "instances": reachable_total,
            "records": total - reachable_total,
            "kinds": len(ordered),
            "curated_records": sum(1 for g in ordered for e in g["records"] if e["curated"]),
        },
        "missing_documents": list(model.missing_documents),
        "sources": resolution.coverage(),
    }


class _CatalogOf:
    """The documents in hand, in the shape `resolve_sources` reads (``.documents``)."""

    __slots__ = ("documents",)

    def __init__(self, documents: Any) -> None:
        self.documents = tuple(documents)


def _declared_source_documents(store: Any, own: Any, *, sandbox: str) -> tuple[Any, ...]:
    """The documents of every sandbox the channel's `sources` manifest declares —
    read per sandbox, so the session costs its own sandbox plus what it cites."""
    from micyte.core.sources import MANIFEST_DOCUMENT, manifest_rows
    from micyte.ports.datum_store import AuthoritativeDatumDocumentRequest

    manifest = next((d for d in own
                     if parse_canonical_document_id(d.document_id).name == MANIFEST_DOCUMENT), None)
    if manifest is None:
        return ()
    index = store.read_document_index(AuthoritativeDatumDocumentRequest(tenant_id="fnd"))
    sandboxes = {str(getattr(s, "tool_id", "") or "") for s in index.documents}
    declared = {row.sandbox for row in manifest_rows(manifest, sandboxes=sandboxes)
                if getattr(row, "sandbox", "") and row.sandbox != sandbox}
    out: list[Any] = []
    for name in sorted(declared):
        out.extend(store.read_documents_by_sandbox(tenant_id="fnd", sandbox=name))
    return tuple(out)


def build_session_payload(
    authority_db_file: Path | None,
    *,
    sandbox: str,
    channel: AgnetChannel,
    tab: str = "",
    day: str = "",
    product: str = "",
    market: str = "",
) -> dict[str, Any]:
    if authority_db_file is None:
        return {"container": CONTAINER, "schema": SESSION_SCHEMA,
                "error": "no authority store configured"}

    from micyte.adapters.sql import open_mos_store

    # The channel's own sandbox, then the sandboxes its manifest declares (2026-09-25):
    # the public channel door read the whole catalog on every session.
    store = open_mos_store(Path(authority_db_file), cache=True)
    own = tuple(store.read_documents_by_sandbox(tenant_id="fnd", sandbox=sandbox))
    docs: dict[str, Any] = {}
    for document in own:
        try:
            parsed = parse_canonical_document_id(document.document_id)
        except Exception:
            continue
        if parsed.sandbox == sandbox:
            docs[parsed.name] = document
    catalog = _CatalogOf(own + _declared_source_documents(store, own, sandbox=sandbox))

    notes: list[str] = []
    if "channel_profile" not in docs:
        return {"container": CONTAINER, "schema": SESSION_SCHEMA,
                "error": f"channel sandbox {sandbox!r} is not bootstrapped "
                         "(no channel_profile document)"}
    profile_meta = dict(getattr(docs["channel_profile"], "document_metadata", {}) or {})
    if profile_meta.get("access") and profile_meta["access"] != channel.access:
        notes.append(
            f"access drift: code declares {channel.access!r}, the sandbox's "
            f"channel_profile records {profile_meta['access']!r}"
        )
    recorded_tabs = tuple(t.strip() for t in str(profile_meta.get("tabs", "")).split(",")
                          if t.strip())
    if recorded_tabs and recorded_tabs != tuple(channel.tabs):
        # Same posture as the access cross-check: report the disagreement, never
        # resolve it silently. A sandbox recording fewer tabs than the channel serves
        # is how a surface starts claiming coverage nobody denoted.
        notes.append(
            f"tab drift: code serves {list(channel.tabs)}, the sandbox's "
            f"channel_profile records {list(recorded_tabs)}"
        )

    anchor = docs.get("anchor")
    chain = find_fiat_chain(anchor) if anchor is not None else None
    if chain is None:
        return {"container": CONTAINER, "schema": SESSION_SCHEMA,
                "error": f"{sandbox!r} anchor defines no price datum; demand "
                         "prices cannot be read as money"}

    lot_documents = {name: doc for name, doc in docs.items() if _is_record_document(doc)}
    titles = _product_titles(docs)
    if not titles:
        notes.append("no product_profiles document: entries are shown under the "
                     "report's own wording, ungrouped")

    # MARKETS. Four observers describe three auctions, and two of them describe the
    # SAME auction over overlapping years. Pooling them would put one sale in the
    # histogram twice and average two different auctions' prices together, so a session
    # reads exactly one market at a time and the rest are offered.
    #
    # A market is now an (entity, OBSERVER) pair read from the profiles' 4-11-N observer
    # rows — three documents' worth of header rows. It used to be read from document
    # METADATA across 119 monthly documents, because the observer was only recorded in
    # each document's NAME. Provenance became a cell on 2026-08-05; this is the reader
    # catching up. What must NOT change: the picker still does not walk 47,569 rows to
    # draw itself, and only the selected market's rows are scanned, below.
    markets, docs_by_market, market_notes = _scan_markets(lot_documents)
    notes.extend(market_notes)

    ordered_markets = sorted(markets.values(), key=lambda m: (-m["entries"], m["source_key"]))
    selected_market = market if market in markets else (
        ordered_markets[0]["source_key"] if ordered_markets else "")
    if market and market not in markets:
        notes.append(f"no market {market!r} in this channel; showing {selected_market}")

    days: set[str] = set()
    for doc, address in docs_by_market.get(selected_market, ()):
        for row in _lot_rows(doc):
            if _observed_by(row) != address:
                continue
            found_day = _lot_day(row)
            if found_day:
                days.add(found_day)
    ordered_days = sorted(days)
    lots_total = sum(m["entries"] for m in ordered_markets)

    # An explicit default rather than tabs[-1]: adding a tab must not silently change
    # which one a session opens on.
    active_tab = tab if tab in channel.tabs else channel.default_tab
    selected_day = day if day in days else (ordered_days[-1] if ordered_days else "")
    if day and day not in days:
        notes.append(f"no {selected_market} report on {day}; showing {selected_day}")

    decoded: list[dict[str, Any]] = []
    undecodable = 0
    aligned = unaligned = 0
    if selected_day:
        for doc, address in docs_by_market.get(selected_market, ()):
            for row in _lot_rows(doc):
                if _observed_by(row) != address or _lot_day(row) != selected_day:
                    continue
                lot = _decode_lot(row, chain.marker)
                if lot is None:
                    undecodable += 1
                    continue
                if lot["product_id"]:
                    aligned += 1
                else:
                    unaligned += 1
                decoded.append(lot)

    # Grouping is by the RESOLVED product, which is the whole repair: one crop
    # spelled six ways used to be six products. An entry that never resolved is
    # still shown — under the report's own words, marked as unaligned, because a
    # price nobody could classify is still a price somebody paid.
    groups: dict[str, dict[str, Any]] = {}
    for lot in decoded:
        product_id = lot["product_id"]
        if product_id:
            profile = titles.get(product_id, {})
            key = product_id
            label = profile.get("title") or product_id
            taxon = profile.get("taxon", "")
        else:
            key = f"~{lot['product']}"
            label = lot["product"]
            taxon = ""
        group = groups.setdefault(key, {
            "product": label, "product_id": product_id, "taxon": taxon,
            "aligned": bool(product_id), "lots": [],
        })
        group["lots"].append(lot)

    by_label = {group["product"]: key for key, group in groups.items()}
    product_filter = product if product in by_label else ""
    if product and product not in by_label:
        notes.append(f"no {product!r} on {selected_day} at {selected_market}")

    shown = [group for key, group in groups.items()
             if not product_filter or key == by_label[product_filter]]
    shown.sort(key=lambda entry: (entry["aligned"] is False, -len(entry["lots"])))

    # The entity-aggregation view reads ONLY what this channel's manifest declares.
    # verify=False: a session render is a hot path, and the coherence gate is where
    # pins are checked. The resolution's coverage rides in the payload either way, so
    # a manifest that has lost a source says so instead of quietly rendering less.
    resolution = resolve_sources(catalog.documents, sandbox=sandbox)
    declared = [resolved.document for resolved in resolution.sources
                if resolved.document is not None]
    # The HOSTING instance is live by definition — it is the one serving this session.
    # Not the SUBJECT entity: County Line is exactly the record-kept case this view
    # exists to distinguish, and counting it as an instance would invert the point.
    hosting = ""
    try:
        hosting = parse_canonical_document_id(docs["channel_profile"].document_id).msn_id
    except Exception:
        hosting = ""
    live_nodes = _live_instance_nodes(authority_db_file) | ({hosting} if hosting else set())
    profiles = _profiles_section(declared, live_nodes=live_nodes, resolution=resolution)

    binary = _published_binary(authority_db_file, sandbox, docs)
    if binary.get("published") and not binary.get("current"):
        notes.append(
            "the published still is behind the documents: "
            + ", ".join(binary.get("stale_documents") or binary.get(
                "unpublished_documents") or ())
            + " — re-run export_registry_still"
        )

    # The artifact the VIEWER reads. Cited separately from the still because the two are
    # different artifacts with different jobs, and a consumer must be able to tell which
    # it is being offered: the still is the faithful snapshot another INSTANCE rebuilds
    # documents from, this is the derived view a BROWSER holds. Same publication chain,
    # same staleness arithmetic, same held-is-not-served rule.
    projection = _published_binary(
        authority_db_file, sandbox, docs,
        artifact=f"{sandbox}{PROJECTION_SUFFIX}",
        export_hint=(f"no demand projection published for {sandbox!r} — "
                     f"export_channel_projection --sandbox {sandbox}"),
    )
    if projection.get("published"):
        projection["schema"] = PROJECTION_SCHEMA
        if not projection.get("current"):
            notes.append(
                "the published demand projection is behind the documents: "
                + ", ".join(projection.get("stale_documents") or projection.get(
                    "unpublished_documents") or ())
                + " — re-run export_channel_projection"
            )

    # The tree is 4,096 nodes — a quarter of a megabyte of payload — and the viewer
    # refetches the WHOLE session behind every day and product pick. So it is built
    # for its own tab and for nothing else; every other request says so rather than
    # sending an empty section that reads like an empty tree.
    if active_tab == "taxonomy":
        taxonomy = _taxonomy_section(
            resolution, titles=titles, traded=_entries_by_product(lot_documents),
        )
    else:
        taxonomy = {"loaded": False}

    taxonomy_coverage: dict[str, Any] = {}
    if taxonomy.get("loaded"):
        totals = taxonomy.get("totals", {})
        taxonomy_coverage = {
            "taxonomy_nodes": totals.get("nodes", 0),
            "taxonomy_named": totals.get("named", 0),
            "taxonomy_unnamed": totals.get("unnamed", 0),
            "taxonomy_traded_taxa": totals.get("traded_taxa", 0),
        }
        for name in taxonomy.get("missing_documents", ()):
            notes.append(
                f"this channel does not declare {name} as a source, so the "
                "classification tree is read from what it does declare"
            )

    return {
        "container": CONTAINER,
        "schema": SESSION_SCHEMA,
        "channel": {
            "channel_id": channel.channel_id,
            "label": channel.label,
            "summary": channel.summary,
            "access": channel.access,
            "tabs": list(channel.tabs),
        },
        "active_tab": active_tab,
        "published_binary": binary,
        "projection": projection,
        "profiles": profiles,
        "taxonomy": taxonomy,
        "supply": {
            "status": "empty",
            "reason": (
                "no source publishes offerings to this channel yet — instance "
                "offerings (the commerce_offering port) would populate it once "
                "published as channel sources"
            ),
        },
        "demand": {
            "market": selected_market,
            "markets": ordered_markets,
            "day": selected_day,
            "days": ordered_days,
            "product_filter": product_filter,
            "product_names": sorted(by_label),
            "products": shown,
        },
        "coverage": {
            "documents_read": len(lot_documents),
            "lots_total": lots_total,
            "days": len(ordered_days),
            "lots_on_day": len(decoded),
            "undecodable_on_day": undecodable,
            "aligned_on_day": aligned,
            "unaligned_on_day": unaligned,
            "products_known": len(titles),
            "markets": len(ordered_markets),
            "subject_msn": str(markets.get(selected_market, {}).get("subject_msn", "")),
            **taxonomy_coverage,
            "notes": notes,
        },
    }


class AgnetChannel:
    channel_id = "agnet"
    label = "AGNET"
    # UI copy: the rail hover, one sentence (the supply side's status is the
    # channel page's own content, not the tooltip's).
    summary = "The open farm-network channel: market demand pricing by product and day."
    access = "open"
    sandbox = "agnet"
    # `taxonomy` is the responsibility absorbed from the taxonomy_domain tool: the
    # txa tree the market's products resolve THROUGH, served by the channel that
    # holds them rather than by a second, divergent copy on a website.
    tabs = ("supply", "demand", "taxonomy", "profiles")
    default_tab = "demand"
    wants_surface_query = True

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str,
        document_id: str,
        datum_address: str,
        extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del sandbox_id, document_id, datum_address  # a channel supplies its own context
        eq = extra_query or {}
        payload = build_session_payload(
            authority_db_file,
            sandbox=self.sandbox,
            channel=self,
            tab=str(eq.get("channel_tab", "") or ""),
            day=str(eq.get("day", "") or ""),
            product=str(eq.get("product", "") or ""),
            market=str(eq.get("market", "") or ""),
        )
        # The operator's overlay refreshes day/product picks through the
        # authenticated twin of the public session route — same builder, so the
        # internal and external renderings cannot drift.
        payload["refresh_endpoint"] = f"/portal/api/channels/{self.channel_id}/session"
        return payload


CHANNEL = register(AgnetChannel())
