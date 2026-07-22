"""Canonical field registry — the anchor decoder ring (namespace convergence, Phase B).

The same ``rf.3-1-N`` marker means different fields in different anchors: ``rf.3-1-1``
is the txa/node id in the system/taxonomy/farm namespaces but the HOPS *coordinate* in
the registrar namespace; ``rf.3-1-9`` is ``dns`` in registrar but ``common_name`` in
taxonomy; ``rf.3-1-3`` has four meanings across the six anchors. Historically each
viewer / tool / script hardcoded its own ``rf.3-1-N`` constants keyed to the one anchor
it read (``Markers`` = system, ``_REG_*`` = registrar, farm constants, taxonomy
constants) — hundreds of sites across four incompatible namespaces, with the standing
hazard that a marker read against the wrong anchor silently mismaps a field.

This module single-sources that mapping as one data table keyed on
``(namespace, logical_field) -> physical 3-1 address``, plus the ``sandbox -> namespace``
assignment. Code resolves a field by NAME through :func:`marker` / :func:`address`,
never by a hardcoded literal, so the conflicting *legacy* numbering becomes invisible
and new standardized fields land at a declared address per anchor. There is no single
global ``address -> address`` map that is correct across anchors — the mapping is keyed
on ``(namespace, field)``, which is exactly what this table encodes.

This is the vocabulary side of ``docs/contracts/msn_profile_and_contact_card``. It is
pure data + lookups (``core`` layer; no I/O, no store, no ``state_machine``).
"""

from __future__ import annotations


def _text(value: object) -> str:
    """Coerce to str without importing the samras codec (keeps this module a pure leaf
    so ``core`` modules can import it without a cycle)."""
    return value if isinstance(value, str) else str(value)


# --- Namespaces (one per distinct anchor numbering) -------------------------------

SYSTEM = "system"          # the system anthology + agro_erp `Markers` vocabulary
REGISTRAR = "registrar"    # the registrar entity directory (its own numbering)
TAXONOMY = "taxonomy"      # the taxonomy anchor
FARM = "farm"              # trapp + wolf (structurally identical anchors)
NETWORK_EBI = "network_ebi"  # the small fnd_ebi network-only anchor

NAMESPACES = frozenset({SYSTEM, REGISTRAR, TAXONOMY, FARM, NETWORK_EBI})

# Which namespace each live sandbox anchor speaks.
NAMESPACE_BY_SANDBOX: dict[str, str] = {
    "system": SYSTEM,
    "registrar": REGISTRAR,
    "taxonomy": TAXONOMY,
    "trapp_family_farm": FARM,
    "wolf_family_sustainable_farm": FARM,
    "fnd_ebi": NETWORK_EBI,
}

# --- The decoder ring: (namespace) -> {logical_field: physical 3-1 address} --------
#
# Verified read-only against the live MOS authority by a downstream verification
# one-shot. Each address is the babelette row the anchor actually defines. Do not
# edit without re-running the verifier.

FIELD_ADDRESS: dict[str, dict[str, str]] = {
    SYSTEM: {
        "utc": "3-1-1",
        "coordinate": "3-1-2",
        "msn_id": "3-1-3",
        "name": "3-1-4",
        "title": "3-1-5",
        "ipv4": "3-1-6",
        "ipv6": "3-1-7",
        "dns": "3-1-8",
        "email": "3-1-9",
    },
    REGISTRAR: {
        "coordinate": "3-1-1",
        "msn_id": "3-1-2",
        "title": "3-1-3",
        "ruiqi_id": "3-1-4",
        "identification": "3-1-5",
        "utc": "3-1-6",
        "sosvid": "3-1-7",
        "email": "3-1-8",
        "dns": "3-1-9",
        "jurisdiction_type": "3-1-10",
        "region_polygon_ref": "3-1-11",
        "mss_source_binary": "3-1-12",
        "lcl_id": "3-1-13",
        # entity_kind is an ALIAS of lcl_id: the card's lcl_id → a node the `lcl` doc marks
        # as a 'type' node IS the entity kind (legal/natural/administrative/informal). No
        # new address, no DB write — it reuses the field the registrar already defines.
        "entity_kind": "3-1-13",
        "resource_kind": "3-1-14",
        "ic_stamp": "3-1-15",
        "tiu_magnitude": "3-1-16",
        # msn contact-card fields (Phase C.2 registrar-card backfill) — plaintext
        # strings over niu-baciloid-256-64 (2-1-1), mirroring email/dns; empty when absent.
        # ipv4/ipv6/website are card fields; `social` is profile-only (leaflet-fold target).
        "ipv4": "3-1-22",
        "ipv6": "3-1-23",
        "website": "3-1-24",
        "social": "3-1-26",
    },
    TAXONOMY: {
        "txa_id": "3-1-1",
        "title": "3-1-2",
        "coordinate": "3-1-3",
        "msn_id": "3-1-4",
        "lcl_id": "3-1-5",
        "utc": "3-1-6",
        "nominal": "3-1-7",
        "common_name": "3-1-9",
        "icon_ref": "3-1-10",
    },
    FARM: {
        "txa_id": "3-1-1",
        "title": "3-1-2",
        "coordinate": "3-1-3",
        "msn_id": "3-1-4",
        "lcl_id": "3-1-5",
        "utc": "3-1-6",
        "nominal": "3-1-7",
    },
    NETWORK_EBI: {
        "utc": "3-1-1",
        "msn_id": "3-1-2",
        "ipv4": "3-1-3",
        "ipv6": "3-1-4",
        "dns": "3-1-5",
    },
}

# Fields that RESOLVE for a namespace but are NOT defined in that namespace's anchor:
# same-namespace anchor gaps (the agro tools read/write a `view` / `retire` / `visual`
# slot the farm anchor never defined) and cross-namespace borrows (the farm `sources`
# docs use registrar fields). These resolve today against the borrowed/implicit numbering
# and are EXPECTED danglers; Phase C closes them by adding the missing babelette to the
# anchor (or rewriting the reference). Declared so the resolver and the verifier agree
# they are expected, not silent corruption; the verifier derives its expected-dangler set
# from these addresses.
EXTRA_FIELDS: dict[str, dict[str, str]] = {
    FARM: {
        "view": "3-1-8",                # record-view token (agro tools) — anchor gap
        "retire": "3-1-10",             # effective-dating retire stamp — anchor gap
        "visual": "3-1-11",             # profile visual ref (0-0-11) — anchor gap
        "mss_source_binary": "3-1-12",  # borrow <- registrar
        "resource_kind": "3-1-14",      # borrow <- registrar
    },
}

# Additive fields NOT yet defined in any anchor — Phase 2 writes their babelette rows,
# then they are promoted into FIELD_ADDRESS. The verifier proves each is neither defined
# nor referenced in its sandbox, so the additive write cannot collide.
#
# `active` (a net-new base-2 bit — relational cache of contract status) converges to ONE
# uniform address across every anchor: the only place the numbering is deliberately
# uniform. `entity_kind` is NOT reserved — in the registrar it aliases the existing
# `lcl_id` (3-1-13) above, whose target the `lcl` doc marks as a 'type' node.
RESERVED_NEW_FIELDS: dict[str, dict[str, str]] = {ns: {"active": "3-1-20"} for ns in NAMESPACES}

# Registrar additive fields still awaiting a write. `active` and `dns_present` are
# RELATIONAL booleans derived at export time (network_map_viewer) rather than stored — a
# stored base-2 bit is deferred (there is no base-2 radix, and no `micyte-<msn_id>.bin`
# exists yet). ipv4/ipv6/website (and profile-only `social`) are already promoted into
# FIELD_ADDRESS above by the registrar-card backfill.
RESERVED_NEW_FIELDS[REGISTRAR] = {
    "active": "3-1-20",
    "dns_present": "3-1-25",
}

# The canonical logical vocabulary (every field any anchor defines + the pending additive
# fields). `entity_kind` enters via FIELD_ADDRESS[REGISTRAR] (aliased to lcl_id).
CANONICAL_FIELDS = (
    frozenset(f for table in FIELD_ADDRESS.values() for f in table)
    | frozenset(f for table in EXTRA_FIELDS.values() for f in table)
    | frozenset(f for table in RESERVED_NEW_FIELDS.values() for f in table)
)


# --- Resolution API ---------------------------------------------------------------


def namespace_for_sandbox(sandbox: str) -> str:
    """Map a live sandbox token to its field-registry namespace."""
    key = _text(sandbox)
    try:
        return NAMESPACE_BY_SANDBOX[key]
    except KeyError:
        raise KeyError(f"no field-registry namespace for sandbox {key!r}") from None


def _namespace(anchor: str) -> str:
    """Accept either a namespace name or a sandbox token; return the namespace."""
    key = _text(anchor)
    if key in FIELD_ADDRESS:
        return key
    return namespace_for_sandbox(key)


def address(anchor: str, field: str) -> str:
    """The physical ``3-1-N`` address of ``field`` in ``anchor``'s namespace.

    ``anchor`` may be a namespace name or a sandbox token. Raises ``KeyError`` if the
    field is not defined (nor a known borrow) for that namespace.
    """
    ns = _namespace(anchor)
    table = FIELD_ADDRESS[ns]
    if field in table:
        return table[field]
    extra = EXTRA_FIELDS.get(ns, {})
    if field in extra:
        return extra[field]
    raise KeyError(f"field {field!r} is not defined for namespace {ns!r}")


def marker(anchor: str, field: str) -> str:
    """The ``rf.3-1-N`` reference marker for ``field`` in ``anchor``'s namespace."""
    return "rf." + address(anchor, field)


def field_at(anchor: str, addr: str) -> str | None:
    """Reverse lookup: the logical field an ``rf.3-1-N`` / ``3-1-N`` names, or ``None``."""
    ns = _namespace(anchor)
    key = _text(addr)
    if key.lower().startswith("rf.") or key.lower().startswith("ref."):
        key = key.split(".", 1)[1]
    for name, a in FIELD_ADDRESS[ns].items():
        if a == key:
            return name
    return None


def fields(anchor: str) -> frozenset[str]:
    """The logical fields defined by ``anchor``'s namespace (excludes borrows)."""
    return frozenset(FIELD_ADDRESS[_namespace(anchor)])


def has_field(anchor: str, field: str) -> bool:
    """True if ``field`` resolves (defined or a known borrow) for ``anchor``."""
    try:
        address(anchor, field)
        return True
    except KeyError:
        return False
