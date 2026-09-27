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

import contextlib
from collections.abc import Iterable, Iterator


def _text(value: object) -> str:
    """Coerce to str without importing the samras codec (keeps this module a pure leaf
    so ``core`` modules can import it without a cycle)."""
    return value if isinstance(value, str) else str(value)


# --- Namespaces (one per distinct anchor numbering) -------------------------------

SYSTEM = "system"          # the system anthology + agro_erp `Markers` vocabulary
REGISTRAR = "registrar"    # the registrar entity directory (its own numbering)
TAXONOMY = "taxonomy"      # the taxonomy anchor
FARM = "farm"              # both farms (structurally identical anchors)
ARCHETYPE = "archetype"    # the archetype library's own anchor (TASK-2026-08-06-004)
# The glyph library. The FIRST anchor in the corpus whose numbering was CHOSEN rather than
# copied — which is why it can be five babelettes instead of eighteen, and why its
# `grid_point` sits at 4-1-1: that abstraction's chain is four deep, so its babelette
# cannot live at layer 3 like every other field in this table.
GLYPH = "glyph"

NAMESPACES = frozenset({SYSTEM, REGISTRAR, TAXONOMY, FARM, ARCHETYPE, GLYPH})

# Which namespace each live sandbox anchor speaks.
NAMESPACE_BY_SANDBOX: dict[str, str] = {
    "system": SYSTEM,
    "registrar": REGISTRAR,
    "taxonomy": TAXONOMY,
    # The hosted channel's sandbox. Its anchor is field-for-field the FARM anchor
    # (3-1-1 txa_id, 3-1-2 title, 3-1-3 coordinate, 3-1-4 msn_id, 3-1-5 lcl_id,
    # 3-1-6 utc, 3-1-7 nominal, 3-1-21 fiat) because its `product_profiles` was
    # built to the shape the farm sandbox already used. Undeclared until
    # 2026-08-05, which meant `namespace_for_sandbox("agnet")` RAISED for a
    # sandbox holding 119 live documents — the table was a census of the sandboxes
    # that existed when it was written, not of the ones that exist.
    "agnet": FARM,
    # The grantor channel's books speak the same vocabulary as agnet's roster
    # (channel_account rows: msn_id, title, lcl_id, utc) — FARM carries all four.
    "grantor": FARM,
    # Onboarded INSTANCE sandboxes. `bootstrap_handyman_sandbox` copies registrar/anchor
    # verbatim, so an instance's numbering IS the registrar's — the same reason the
    # archetype library speaks REGISTRAR below 3-1-28.
    #
    # A namespace is a CLAIM about an anchor's numbering and nothing yet derives one from
    # the anchor itself, so an instance's claim has to be stated. It is stated in
    # NAMESPACE_BY_INSTANCE (address-only) or in the instance's own config — NOT here.
    # This table is keyed on the NAME, and since the 2026-08-14 standardization every
    # instance names its core sandbox `system`, so a name-keyed entry cannot identify one.
    #
    # Three entity-named entries were removed on 2026-08-22. They named a real family or
    # business, in the package the repo split publishes, and they were dead: all three of
    # those sandboxes hold zero documents since the rename. Not restated here, for the same
    # reason they were removed.
    # The archetype library. Its anchor is the REGISTRAR stack copied verbatim, extended
    # with the six fields the registrar has no babelette for, so its numbering IS the
    # registrar's below 3-1-28. That looks arbitrary for a namespace meant to be canonical
    # — `coordinate` at 3-1-1, `title` at 3-1-3 — and it is deliberate: the archetype
    # fold resolves LOGICAL names, so a sandbox's physical numbering is invisible to every
    # match. Inventing a "nicer" numbering would have meant authoring radix rows from
    # scratch, and a radix nobody can derive is worse than an ugly address anybody can
    # trace to the anchor it was copied from.
    "archetype": ARCHETYPE,
    # The glyph library. Only FND holds it; every other instance IMPORTS it as a source,
    # so a consumer never speaks this namespace — it reads glyphs by lcl address.
    "glyph": GLYPH,
}

#: ``(msn_id, sandbox) -> namespace`` — the address a namespace is really keyed on.
#:
#: Every instance keeps its own core sandbox named ``system``, so the NAME alone stops
#: identifying one. These entries are consulted first and the name-keyed table above is the
#: fallback for sandboxes only one instance can hold (``registrar``, ``taxonomy``, ``agnet``,
#: ``archetype``).
#:
#: An instance's numbering is its ANCHOR's, and an instance anchor is copied verbatim from
#: the registrar's (`bootstrap_handyman_sandbox`) or from the farm template
#: (`bootstrap_farm_sandbox`) — which is exactly what these say. The entries are stated per
#: instance rather than derived because the anchors cannot yet answer: measured 2026-08-14,
#: the registrar's anchor declares 18 field babelettes and the farm anchors declare THREE,
#: so the table carries what the anchors do not. Deriving it is the right end state and is
#: not available today; claiming otherwise would put a guess where a claim belongs.
#: THE PARTY NAMES ARE GONE (2026-08-22). This dict used to hold seven entries; three keyed a
#: sandbox named after a real business or family against that party's live msn. ``micyte/``
#: is the package the repo split publishes, so those three were a customer list with network
#: addresses attached, bound for clones that could never be recalled. They are not repeated
#: here — a comment explaining a removed disclosure that restates it has removed nothing.
#:
#: They were also DEAD. The 2026-08-14 standardization renamed every one of those sandboxes
#: to ``system``; measured 2026-08-22, all three hold **zero documents**. They were removed,
#: not relocated, because a binding for a sandbox that does not exist is not a binding.
#:
#: What remains is address-only: four ``(msn, "system")`` pairs, no party named. These STAY
#: in the package rather than moving to config, and the first attempt to move them is why
#: that is worth stating. A unit test, a script, a one-off REPL — none of them run the
#: portal's boot replay, so an empty table there does not fail, it FALLS BACK to
#: NAMESPACE_BY_SANDBOX and resolves ``system`` to FND's numbering for all four instances.
#: Two live-reading tests caught it (``test_agronomics_viewer``, ``test_editable_table_columns``)
#: by rendering the wrong container; nothing raised. The table earns its place in the package
#: by being what makes resolution correct in EVERY process, not just the booted one.
#:
#: Config can still ADD claims without a code edit — see :func:`declare_instance_namespace`
#: and ``apply_declared_instance_namespaces``. That is what onboarding an instance needs, and
#: it is why the loader exists; this dict is the floor it builds on, not a thing it replaces.
NAMESPACE_BY_INSTANCE: dict[tuple[str, str], str] = {
    ("3-2-3-17-77-1-6-4-1-4", "system"): SYSTEM,
    ("3-2-3-17-77-1-6-34-1-3", "system"): REGISTRAR,
    ("3-2-3-17-77-2-6-3-1-6", "system"): FARM,
    # A fourth farm sat here until 2026-08-26. Its instance was retired at the operator's
    # instruction — not a client — and its `system` sandbox holds no documents at all now,
    # so the claim had nothing left to be a claim ABOUT. The entity itself is untouched:
    # it is still a real farm with registrar and agnet directory rows, which is why the
    # retirement stopped at the instance and why its msn stays in the public-package
    # allowlists. A namespace claim is about a (msn, SANDBOX) pair, and that pair is gone.
}

#: ``(msn_id, sandbox) -> namespace`` claims REGISTERED at runtime — the store-backed half
#: of the table above. An app manifest declares the namespace its copied anchor speaks;
#: installing the app registers it here (and persists it in the instance's config, which
#: the host replays at boot). This is what closes the "onboarding a customer needs a hand
#: edit and a deploy" limitation the hand table documents about itself.
#:
#: The HAND TABLE WINS: it is a verified claim, a registration is a manifest's, and where
#: the two disagree :func:`register_instance_namespace` refuses rather than merging —
#: silently preferring either one would relabel every cell in the sandbox.
_REGISTERED_INSTANCE_NAMESPACES: dict[tuple[str, str], str] = {}


def register_instance_namespace(
    msn_id: str, sandbox: str, namespace: str, *, source: str = ""
) -> str:
    """Record that ``(msn_id, sandbox)``'s anchor speaks ``namespace``.

    Returns ``"registered"``, or ``"already-declared"`` when the claim is already known
    with the SAME value (hand table or a prior registration — re-running an install is
    not an error). Raises ``ValueError`` on an unknown namespace or on a CONFLICT with an
    existing claim: a conflict means the manifest and the anchor disagree about what
    every ``rf.3-1-N`` in the sandbox means, and that is a refusal, not a preference.
    """
    msn, key, ns = _text(msn_id).strip(), _text(sandbox).strip(), _text(namespace).strip()
    if not (msn and key):
        raise ValueError("an instance namespace is keyed on (msn_id, sandbox); both are required")
    if ns not in NAMESPACES:
        raise ValueError(
            f"unknown field-registry namespace {ns!r}; expected one of {sorted(NAMESPACES)}"
        )
    existing = NAMESPACE_BY_INSTANCE.get((msn, key)) or _REGISTERED_INSTANCE_NAMESPACES.get((msn, key))
    if existing:
        if existing == ns:
            return "already-declared"
        raise ValueError(
            f"({msn!r}, {key!r}) is already declared to speak {existing!r}; "
            f"{source or 'a registration'} claims {ns!r}. Refused — accepting either "
            "silently would relabel every cell in the sandbox."
        )
    _REGISTERED_INSTANCE_NAMESPACES[(msn, key)] = ns
    return "registered"


def declare_instance_namespace(
    msn_id: str, sandbox: str, namespace: str, *, source: str = ""
) -> str:
    """Record a VERIFIED claim that ``(msn_id, sandbox)``'s anchor speaks ``namespace``.

    The tier that used to be a literal table in this module. Same contract as
    :func:`register_instance_namespace` — ``"declared"``, ``"already-declared"`` when the
    claim is already known with the SAME value, ``ValueError`` on a conflict — but the claim
    lands in :data:`NAMESPACE_BY_INSTANCE`, which OUTRANKS a registration.

    A conflict is refused here for the reason it is refused there: two claims about one
    anchor's numbering do not average. Accepting either would relabel every ``rf.3-1-N`` in
    the sandbox, and nothing would error.
    """
    msn, key, ns = _text(msn_id).strip(), _text(sandbox).strip(), _text(namespace).strip()
    if not (msn and key):
        raise ValueError("an instance namespace is keyed on (msn_id, sandbox); both are required")
    if ns not in NAMESPACES:
        raise ValueError(
            f"unknown field-registry namespace {ns!r}; expected one of {sorted(NAMESPACES)}"
        )
    existing = NAMESPACE_BY_INSTANCE.get((msn, key)) or _REGISTERED_INSTANCE_NAMESPACES.get((msn, key))
    if existing:
        if existing == ns:
            return "already-declared"
        raise ValueError(
            f"({msn!r}, {key!r}) is already declared to speak {existing!r}; "
            f"{source or 'a declaration'} claims {ns!r}. Refused — accepting either "
            "silently would relabel every cell in the sandbox."
        )
    NAMESPACE_BY_INSTANCE[(msn, key)] = ns
    return "declared"


@contextlib.contextmanager
def instance_namespaces_isolated(
    declared: dict[tuple[str, str], str] | None = None,
) -> Iterator[None]:
    """Snapshot BOTH claim tiers, optionally seed the verified one, restore on exit.

    Needed since 2026-08-22, when :data:`NAMESPACE_BY_INSTANCE` stopped being a literal and
    became state loaded at boot. A module-level dict that tests write into leaks between
    them: the first symptom was a test declaring ``(FND, "system")`` as ``farm`` and a later,
    unrelated test refusing a correct registration because of it.

    Both tiers are restored, not just the one a caller touched, because the tiers consult
    each other — a conflict check reads the verified tier and the registered tier together,
    so leaving either dirty makes the NEXT test's refusal depend on test order.
    """
    saved_declared = dict(NAMESPACE_BY_INSTANCE)
    saved_registered = dict(_REGISTERED_INSTANCE_NAMESPACES)
    try:
        if declared is not None:
            NAMESPACE_BY_INSTANCE.clear()
            NAMESPACE_BY_INSTANCE.update(declared)
        yield
    finally:
        NAMESPACE_BY_INSTANCE.clear()
        NAMESPACE_BY_INSTANCE.update(saved_declared)
        _REGISTERED_INSTANCE_NAMESPACES.clear()
        _REGISTERED_INSTANCE_NAMESPACES.update(saved_registered)


def declared_instance_namespaces() -> dict[tuple[str, str], str]:
    """A copy of the VERIFIED claims, for tests and posture surfaces."""
    return dict(NAMESPACE_BY_INSTANCE)


def registered_instance_namespaces() -> dict[tuple[str, str], str]:
    """A copy of the runtime-registered claims, for tests and posture surfaces."""
    return dict(_REGISTERED_INSTANCE_NAMESPACES)


def _instance_namespace(msn: str, sandbox: str) -> str | None:
    """The paired claim for ``(msn, sandbox)`` — hand table first, then registered."""
    return (
        NAMESPACE_BY_INSTANCE.get((msn, sandbox))
        or _REGISTERED_INSTANCE_NAMESPACES.get((msn, sandbox))
    )


#: The one sandbox name EVERY instance uses for its core, so the name cannot say WHOSE.
#: Every other name in :data:`NAMESPACE_BY_SANDBOX` belongs to a sandbox only one instance
#: holds, and for those the name is a complete answer.
CORE_SANDBOX_NAME = "system"


def name_answers_for(sandbox: str) -> bool:
    """Can the sandbox NAME alone identify a namespace, with no instance to pair it to?

    Yes for `registrar`, `taxonomy`, `agnet`, `grantor`, `archetype` — one instance holds
    each, so the name IS the address. No for `system`: every instance's core sandbox
    carries that name, so it identifies a sandbox on four instances at once and answers
    correctly for one of them.

    This is the line :func:`namespace_for_sandbox`'s fallback already draws in prose. It is
    written down as a predicate because a CALLER needs it: an installer resolving a copied
    anchor's provenance may safely trust the name for the first group and must refuse for
    the second, and it cannot tell them apart by asking what the name resolves to — both
    return a real namespace.
    """
    key = _text(sandbox)
    return bool(key) and key != CORE_SANDBOX_NAME and key in NAMESPACE_BY_SANDBOX


def claimed_namespace(msn_id: str, sandbox: str) -> str:
    """The namespace CLAIMED for this exact pair, or ``""``. Never the name fallback.

    A different question from :func:`namespace_for_sandbox`, and the difference is the
    whole reason this exists. That function answers *"what numbering should I read this
    sandbox with"* and falls back to the sandbox NAME when the pair is unclaimed — which
    is right for `registrar`/`taxonomy`/`agnet`, sandboxes only one instance can hold.

    It is wrong for anything asking *"has somebody actually claimed this"*, because the
    fallback returns a REAL namespace rather than raising. Measured 2026-08-26: installing
    an app from a process that had not replayed the claims resolved MLN's copied `system`
    anchor to the namespace named `system` — and the installer's own guard for exactly
    this case is a `KeyError` branch that can therefore never fire. It wrote
    `pim -> system` into the live config as a durable claim, and the app's local domain
    could not seed because `system` has no lcl vocabulary.

    So: ask THIS when an absent claim should stop you, and `namespace_for_sandbox` when
    you need a numbering to read with. A plausible wrong answer is worse than an error,
    and one function cannot give both.
    """
    from micyte.core.instance_scope import resolve_msn

    msn = _text(resolve_msn(msn_id))
    if not msn:
        return ""
    return _instance_namespace(msn, _text(sandbox)) or ""

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
        # --- SITE ANALYTICS (2026-08-28) -----------------------------------------
        # What a month of traffic to an instance's own website amounts to. Four counts,
        # because they are four facts a client acts on differently: `site_visitors` is
        # people, `site_sessions` is visits, `site_views` is pages, and `site_bots` is
        # what was EXCLUDED from the other three — without which a visitor count that
        # fell cannot say whether the traffic changed or the filtering did.
        #
        # ASCII over the 2-1-1 baciloid, which is what every other magnitude here does:
        # `tiu_magnitude` at 3-1-16 grounds at 2-1-1 in the live registrar anchor, and a
        # count is the same kind of value. Inventing a numeric radix for four fields would
        # be a second way to write a number.
        #
        # 3-1-42..45 was MEASURED free before it was taken, on both halves the registry
        # distinguishes: free in FIELD_ADDRESS, EXTRA_FIELDS and RESERVED_NEW_FIELDS
        # across every namespace, and ZERO live cells at any of the four across all 762
        # instance documents. 3-1-36..40 are uniformly reserved (site_msn, project_ref,
        # status_ref, lead_ref, supply_ref) and 3-1-41 is `length`, so 42 is the first
        # address AFTER the reserved band rather than a gap inside it — the mistake
        # `length` made once, when it took 3-1-36 from `site_msn`.
        #
        # Prefixed `site_` deliberately: these count traffic to a WEBSITE, in a namespace
        # shared with entity and place fields where a bare `visitors` would read as
        # somebody's guests. The same prefix `site_msn` uses one band down.
        "site_visitors": "3-1-42",
        "site_sessions": "3-1-43",
        "site_views": "3-1-44",
        "site_bots": "3-1-45",
        # msn contact-card fields (Phase C.2 registrar-card backfill) — plaintext
        # strings over niu-baciloid-256-64 (2-1-1), mirroring email/dns; empty when absent.
        # ipv4/ipv6/website are card fields; `social` is profile-only (leaflet-fold target).
        "ipv4": "3-1-22",
        "ipv6": "3-1-23",
        # The instance's PUBLIC SIGNATURE: base64 of the raw 32-byte Ed25519 public key
        # (44 chars, so it fits the 64-char babelette a PEM would overflow). Published in
        # the contact card because that is what makes "this request is from msn X"
        # checkable by anyone holding the card — a contract must never carry the key that
        # authorises it, which would be circular. Empty for a node with no instance.
        # 3-1-17 rather than a slot in the 22..26 card block: 3-1-20/21 are uniformly
        # reserved (active/price) and 3-1-25 is reserved for the registrar's dns_present,
        # so 3-1-17..19 are the only free-and-unreserved addresses below 28.
        "public_signature": "3-1-17",
        # WHERE this instance answers contract traffic: an https origin, e.g.
        # "https://portal.fruitfulnetworkdevelopment.com". Published in the card for the
        # same reason the signature is — a contract request has to be DELIVERED before
        # any contract exists to carry an address, so the card is the only document that
        # can hold it. Deliberately NOT `dns` (3-1-9): that cell holds an ordinary
        # website domain, which 129 of 236 nodes carry and almost none of which answer a
        # handshake. Empty for a node that runs no reachable instance, which is most of
        # them — and publishing one is the opt-in to being reachable at all.
        "instance_endpoint": "3-1-18",
        "website": "3-1-24",
        "social": "3-1-26",
        # The instance that HOSTS a hosted channel, when that differs from the entity
        # the row is about — a channel hosted on behalf of someone else. The channels
        # doc's first rows needed no such cell (FND hosts its own channel).
        #
        # NOTHING carries it today: the one row that did (county_line_records) was
        # retired 2026-08-04. The address stays reserved anyway — a reservation states
        # what an address MEANS, not that something currently uses it, and freeing it
        # would invite a reuse that collides with every historical row.
        "hosting_msn": "3-1-27",
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
        # Site analytics, at the SAME addresses registrar and archetype take them at.
        # A farm instance has a website like any other and its traffic is counted the
        # same way, so the field converges to one address across every namespace that
        # holds it — the rule `price` and `hyphae_ref` already state: a value written in
        # one sandbox and read by another has to be the same field.
        #
        # Farm numbers its OWN fields at 3-1-1..7, nowhere near this band, so nothing
        # collides and no rename is needed here — unlike the `lcl_id` borrow above.
        "site_visitors": "3-1-42",
        "site_sessions": "3-1-43",
        "site_views": "3-1-44",
        "site_bots": "3-1-45",
        "lcl_id": "3-1-5",
        "utc": "3-1-6",
        "nominal": "3-1-7",
    },
    # The archetype library: the registrar block verbatim (every address below 3-1-28 is
    # the registrar's, because the anchor is its stack copied row for row), plus the six
    # fields the archetype vocabulary needs and the registrar has no babelette for. Those
    # six sit at 3-1-30+ because 3-1-19 is the only free address below 28 and 3-1-20/21/
    # 25/28/29 are uniformly reserved.
    ARCHETYPE: {
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
        "entity_kind": "3-1-13",
        "resource_kind": "3-1-14",
        "ic_stamp": "3-1-15",
        "tiu_magnitude": "3-1-16",
        "public_signature": "3-1-17",
        "instance_endpoint": "3-1-18",
        "ipv4": "3-1-22",
        "ipv6": "3-1-23",
        "website": "3-1-24",
        "social": "3-1-26",
        "hosting_msn": "3-1-27",
        # copied from the taxonomy anchor, which is the only one that defines them
        "txa_id": "3-1-30",
        "nominal": "3-1-31",
        "common_name": "3-1-32",
        "icon_ref": "3-1-33",
        # the farm anchor-gap fields, given a real address here rather than a borrow
        "view": "3-1-34",
        "name": "3-1-35",
        # Site analytics, at the SAME addresses the registrar takes them at — see the
        # block there. The library needs them because an archetype document's own row
        # carries the markers, and `document_row_shapes` folds that row through THIS
        # namespace: a field the library cannot name is an archetype it cannot declare.
        "site_visitors": "3-1-42",
        "site_sessions": "3-1-43",
        "site_views": "3-1-44",
        "site_bots": "3-1-45",
        # The two spatial fields, so the library can hold an archetype for a DRAWING. The
        # fold resolves logical names, so an arc row folds to the same shape here and in
        # the glyph sandbox even though the anchors number them differently -- which is
        # exactly what the decoder ring is for.
        #
        # `grid_point` is 4-1-1 in BOTH anchors, and not by coincidence: a babelette's
        # layer is its chain's depth, the chain is four deep, and there is nowhere else it
        # could go. `length` is three deep, so it lands at the next free 3-1.
        "length": "3-1-41",
        "grid_point": "4-1-1",
    },
    # The glyph library's own anchor. Authored, not copied, so it holds exactly the five
    # fields a drawing and its log need and no reserved gaps.
    #
    # `grid_point` is the one field in this whole table that is NOT a `3-1-N`. Its chain
    # is `((((siu;512:);512:);1:);0)` — four deep — and a babelette's layer IS its chain's
    # depth, so it lands at 4-1-1 and rows referencing it are layer 5. Writing it at 3-1-N
    # to match the others would be a claim about the anchor that the anchor contradicts.
    GLYPH: {
        # UNIFORM with the archetype library, and for the reason `site_msn` is uniform: a
        # length written here and read by the sandbox that imported the glyph has to be
        # the same field. The first cut put it at 3-1-2, the next free address in an
        # anchor of five fields, and 28 tests caught the sibling mistake one slot up --
        # `length` had taken 3-1-36, which every namespace reserves for `site_msn`.
        "grid_point": "4-1-1",
        "length": "3-1-41",
        "title": "3-1-3",
        # 3-1-13, not the next free address, and NOT a matter of taste. Two tables below
        # this one are keyed on the LITERAL marker and know nothing about namespaces:
        # `datum_resolve._KIND_BY_MARKER` decides whether a node is a type or an instance,
        # and `refs.NODE_REF_MARKERS` decides whether a magnitude is a node reference at
        # all. Both know exactly three spellings — 3-1-1, 3-1-5, 3-1-13 — so an authored
        # anchor that put its lcl vocabulary anywhere else would seed a local domain the
        # editor cannot read (measured: `seeded_local_domain_rows` refuses it BY NAME) and
        # write icon references no reader would follow.
        #
        # Of the three, 3-1-13 is the one that reads as a TYPE and belongs to an lcl
        # vocabulary rather than an agro node id, which is what these nodes are. The gap
        # from 3-1-3 to 3-1-13 is real and stays: reserved, not free.
        "lcl_id": "3-1-13",
        # 3-1-7, the farm/taxonomy spelling. Not 3-1-5, which the tables above read as an
        # INSTANCE node id — a fill flag written there would be followed as a reference.
        "nominal": "3-1-7",
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
        # `dns` at registrar's own address, measured rather than inferred: 118 of the
        # 181 rows in `agnet/member_ag_profiles` cite rf.3-1-9 and every one holds a
        # domain -- akron-microgreens.com, auroraspringshoney.com, bakersproduce.com.
        # Registrar defines 3-1-9 as `dns`, so this is that field, borrowed.
        #
        # It keeps registrar's NAME because it can: farm defines no `dns` of its own and
        # nothing else in farm sits at 3-1-9. The neighbouring borrows rename only where
        # they had to -- 3-1-8 is `view` here and `email` in registrar -- so a borrow
        # taking the source name is not an inconsistency, it is the absence of a
        # collision.
        "dns": "3-1-9",
        "view": "3-1-8",                # record-view token (agro tools) — anchor gap
        "retire": "3-1-10",             # effective-dating retire stamp — anchor gap
        "visual": "3-1-11",             # profile visual ref (0-0-11) — anchor gap
        "mss_source_binary": "3-1-12",  # borrow <- registrar
        # The registrar's `lcl_id`, borrowed, and RENAMED because it had to be: farm
        # defines its own `lcl_id` at 3-1-5, so the source name would collide. It takes
        # the registrar's OTHER name for the same address — `entity_kind` already aliases
        # 3-1-13 there — rather than an invented one, so the two namespaces still name
        # this field with one word. Free in farm: nothing is defined, borrowed or
        # reserved at 3-1-13 here, and `entity_kind` is absent from farm entirely.
        #
        # MEASURED, not inferred (2026-08-28). All 181 rows of `agnet/member_ag_profiles`
        # carry a 3-1-13 cell; 12 distinct values; every one resolves in the REGISTRAR's
        # local domain with exactly the label that row's own tail names:
        #
        #     1-2-1-1 crop (88)   1-2-1-2 orchard (13)   1-2-1-3 pasture (11)
        #     1-2-1-4 farmstand   1-2-1-5 apiary         1-2-1-6 vineyard
        #     1-2-2 farmers_market_host (24)   1-2-3 csa_operator   1-2-4 food_hub
        #     1-2-5 seed_supplier  1-2-6 organization   1-2-7 administrative_sponsor (22)
        #
        # 12 of 12. `1-2` is `ag_profile` there and `1-2-1` is `producer`.
        #
        # THE BLOCKER THAT WASN'T. TASK-2026-08-22-001 recorded this as un-declarable
        # because "SIX of the twelve are absent from agnet's local domain log, including
        # 1-2-1-1, cited by 88 of the 181 rows" — true, and the wrong tree. agnet's own
        # lcl belongs to ONE MEMBER FARM (its `1-2` is `land` → parcel/field/structure/
        # plot), so the addresses collide there by coincidence and mean nothing. The
        # document borrows registrar NUMBERING for every marker it uses
        # (3-1-1 coordinate, 3-1-2 msn_id, 3-1-3 title, 3-1-9 dns, 3-1-13), so its lcl
        # values are registrar lcl nodes — and its only reader already knows: `domains/
        # registry/directory.py` matches them with `marker(REGISTRAR, "lcl_id")`.
        #
        # So this is the second of the two agnet borrows the task recommends settling by
        # declaration. 3-1-9 was declared, 3-1-13 was not, and EXTRA_FIELDS[FARM] read
        # 3-1-8..3-1-14 with one gap. The gap was the bug.
        "entity_kind": "3-1-13",        # borrow <- registrar (its `lcl_id`, renamed)
        "resource_kind": "3-1-14",      # borrow <- registrar
    },
    REGISTRAR: {
        # A contact's phone number is a nominal babelette (the operator's `nominal-256-13`),
        # and the registrar anchor has no nominal row: 3-1-7 is `sosvid` here, so the farm's
        # own `nominal` address CANNOT be reused — a phone written at 3-1-7 in a
        # registrar-namespace sandbox would read as a vital-record identifier.
        #
        # 3-1-31 is not invented for this. It is what the ARCHETYPE anchor already compiled
        # as `nominal-babelette` (mint_archetype_sandbox.BABELETTE_PLAN, backed by 2-1-4 =
        # the taxonomy's nominal radix), so borrowing it means the archetype library and its
        # registrar-namespace consumers name one field with one number. Measured free before
        # taking it: 0 cells at 3-1-31 across every registrar-namespace sandbox in the live
        # store, and it collides with nothing defined, borrowed or reserved here.
        #
        # This is a BORROW, so it is an expected dangler until the registrar anchor grows the
        # babelette — the "Phase C" this table's own header describes. `verify_field_registry`
        # Check 2 reads it from here and reports `[borrow]`, never `[dangling]`.
        "nominal": "3-1-31",            # borrow <- archetype/taxonomy (contact phone)
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
#
# `price` converges to one uniform address for the same reason: a price written in a farm
# and a price read by the taxonomy sandbox that lent it the product profile have to be the
# same field. `3-1-21` is verified free — neither defined as a row nor referenced as an
# `rf.` marker — in every live namespace. It stays RESERVED rather than promoted because the
# field is real only once a sandbox's anchor actually defines the fiat chain; the write path
# resolves it by structural discovery (`core.datum_ops.fiat_datum.find_fiat_chain`), and
# this entry records the address a provisioner should ask for, not one a reader may assume.
# `hyphae_ref` converges uniformly for the same reason `price` does, one step further
# out: it is a NETWORK-layer citation, and a reference written in one sandbox is read by
# another. Its value is a magnet reference — `hy.<msn>.<sandbox>.<document>.<hash>.<addr>`
# — which names a ROW in a document, where `rf.3-1-1` names a POSITION in a tree.
#
# It is a COMPANION to the coordinate, never a replacement. `rf.3-1-1` is the box-wide
# marker for a SAMRAS node coordinate: `micyte/channels/agnet.py`,
# `micyte/tools/profile_projection.py`, `audit_txa_registry.py` and the `mutate_txa`
# cross-sandbox cascade all read it as one. Giving it a second value language would be
# the ambiguity `docs/.../90-network-contract-architecture` rejects `rf.` for in the
# first place. Two denotations of one join is also the only way a bad cascade leaves
# evidence: one denotation cannot disagree with itself.
#
# 3-1-28 is verified free against the LIVE store — neither defined as an anchor row nor
# referenced as an `rf.` marker in any of the 626 documents — by
# `evidence/fnd-network-posture-audit-2026-08-04/p3_free_address.py`. 3-1-19 is free too
# and deliberately not taken: the registrar comment above reserves 3-1-17..19 as its
# last slots below 28.
#
# `observed_by` (3-1-29, added 2026-08-05 for P4) is the third network-layer field and
# converges for the same reason. It names WHO OBSERVED a record, which is a different
# fact from whose record it is: the subject of a market report is the auction, but two
# independent parties publish reports about the same auction — measured, 3,437 (day,
# product) pairs are reported by both and 1,689 of those agree on price to within 1%.
# Until now that fact lived in a DOCUMENT NAME (`market_lots_mt_hope` vs
# `market_lots_usda_mt_hope`), which is not a denotation at all.
#
# Its value is a DOCUMENT-LOCAL datum address, not a `hy.` magnet: the observer row sits
# in the same document as the records that cite it, and within one document a row address
# is already that datum's complete name — nothing to pin, nothing to go stale. It also
# means `datum_semantics.engine._row_local_refs` picks the edge up unaided, so the
# dependency is recorded and `delete_target_row_still_referenced` refuses to drop an
# observer while records still cite it. Cross-DOCUMENT citation stays `hyphae_ref`.
#
# 3-1-29 re-verified free against the live store after P3's writes (p3_free_address.py).
# 3-1-25 is NOT free — `dns_present` reserves it below.
# `site_msn` (3-1-36, added 2026-08-07 for the job-event archetype) is the fourth uniform
# additive field, and it exists because TWO CELLS OF THE SAME KIND ARE NOT THE SAME FIELD.
#
# A job names a person and a place, and both are msn node addresses. Writing them as two
# `msn_id` cells makes the row fold to `L4:msn_id+,…` — the shape's run-collapse is what
# lets one archetype cover a 9-vertex ring and a 29-vertex one, and here it would erase the
# difference between who and where. Worse for the reader: `_viewscope._row_values` keys by
# LOGICAL FIELD, so both addresses arrive in one list and no viewscope slot can label
# either. `region_polygon_ref` is the precedent — an msn address under its own name because
# it means a particular thing.
#
# It converges uniformly for the reason `price` does: a site written by one instance is
# read by another, and a job at an address is not a farm-only or registrar-only fact.
#
# **3-1-36, not 3-1-19.** 3-1-19 is free and deliberately NOT taken — the registrar comment
# above reserves 3-1-17..19 as its last slots below 28, and spending someone else's reserved
# range because it happens to be empty is how a numbering convention stops being one.
# 3-1-36 is verified free against the live store: **0 marker cells** across all 549
# documents (the 9 documents whose payload contains the substring carry it inside HOPS
# coordinate tokens and txa addresses, not as a marker).
RESERVED_NEW_FIELDS: dict[str, dict[str, str]] = {
    ns: {
        "active": "3-1-20",
        "price": "3-1-21",
        "hyphae_ref": "3-1-28",
        "observed_by": "3-1-29",
        "site_msn": "3-1-36",
        # The Quiar job extensions (TASK-2026-08-14-002 Phase 3b). Three FIELDS, not one,
        # although two hold lcl addresses and run-collapse would otherwise merge them with
        # `lcl_id` — a status and a lead source are different facts about a job, the rule
        # `site_msn` established for msn cells. Addresses verified free by MARKER CELL
        # against the live store, 2026-08-15: 0 of each across 106,583 rows.
        #   project_ref — the datum row address, in this sandbox's `projects` document,
        #                 of the standing thing the job is done against;
        #   status_ref  — an lcl node: where the job sits in the pipeline the instance
        #                 mints for itself;
        #   lead_ref    — an lcl node: how the work arrived.
        "project_ref": "3-1-37",
        "status_ref": "3-1-38",
        "lead_ref": "3-1-39",
        # The supply-backed planting reference (TASK-2026-08-14-002 batch re-point): the
        # datum row address, in this sandbox's `invoices` document, of the supply batch a
        # planting consumes — the `project_ref` idiom, its own field per the site_msn
        # rule. NOT a `hy.` magnet: `invoices` changes content hash on every append, so a
        # pinned citation would go stale immediately (the `observed_by` lesson); and not
        # document-local, because the planting and its batch live in different documents.
        # Verified free by MARKER CELL against the live store, 2026-08-15: 0 cells across
        # 106,405 rows / 598 documents.
        "supply_ref": "3-1-40",
        # The two SPATIAL fields (TASK-2026-08-20-002). Uniform for the `site_msn` reason
        # one step further out: a glyph is PUBLISHED — the whole point of the library is
        # that other instances import it — so a length or a point read in a sandbox that
        # did not write it has to be the same field there.
        #
        # `grid_point` is the only field in this file outside `3-1`, and it could not be
        # anywhere else: a babelette's layer IS its chain's depth, and
        # `((((siu;512:);512:);1:);0)` is four deep.
        "length": "3-1-41",
        "grid_point": "4-1-1",
        # The INCLUDED allowance on an offer (TASK-2026-08-31-005, 2026-09-11): how many
        # units a subscription gets before the unit price applies — "the first two
        # mailboxes are in the base price". Its own field for the `site_msn` reason:
        # `nominal` on an offer is the UNIT ("per mailbox") and on a subscription the
        # QUANTITY, and a second nominal on the offer would be two cells of one kind
        # standing for one field. Uniform across namespaces because the grantor's books
        # are read by the client's PIM. Verified free by MARKER CELL against the live
        # store, 2026-09-11: 3-1-42..45 are the site analytics fields three anchors
        # define; 3-1-46 is carried by 0 documents and defined by no namespace.
        "included_units": "3-1-46",
    }
    for ns in NAMESPACES
}

# Registrar additive fields still awaiting a write. `active` and `dns_present` are
# RELATIONAL booleans derived at export time (network_map_viewer) rather than stored — a
# stored base-2 bit is deferred (there is no base-2 radix, and no `micyte-<msn_id>.bin`
# exists yet). ipv4/ipv6/website (and profile-only `social`) are already promoted into
# FIELD_ADDRESS above by the registrar-card backfill.
# MERGED, not replaced. Assigning a fresh dict here drops every uniform field above it —
# which is exactly what happened to `price` the first time it was added, silently, because
# nothing reads this table at import time to notice.
RESERVED_NEW_FIELDS[REGISTRAR].update({"dns_present": "3-1-25"})

# A field is RESERVED or DEFINED, never both: a reservation says "no anchor grounds this
# yet", and `has_field` / `address` answer differently for the two. The archetype library
# and the glyph library both GROUND the spatial pair, so they drop the reservation.
for _grounded in (ARCHETYPE, GLYPH):
    for _spatial in ("length", "grid_point"):
        RESERVED_NEW_FIELDS[_grounded].pop(_spatial, None)

# The canonical logical vocabulary (every field any anchor defines + the pending additive
# fields). `entity_kind` enters via FIELD_ADDRESS[REGISTRAR] (aliased to lcl_id).
CANONICAL_FIELDS = (
    frozenset(f for table in FIELD_ADDRESS.values() for f in table)
    | frozenset(f for table in EXTRA_FIELDS.values() for f in table)
    | frozenset(f for table in RESERVED_NEW_FIELDS.values() for f in table)
)


# --- Resolution API ---------------------------------------------------------------


def namespace_for_sandbox(sandbox: str, *, msn_id: str = "") -> str:
    """Map a live sandbox to its field-registry namespace.

    Keyed on ``(msn_id, sandbox)`` FIRST, because a sandbox is addressed by the pair and a
    namespace is a claim about one anchor's numbering. Once every instance keeps its own
    core sandbox named ``system``, the name alone answers for all of them at once — and
    answers wrongly for three: the client instance's anchor speaks REGISTRAR, where ``title`` sits at
    ``3-1-3``, while ``system`` speaks SYSTEM, where it sits at ``3-1-5``. Nothing would
    error; every cell in its contacts and job log would simply mean something else.

    Falls back to the name for a sandbox only one instance can hold — ``registrar``,
    ``taxonomy``, ``agnet``, ``archetype`` — which is every sandbox that is not an
    instance's core one.
    """
    from micyte.core.instance_scope import resolve_msn

    key = _text(sandbox)
    # Explicit wins, else the request's instance scope — the same order the store
    # reads use, because a namespace and a document read must agree about WHOSE
    # sandbox they are talking about.
    msn = _text(resolve_msn(msn_id))
    if msn:
        paired = _instance_namespace(msn, key)
        if paired:
            return paired
    try:
        return NAMESPACE_BY_SANDBOX[key]
    except KeyError:
        raise KeyError(
            f"no field-registry namespace for sandbox {key!r}"
            + (f" under msn {msn!r}" if msn else "")
        ) from None


def _namespace(anchor: str) -> str:
    """Accept either a namespace name or a sandbox token; return the namespace.

    ``system`` is BOTH — the name of FND's numbering and, since every instance keeps its
    core sandbox under that name, the name of four different sandboxes. This preferred the
    namespace reading and so answered SYSTEM for all of them, which is right for FND and
    wrong for the other three: `writable_fields("system")` reported the client instance's contacts
    document as unable to express `ruiqi_id`, `sosvid`, `nominal` or `website`, on an anchor
    that defines every one of them.

    So an INSTANCE scope that declares this pair wins. It is consulted first and only when
    both are true — there is a scope, and it declares this exact ``(msn, sandbox)`` — so
    nothing changes for a sandbox no instance claims, and FND scoped to itself still gets
    SYSTEM because that is what its pair says.
    """
    from micyte.core.instance_scope import active_instance_msn

    key = _text(anchor)
    scoped = _text(active_instance_msn())
    if scoped:
        paired = _instance_namespace(scoped, key)
        if paired:
            return paired
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
    """Reverse lookup: the logical field an ``rf.3-1-N`` / ``3-1-N`` names, or ``None``.

    Reads all three tables, in precedence order: what the anchor DEFINES, then what it
    borrows or gaps (:data:`EXTRA_FIELDS`), then the uniform additive fields
    (:data:`RESERVED_NEW_FIELDS`). Reading only ``FIELD_ADDRESS`` — as this did — leaves
    every reserved address unnameable, which measured against the live store is 47,569
    market rows whose ``price`` / ``observed_by`` / ``hyphae_ref`` cells read as unknown,
    plus the farm namespace's own borrows. **A reserved address still MEANS the field it
    reserves** — that is the whole content of reserving one — so a reader that meets the
    marker in a row can name it even though no anchor has written the babelette yet.
    :func:`address` deliberately does NOT widen to match: asking where to WRITE a field
    the anchor has not defined must still fail.

    Precedence here is unambiguous rather than merely ordered:
    ``test_reserved_new_field_slots_are_free`` proves per namespace that no reserved
    address collides with a defined or borrowed one, and
    ``test_borrowed_fields_never_shadow_a_defined_one`` proves the same for the borrows.
    Within one table an address MAY carry two names — the registrar's ``lcl_id`` and
    ``entity_kind`` are both 3-1-13 — and declaration order decides: ``lcl_id`` is the
    stored field, ``entity_kind`` is a reading of it.
    """
    ns = _namespace(anchor)
    key = _text(addr)
    if key.lower().startswith("rf.") or key.lower().startswith("ref."):
        key = key.split(".", 1)[1]
    for table in (FIELD_ADDRESS[ns], EXTRA_FIELDS.get(ns, {}), RESERVED_NEW_FIELDS.get(ns, {})):
        for name, a in table.items():
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


def writable_fields(anchor: str) -> frozenset[str]:
    """Every field ``address`` will resolve for ``anchor`` — defined AND borrowed.

    The set form of :func:`has_field`, for callers that need to test many fields at once
    (a tool declaring what it writes, checked against the instance it would run on).

    Deliberately NOT :func:`fields`, which excludes borrows: the registrar resolves
    ``nominal`` at the borrowed 3-1-31, so a contacts tool checked against ``fields`` would
    be refused on the one namespace where it actually works.

    Reads the same two tables, in the same order, as :func:`address` — and RESERVED fields
    are excluded here for the same reason ``address`` excludes them: a reserved address
    records where a provisioner should ask for a field, not somewhere a writer may put one.
    """
    ns = _namespace(anchor)
    return frozenset(FIELD_ADDRESS[ns]) | frozenset(EXTRA_FIELDS.get(ns, {}))


#: The state of one field at ONE pair. The three tables above are keyed per
#: NAMESPACE, and grounding is a fact per ANCHOR — `price` is grounded in six
#: farm-namespace anchors and absent from eight others, and no table with one row
#: per namespace can say that. Three attempts to fix it by EDITING those tables
#: (promote, re-pick, declare-a-borrow) were reverted, each failing in the same
#: place, because the mismatch is not in the answer the tables give. It is in the
#: question they can be asked.
#:
#: So this asks the other question, and asks it WITHOUT a second declaration:
#: the caller supplies what the anchor actually grounds, so the anchor stays the
#: only authority on grounding and the registry stays the only authority on
#: intent. Nothing here is a fact about the store that the store could contradict
#: — which is the trap a per-pair TABLE would have walked into.
#:
#: `address()` is deliberately unchanged and still refuses per namespace. It
#: guards the NEXT writer — `test_address_does_not_widen_the_way_field_at_does`
#: exists so a provisioner cannot write a babelette nothing declares — and that
#: guard is about where it is safe to WRITE. This answers where a field IS.
DEFINED = "defined"                  # the namespace defines it and this anchor grounds it
DECLARED_ABSENT = "declared-absent"  # the namespace defines it and this anchor does NOT
BORROWED = "borrowed"                # a declared cross-namespace borrow
ARRIVED = "arrived"                  # RESERVED, and this anchor already grounds the slot
IN_FLIGHT = "in-flight"              # RESERVED, not grounded, but instance rows cite it
RESERVED = "reserved"                # RESERVED and still genuinely free here
UNKNOWN = "unknown"                  # named in no table for this namespace


def _bare(addr: str) -> str:
    """``rf.3-1-21`` / ``ref.3-1-21`` / ``3-1-21`` -> ``3-1-21``."""
    key = _text(addr)
    if key.lower().startswith("rf.") or key.lower().startswith("ref."):
        key = key.split(".", 1)[1]
    return key


def field_state_at(
    anchor: str,
    field: str,
    *,
    grounded: Iterable[str],
    referenced: Iterable[str] = (),
) -> tuple[str, str]:
    """What ``field`` IS at the pair whose anchor grounds ``grounded``.

    ``grounded`` is that pair's anchor addresses — what the anchor actually
    defines. ``referenced`` is the addresses its instance documents cite. Both
    accept bare or ``rf.``-prefixed addresses.

    Returns ``(state, address)``; ``address`` is ``""`` only for ``UNKNOWN``.

    The distinction ARRIVED vs IN_FLIGHT is the one the flat tables could not
    draw, and it is the difference between two opposite remedies:

    * **IN_FLIGHT** — instance rows cite the reserved address, the anchor does not
      ground it. The corpus is mid-decision. Re-picking here abandons a choice
      already made.
    * **ARRIVED** — the anchor grounds it too. The field is simply THERE, and the
      reservation is mislabelled rather than misplaced. The verifier used to call
      this a collision and advise "pick another"; measured, that advice would have
      stranded 142,759 live ``price`` cells across ten documents.
    """
    ns = _namespace(anchor)
    have = {_bare(a) for a in grounded}
    cited = {_bare(a) for a in referenced}

    table = FIELD_ADDRESS[ns]
    if field in table:
        addr = table[field]
        return (DEFINED if addr in have else DECLARED_ABSENT), addr

    extra = EXTRA_FIELDS.get(ns, {})
    if field in extra:
        return BORROWED, extra[field]

    held = RESERVED_NEW_FIELDS.get(ns, {})
    if field in held:
        addr = held[field]
        if addr in have:
            return ARRIVED, addr
        if addr in cited:
            return IN_FLIGHT, addr
        return RESERVED, addr

    return UNKNOWN, ""
