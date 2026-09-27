"""The browser's model of the registry: regions to navigate, nodes to select,
and the profile a selected node yields.

Why this is not the map payload
-------------------------------
``network_map_viewer`` builds the *agronomics* map: it reads the
``network_sources`` manifest and yields one point per (entity x ag-profile), so
it sees 177 of the registry's 235 nodes and nothing at all about the 58 that
publish no ag profile. That is the right slice for a map of who sells food. It
is the wrong slice for a browser of the network, where a township with no farm
stand is still a node you must be able to find.

So the browser's backbone is the ``registry`` card document — one row per
distinct ``msn_id``, type-agnostic, already covering exactly the union of
``legal_entity`` + ``natural_entity`` + ``administrative_entity``. Everything
else in here enriches that backbone rather than replacing it.

The msn_profile
---------------
A node's profile is assembled by scanning **every** registrar document for rows
carrying that ``msn_id``, and emitting one section per document that has any.
Nothing enumerates which documents may contribute. That is deliberate and it is
the point: the operator's model is that an ``lcl_id`` does not *change* a
profile, it *denotes the expectation* that further detail exists, and that the
detail lives in a separate datum document for nodes with no instance of their
own. Adding that document later must be a data change, not a code change — so
this reads the sandbox, not a list.

Pure: no I/O, no MOS, no filesystem. It takes documents someone else read,
whether from the live authority or from a decoded still.
"""

from __future__ import annotations

import re
import threading
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from micyte.core import instance_baseline as _baseline
from micyte.core.datum_ops import field_registry as _fr
from micyte.core.document_naming import document_in_sandbox, parse_canonical_document_id

SANDBOX = "registrar"

#: The card directory: one row per distinct msn_id, type-agnostic.
REGISTRY_DOCUMENT = "registry"
#: The gazetteer whose rows label region nodes.
GAZETTEER_DOCUMENT = "administrative"
#: Named jurisdictions. These drive region navigation: an administrative entity
#: names a region and says what kind of jurisdiction it is.
ADMIN_ENTITY_DOCUMENT = "administrative_entity"
#: The local classification list — lcl_id -> label, for every denotation.
#:
#: Read through :data:`LCL_DOCUMENT_NAMES`, never against one literal: the document was
#: renamed to ``lcl_domain`` on 2026-08-20 and a directory that looked up only the old name
#: would report the registrar's own classification MISSING for the whole msn browser.
LCL_DOCUMENT = _baseline.LCL_DOCUMENT
LCL_DOCUMENT_NAMES = _baseline.LOCAL_DOMAIN_NAMES
#: Per-node ag denotations.
#: Moved to the channel by phase 3b — profiles OF members belong where the
#: unengaged case lives. Kept named here so a reader has one place to look.
AG_PROFILE_DOCUMENT = "member_ag_profiles"
AG_PROFILE_SANDBOX = "agnet"
#: Depth-9 street addresses. Split from the gazetteer only by size.
ADDRESS_DOCUMENT = "address_nodes"

#: A boundary document is NAMED for the gazetteer node it outlines, so the catalog itself says
#: which places are drawable. Ohio is 3-2-3-17; every node below it is a region of the service
#: area.
_GAZETTEER_NODE = re.compile(r"3-2-3-17(-\d+)+")

_MSN = _fr.marker(_fr.REGISTRAR, "msn_id")
_TITLE = _fr.marker(_fr.REGISTRAR, "title")
_LCL = _fr.marker(_fr.REGISTRAR, "lcl_id")
_DNS = _fr.marker(_fr.REGISTRAR, "dns")
_WEBSITE = _fr.marker(_fr.REGISTRAR, "website")
_SIGNATURE = _fr.marker(_fr.REGISTRAR, "public_signature")
_ENDPOINT = _fr.marker(_fr.REGISTRAR, "instance_endpoint")
_JURISDICTION = _fr.marker(_fr.REGISTRAR, "jurisdiction_type")
_REGION_REF = _fr.marker(_fr.REGISTRAR, "region_polygon_ref")

#: Marker -> readable label, so a profile row says "dns", not "rf.3-1-9". Built
#: from the field registry rather than hand-listed, so a new registrar field is
#: named here the moment it is defined there.
_FIELD_LABEL: dict[str, str] = {}
for _name, _addr in _fr.FIELD_ADDRESS[_fr.REGISTRAR].items():
    _FIELD_LABEL.setdefault(f"rf.{_addr}", _name)

#: The county is the depth-5 gazetteer node, the municipality the depth-7 — the
#: same walk ``network_map_viewer.region_of`` does, and the same depths the map
#: and calendar filters already page by. Data-driven within those bounds: a
#: prefix is a region only if the gazetteer actually names it.
_COUNTY_DEPTH = 5
_MUNICIPALITY_DEPTH = 7


# --------------------------------------------------------------------------- #
# Row reading
# --------------------------------------------------------------------------- #
def _head(row: Any) -> list[Any]:
    raw = getattr(row, "raw", None)
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return raw[0]
    if isinstance(raw, list):
        return raw
    return []


def _tail_label(row: Any) -> str:
    raw = getattr(row, "raw", None)
    if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], list) and raw[1]:
        return "" if raw[1][0] is None else str(raw[1][0]).strip()
    return ""


def _pairs(head: list[Any]) -> dict[str, list[str]]:
    """``{marker: [value, ...]}`` from a ``[addr, marker, value, ...]`` head.

    A marker may repeat (a natural entity carries two ``ruiqi_id`` values, one
    per name part), so values are collected rather than overwritten.
    """
    out: dict[str, list[str]] = {}
    for i in range(1, len(head) - 1, 2):
        key = "" if head[i] is None else str(head[i]).strip()
        val = "" if head[i + 1] is None else str(head[i + 1]).strip()
        if key:
            out.setdefault(key, []).append(val)
    return out


def _first(pairs: dict[str, list[str]], marker: str) -> str:
    values = pairs.get(marker)
    return values[0] if values else ""


@lru_cache(maxsize=8192)
def decode_display_text(value: str) -> str:
    """Decode the corpus's 8-bit-aligned bit-string display encoding.

    The gazetteer and the lcl list store their labels this way. A value that is
    not one is returned untouched — several registrar documents store the same
    field as plain text, and a browser that showed one and not the other would
    be reporting an encoding choice as if it were data.

    MEMOIZED, and the decode is one `int()` rather than one per byte. MEASURED
    2026-08-30: the operator's profile page spent 1.45s of local work per render, and
    this function was 2.45s of a 4.6s cold profile — 48,601 calls driving 2.87 million
    generator evaluations. It is called once per ROW per gazetteer, and a gazetteer is
    mostly repeated place names, so the same few thousand strings are decoded over and
    over.

    Safe to cache because it is pure: a `str` in, a `str` out, no clock and no store. The
    cache is BOUNDED — an unbounded one would hold every label the process ever saw,
    including the plain-text values that take the early return. `to_bytes` is byte-identical
    to the per-byte loop it replaces (proved over 4,014 cases, including padding, an
    all-zero payload, non-UTF-8 bytes and every unaligned length).
    """
    if len(value) < 8 or len(value) % 8 or set(value) - {"0", "1"}:
        return value
    try:
        raw = int(value, 2).to_bytes(len(value) // 8, "big")
        text = raw.decode("utf-8").rstrip("\x00")
    except (ValueError, UnicodeDecodeError):
        return value
    # An all-zero payload is padding, not an empty label; keep the caller's
    # fallback rather than replacing a name with "".
    return text or value


def _document_name(document: Any) -> str:
    """The short name out of ``lv.<msn>.<sandbox>.<name>.<hash>``.

    A directory may arrive from *another instance* as a decoded still, so an
    unparseable id is untrusted input rather than a programming error: it must
    drop the document, not raise out of a surface render. Falling back to the
    positional segment keeps a document readable when only its hash is
    malformed, which is the difference between a browser that degrades and one
    that goes blank.
    """
    document_id = str(getattr(document, "document_id", "") or "")
    try:
        parsed = parse_canonical_document_id(document_id)
    except Exception:
        parsed = None
    name = getattr(parsed, "name", "") if parsed is not None else ""
    if name:
        return name
    segments = document_id.split(".")
    return segments[3] if len(segments) > 4 else ""


def registrar_documents(
    documents: Iterable[Any], *, sandbox: str = SANDBOX, msn_id: str = ""
) -> dict[str, Any]:
    """``name -> document`` for the registrar sandbox, from any document source.

    ``msn_id`` scopes to one instance's copy. The registrar is FND-only today, so the
    default keeps the name-only question; a caller holding the msn should pass it.
    """
    out: dict[str, Any] = {}
    for document in documents:
        document_id = str(getattr(document, "document_id", "") or "")
        if not document_in_sandbox(document_id, sandbox, msn_id=msn_id):
            continue
        name = _document_name(document)
        if name:
            out[name] = document
    return out


# --------------------------------------------------------------------------- #
# The model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Region:
    """A navigable area, named by the gazetteer and typed by an administrative entity."""

    node: str
    label: str
    depth: int
    parent: str = ""
    #: "city" / "village" / "township" / "county" — from the administrative
    #: ENTITY that governs this area, when one is registered. Empty means the
    #: gazetteer names the area but no entity has been registered for it, which
    #: is a real and common state, not a gap to paper over.
    jurisdiction_type: str = ""
    governed_by: str = ""
    node_count: int = 0


@dataclass(frozen=True)
class Node:
    """One selectable msn node — the card projection, plus where it sits."""

    msn_id: str
    title: str
    entity_kind: str = ""
    entity_kind_label: str = ""
    dns: str = ""
    website: str = ""
    #: base64 of the raw Ed25519 public key this node publishes. It is what makes a
    #: signed message from this node checkable by anyone holding the card — and it is
    #: therefore the ONLY place an identity key may come from: a contract that carried
    #: the key authorising it would be authorising itself. Empty for a node that runs
    #: no instance, which is most of them.
    public_signature: str = ""
    #: The https origin at which this node's instance answers contract traffic. The
    #: other half of reachability, published in the same document and for the same
    #: reason: a request must be delivered before there is a contract to carry an
    #: address. Never taken from ``dns``, which is a website. Empty for a node that
    #: runs no reachable instance.
    instance_endpoint: str = ""
    region_node: str = ""
    region_label: str = ""
    county_node: str = ""
    county_label: str = ""
    ag_profiles: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProfileSection:
    """What one registrar document knows about a node."""

    document: str
    rows: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class PlaceLevel:
    """One rung of the geospatial profile: the node, what it is, and whether it has an outline."""

    depth: int
    band: str
    node: str
    label: str
    has_polygon: bool = False


@dataclass(frozen=True)
class Profile:
    """The msn_profile: the default identity block, plus whatever is appended.

    ``sections`` is every registrar document carrying a row for this node. It is
    discovered, never enumerated — see the module docstring.

    ``place`` is the geospatial profile presented as an aspect of this one. It is DERIVED from
    the msn rather than stored, because the msn already is the address: walking it names the
    county, the municipality, the street and the street address, and says which of those have a
    boundary the map can draw. ``contains`` is the reciprocal — on a region node, the entities
    that sit inside it.
    """

    msn_id: str
    title: str = ""
    identity: tuple[tuple[str, str], ...] = ()
    sections: tuple[ProfileSection, ...] = ()
    place: tuple[PlaceLevel, ...] = ()
    contains: tuple[dict[str, str], ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.identity and not self.sections


@dataclass(frozen=True)
class RegistryDirectoryModel:
    """Everything the browser navigates, derived once per read."""

    nodes: tuple[Node, ...] = ()
    regions: tuple[Region, ...] = ()
    lcl_labels: dict[str, str] = field(default_factory=dict)
    #: Documents that were expected and absent. A browser reading a partial
    #: still must say which part is missing rather than render a short list as
    #: though it were the whole registry.
    missing_documents: tuple[str, ...] = ()

    def node(self, msn_id: str) -> Node | None:
        for candidate in self.nodes:
            if candidate.msn_id == msn_id:
                return candidate
        return None


# --------------------------------------------------------------------------- #
# Building it
# --------------------------------------------------------------------------- #
#: `_gazetteer` answers, keyed on the DOCUMENT ID. A canonical id carries the content
#: hash, so two document objects with one id are one content — which is the key the
#: 2026-08-30 attempt (a `WeakKeyDictionary` on the object) did not have: the four calls
#: per profile render arrive with four distinct objects that never outlive the render, and
#: it never hit once. Keyed on the id it hits from the second call on, across renders,
#: until the document is rewritten. Four entries: the gazetteer and the address nodes
#: (~97,000 rows, the profile's warm second), and one spare pair for a second store.
#: Readers only look labels up; the dict is shared, not copied.
_GAZETTEER_LOCK = threading.Lock()
_GAZETTEER: OrderedDict[str, dict[str, str]] = OrderedDict()
_GAZETTEER_MAX = 4


def _gazetteer(document: Any) -> dict[str, str]:
    """``{msn node: display label}`` for one gazetteer-shaped document.

    Remembered by document id ONLY when the id is content-addressed (a canonical `lv.`
    id carries the version hash, so the id names the rows). A made-up id — a fixture's
    `.deadbeef` — names nothing, and remembering under it handed one suite's gazetteer to
    the next (found 2026-09-22 as an order-dependent red in the directory suite).
    """
    from micyte.core.document_naming import is_canonical_document_id

    document_id = str(getattr(document, "document_id", "") or "")
    if document_id and not is_canonical_document_id(document_id):
        document_id = ""
    if document_id:
        with _GAZETTEER_LOCK:
            hit = _GAZETTEER.get(document_id)
            if hit is not None:
                _GAZETTEER.move_to_end(document_id)
                return hit
    labels: dict[str, str] = {}
    for row in getattr(document, "rows", ()) or ():
        pairs = _pairs(_head(row))
        node = _first(pairs, _MSN)
        if not node:
            continue
        labels.setdefault(node, decode_display_text(_first(pairs, _TITLE) or _tail_label(row)))
    if document_id:
        with _GAZETTEER_LOCK:
            _GAZETTEER[document_id] = labels
            _GAZETTEER.move_to_end(document_id)
            while len(_GAZETTEER) > _GAZETTEER_MAX:
                _GAZETTEER.popitem(last=False)
    return labels


def _lcl_labels(document: Any) -> dict[str, str]:
    labels: dict[str, str] = {}
    for row in getattr(document, "rows", ()) or ():
        pairs = _pairs(_head(row))
        lcl_id = _first(pairs, _LCL)
        if not lcl_id:
            continue
        labels.setdefault(lcl_id, decode_display_text(_first(pairs, _TITLE) or _tail_label(row)))
    return labels


#: What each depth of an msn names. The msn IS a hierarchical address, so these are bands of
#: one identifier rather than separate fields somebody has to keep in step.
PLACE_BANDS = {
    5: "county", 6: "municipality class", 7: "municipality", 8: "street", 9: "street address",
}


def boundary_nodes(documents: Iterable[Any], *, sandbox: str = SANDBOX) -> set[str]:
    """Gazetteer nodes that have a boundary document — the outlines a map can draw.

    A boundary document is NAMED for the node it outlines, so this is a read of the catalog
    rather than a list anybody maintains: publish a boundary and the place becomes selectable.
    """
    return {name for name in registrar_documents(documents, sandbox=sandbox)
            if _GAZETTEER_NODE.fullmatch(name)}


def _place_of(
    msn_id: str, labels: dict[str, str], outlines: set[str]
) -> tuple[PlaceLevel, ...]:
    levels: list[PlaceLevel] = []
    for depth, band in sorted(PLACE_BANDS.items()):
        prefix = _prefix_at(msn_id, depth)
        if not prefix:
            continue
        label = labels.get(prefix, "")
        if not label:
            continue
        levels.append(PlaceLevel(depth=depth, band=band, node=prefix, label=label,
                                 has_polygon=prefix in outlines))
    return tuple(levels)


def _prefix_at(msn_id: str, depth: int) -> str:
    segments = msn_id.split("-")
    return "-".join(segments[:depth]) if len(segments) >= depth else ""


def _region_of(msn_id: str, labels: dict[str, str]) -> tuple[str, str]:
    """The deepest gazetteer node this msn sits under, municipality-first."""
    for depth in (_MUNICIPALITY_DEPTH, _COUNTY_DEPTH):
        prefix = _prefix_at(msn_id, depth)
        if prefix and prefix in labels:
            return prefix, labels[prefix]
    return "", ""


def build_directory_model(
    documents: Iterable[Any], *, sandbox: str = SANDBOX
) -> RegistryDirectoryModel:
    """The browser's model, from whatever documents the caller has in hand."""
    by_name = registrar_documents(documents, sandbox=sandbox)
    missing = tuple(
        name
        for name in (REGISTRY_DOCUMENT, GAZETTEER_DOCUMENT, ADMIN_ENTITY_DOCUMENT)
        if name not in by_name
    )
    # The local domain, asked about as a PAIR — the same rule the anchor's two reserved
    # names have always had. Dropping it from the tuple above would have quietly stopped
    # reporting a registrar with no classification at all.
    if not any(name in by_name for name in LCL_DOCUMENT_NAMES):
        missing = (*missing, LCL_DOCUMENT)

    gazetteer = _gazetteer(by_name.get(GAZETTEER_DOCUMENT))
    lcl_labels = _lcl_labels(next(
        (by_name[name] for name in LCL_DOCUMENT_NAMES if name in by_name), None))

    # Named jurisdictions -> the region navigation. An administrative entity's
    # region_polygon_ref IS a gazetteer node; that join is what makes the tree
    # administrative-entity-driven rather than a hardcoded list of counties.
    jurisdiction: dict[str, tuple[str, str]] = {}
    for row in getattr(by_name.get(ADMIN_ENTITY_DOCUMENT), "rows", ()) or ():
        pairs = _pairs(_head(row))
        region_ref = _first(pairs, _REGION_REF)
        if not region_ref:
            continue
        name = decode_display_text(_first(pairs, _TITLE) or _tail_label(row))
        jurisdiction.setdefault(region_ref, (_first(pairs, _JURISDICTION), name))

    ag_profiles: dict[str, list[str]] = {}
    for row in getattr(by_name.get(AG_PROFILE_DOCUMENT), "rows", ()) or ():
        pairs = _pairs(_head(row))
        node, lcl_id = _first(pairs, _MSN), _first(pairs, _LCL)
        if node and lcl_id:
            ag_profiles.setdefault(node, []).append(lcl_labels.get(lcl_id, lcl_id))

    nodes: list[Node] = []
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for row in getattr(by_name.get(REGISTRY_DOCUMENT), "rows", ()) or ():
        pairs = _pairs(_head(row))
        msn_id = _first(pairs, _MSN)
        if not msn_id or msn_id in seen:
            continue
        seen.add(msn_id)
        region_node, region_label = _region_of(msn_id, gazetteer)
        county_node = _prefix_at(msn_id, _COUNTY_DEPTH)
        lcl_id = _first(pairs, _LCL)
        nodes.append(
            Node(
                msn_id=msn_id,
                title=decode_display_text(_tail_label(row) or _first(pairs, _TITLE) or msn_id),
                entity_kind=lcl_id,
                entity_kind_label=lcl_labels.get(lcl_id, lcl_id),
                dns=_first(pairs, _DNS),
                website=_first(pairs, _WEBSITE),
                public_signature=_first(pairs, _SIGNATURE),
                instance_endpoint=_first(pairs, _ENDPOINT),
                region_node=region_node,
                region_label=region_label,
                county_node=county_node if county_node in gazetteer else "",
                county_label=gazetteer.get(county_node, ""),
                ag_profiles=tuple(sorted(set(ag_profiles.get(msn_id, ())))),
            )
        )
        for key in {region_node, county_node} - {""}:
            counts[key] = counts.get(key, 0) + 1

    regions: list[Region] = []
    for node_id, count in counts.items():
        if node_id not in gazetteer:
            continue
        depth = node_id.count("-") + 1
        kind, governed_by = jurisdiction.get(node_id, ("", ""))
        regions.append(
            Region(
                node=node_id,
                label=gazetteer[node_id],
                depth=depth,
                parent=_prefix_at(node_id, _COUNTY_DEPTH) if depth > _COUNTY_DEPTH else "",
                jurisdiction_type=kind,
                governed_by=governed_by,
                node_count=count,
            )
        )

    return RegistryDirectoryModel(
        nodes=tuple(sorted(nodes, key=lambda n: (n.title.lower(), n.msn_id))),
        regions=tuple(sorted(regions, key=lambda r: (r.depth, r.label.lower()))),
        lcl_labels=lcl_labels,
        missing_documents=missing,
    )


def build_profile(
    documents: Iterable[Any],
    msn_id: str,
    *,
    model: RegistryDirectoryModel | None = None,
    sandbox: str = SANDBOX,
) -> Profile:
    """The msn_profile for one node.

    The default identity block comes from the card. Every registrar document
    with a row for this node then appends a section — including documents this
    module has never heard of.
    """
    if not msn_id:
        return Profile(msn_id="")

    documents = tuple(documents)
    by_name = registrar_documents(documents, sandbox=sandbox)
    model = model or build_directory_model(documents, sandbox=sandbox)
    node = model.node(msn_id)

    identity: list[tuple[str, str]] = [("msn_id", msn_id)]
    if node is not None:
        if node.entity_kind:
            identity.append(
                ("entity kind", f"{node.entity_kind_label} ({node.entity_kind})")
            )
        if node.region_label:
            identity.append(("region", node.region_label))
        if node.county_label and node.county_label != node.region_label:
            identity.append(("county", node.county_label))
        if node.dns:
            identity.append(("dns", node.dns))
        if node.website:
            identity.append(("website", node.website))
        if node.ag_profiles:
            identity.append(("ag profiles", ", ".join(node.ag_profiles)))

    sections: list[ProfileSection] = []
    for name in sorted(by_name):
        # The card is the identity block above; repeating it as a section would
        # show the operator the same six values twice.
        if name == REGISTRY_DOCUMENT:
            continue
        rows: list[dict[str, Any]] = []
        for row in getattr(by_name[name], "rows", ()) or ():
            head = _head(row)
            pairs = _pairs(head)
            if _first(pairs, _MSN) != msn_id:
                continue
            fields = [
                {
                    "field": _FIELD_LABEL.get(marker, marker),
                    "marker": marker,
                    "value": decode_display_text(value),
                }
                for marker, values in pairs.items()
                for value in values
                if marker != _MSN
            ]
            rows.append(
                {
                    "datum_address": str(getattr(row, "datum_address", "") or ""),
                    "label": _tail_label(row),
                    "fields": fields,
                }
            )
        if rows:
            sections.append(ProfileSection(document=name, rows=tuple(rows)))

    gazetteer = _gazetteer(by_name.get(GAZETTEER_DOCUMENT))
    addresses = _gazetteer(by_name.get(ADDRESS_DOCUMENT))
    outlines = boundary_nodes(documents, sandbox=sandbox)
    place = _place_of(msn_id, {**gazetteer, **addresses}, outlines)

    # A region node is browsable in its own right: selecting an outline on the map has to lead
    # somewhere, and where it leads is the entities standing on that ground.
    contains = tuple(
        {"msn_id": other.msn_id, "title": other.title,
         "entity_kind": other.entity_kind_label or other.entity_kind}
        for other in model.nodes
        if other.msn_id != msn_id and other.msn_id.startswith(msn_id + "-")
    ) if msn_id in gazetteer else ()

    return Profile(
        msn_id=msn_id,
        title=node.title if node is not None else (gazetteer.get(msn_id) or msn_id),
        identity=tuple(identity),
        sections=tuple(sections),
        place=place,
        contains=contains,
    )


__all__ = [
    "ADMIN_ENTITY_DOCUMENT",
    "AG_PROFILE_DOCUMENT",
    "GAZETTEER_DOCUMENT",
    "LCL_DOCUMENT",
    "REGISTRY_DOCUMENT",
    "SANDBOX",
    "Node",
    "Profile",
    "ProfileSection",
    "Region",
    "RegistryDirectoryModel",
    "build_directory_model",
    "build_profile",
    "decode_display_text",
    "registrar_documents",
]
