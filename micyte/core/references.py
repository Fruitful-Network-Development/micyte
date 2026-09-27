"""Cross-instance references: what one instance is declared to read from another.

A farm's product rows are keyed to taxon nodes owned by another instance's
`taxonomy` sandbox. Those references are part of the model, so a rule check that
only knows one sandbox's own definitions reports every one of them as dangling.
The engine therefore needs to know which external nodes are legitimate — and that
must be **declared**, never inferred: "this reference resolves" and "this
reference is allowed" are different questions, and inferring the second from the
first makes every accidental collision legal.

The declaration already exists on disk. `<private>/contracts/contract-<owner>.<
counterparty>.json` (schema `mycite.portal.contract.v2`) names an owner msn, a
counterparty msn, and the `tracked_resource_ids` the owner shares —
`rc.<owner_msn>.txa` and friends. `config.json` registers the file. This module
reads that contract; it does not invent a new format.

Read side only, per the V3 plan: same process, same tenant, no crypto, no
network. `symmetric_key_ref`, the mss handshake fields and `status` govern the
network exchange, which V3 does not perform — so a contract that exists grants
reads here regardless of where its negotiation got to. Only an explicit refusal
withdraws the grant.

Pure functions over already-read data. Callers do the I/O.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from micyte.core.datum_ops import defined_node_addrs
from micyte.core.document_naming import CanonicalNameError, parse_canonical_document_id

CONTRACT_SCHEMA = "mycite.portal.contract.v2"

# A contract whose negotiation ended in refusal grants nothing. Every other
# status (including "pending", where the live FND->farm contract sits) declares
# the relationship, which is all the read side needs.
REFUSED_STATUSES: frozenset[str] = frozenset({"revoked", "rejected", "terminated", "expired"})

# `rc.<owner_msn>.<resource>`
_RESOURCE_PREFIX = "rc."


@dataclass(frozen=True)
class ReferenceGrant:
    """One instance's declared permission to read named resources of another."""

    contract_id: str
    owner_msn_id: str
    consumer_msn_id: str
    resources: tuple[str, ...]
    status: str
    #: The counterparty's Ed25519 public key (PEM), when the contract carries one.
    #: This is what turns "an msn id names the counterparty" into an identity that can
    #: be VERIFIED. Empty for every contract written before closed-channel engagement
    #: existed, and an empty key admits nobody — absence refuses rather than defaults.
    counterparty_public_key: str = ""

    @property
    def is_refused(self) -> bool:
        return self.status.strip().lower() in REFUSED_STATUSES


def _as_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def parse_contract(payload: Any) -> ReferenceGrant | None:
    """Read one contract document into a grant. ``None`` if it is not one."""
    if not isinstance(payload, dict):
        return None
    if _as_text(payload.get("schema")) != CONTRACT_SCHEMA:
        return None
    owner = _as_text(payload.get("owner_msn_id"))
    consumer = _as_text(payload.get("counterparty_msn_id"))
    if not owner or not consumer:
        return None
    resources: list[str] = []
    for token in payload.get("tracked_resource_ids") or ():
        text = _as_text(token)
        # rc.<owner_msn>.<resource> — the msn segment is dashed, so the resource
        # is whatever follows the owner's msn, not simply the last dot-segment.
        head = f"{_RESOURCE_PREFIX}{owner}."
        if text.startswith(head):
            name = text[len(head) :]
            if name and name not in resources:
                resources.append(name)
    return ReferenceGrant(
        contract_id=_as_text(payload.get("contract_id")),
        owner_msn_id=owner,
        consumer_msn_id=consumer,
        resources=tuple(resources),
        status=_as_text(payload.get("status")),
        counterparty_public_key=_as_text(payload.get("counterparty_public_key")),
    )


def grants_for(grants: Iterable[ReferenceGrant], *, consumer_msn_id: str) -> list[ReferenceGrant]:
    """The grants that let ``consumer_msn_id`` read someone else's resources."""
    return [
        g
        for g in grants
        if g.consumer_msn_id == consumer_msn_id and g.owner_msn_id != consumer_msn_id and not g.is_refused
    ]


def admitting_grant(
    grants: Iterable[ReferenceGrant],
    documents: Iterable[Any],
    *,
    channel_sandbox: str,
    counterparty_msn_id: str,
) -> ReferenceGrant | None:
    """The grant that admits ``counterparty_msn_id`` to a closed channel, or None.

    Three conditions, each already expressed somewhere and composed here rather than
    re-derived: the grant names this counterparty; its contract status is ACTIVE (only
    ACTIVE may carry traffic — the read side's looser "any non-refused status declares
    the relationship" is deliberately NOT reused here, because engaging a channel is
    traffic, not a reference); and the channel's sandbox is among the sandboxes the
    grant's tracked resources resolve to.

    That last condition is why no new document field is needed: a channel's ``sandbox``
    attribute is a sandbox name, and :func:`granted_sandboxes` already answers which
    sandboxes a contract's resources name. A contract that does not name the channel's
    sandbox admits nothing, however active it is.
    """
    from micyte.domains.contracts.channel import state_from_contract_status

    documents = tuple(documents)
    for grant in grants:
        if grant.consumer_msn_id != counterparty_msn_id:
            continue
        if not state_from_contract_status(grant.status).grants_channel:
            continue
        if channel_sandbox and channel_sandbox in granted_sandboxes(documents, grant):
            return grant
    return None


def live_instance_nodes(payloads: Iterable[Any]) -> set[str]:
    """The msn nodes that hold a live install, derived from contract payloads.

    "Has an instance to reach" is a **derived** fact, never a stored flag: a node is a
    live install exactly when a non-refused contract names it. Both parties of such a
    contract are live — a contract is between two running installs — and a refused one
    grants nothing.

    This is the derivation ``publish_micyte_registry`` already applies for the public
    registry feed's ``live`` status; it lives here so a second surface asking the same
    question cannot answer it differently. Note what it is NOT derived from: the
    registry card's ``dns`` cell holds an ordinary website domain (129 of 236 nodes
    carry one), so reading it as an instance address would report a hundredfold more
    installs than exist.

    Pure over already-parsed payloads. The caller does the I/O.
    """
    nodes: set[str] = set()
    for payload in payloads:
        grant = parse_contract(payload)
        if grant is None or grant.is_refused:
            continue
        nodes.add(grant.owner_msn_id)
        nodes.add(grant.consumer_msn_id)
    return nodes


def granted_sandboxes(documents: Iterable[Any], grant: ReferenceGrant) -> frozenset[str]:
    """The owner's sandboxes a resource name refers to.

    A resource is matched against the owner's sandboxes first (``registrar`` names
    the sandbox), then against document names within them (``txa`` names a
    document in the ``taxonomy`` sandbox). Scoped to the owner's msn throughout:
    the consumer has a ``txa`` of its own, and a grant must never be read as
    permission over the consumer's own data.

    A resource that resolves to nothing grants nothing — silently, because a
    contract may name resources this store does not hold.
    """
    owner_sandboxes: set[str] = set()
    docs_by_sandbox: dict[str, set[str]] = {}
    for document in documents:
        try:
            parsed = parse_canonical_document_id(str(getattr(document, "document_id", "") or ""))
        except CanonicalNameError:
            continue
        if parsed.msn_id != grant.owner_msn_id or not parsed.sandbox:
            continue
        owner_sandboxes.add(parsed.sandbox)
        docs_by_sandbox.setdefault(parsed.sandbox, set()).add(parsed.name)

    out: set[str] = set()
    for resource in grant.resources:
        if resource in owner_sandboxes:
            out.add(resource)
            continue
        out |= {sb for sb, names in docs_by_sandbox.items() if resource in names}
    return frozenset(out)


def own_instance_nodes(
    documents: Iterable[Any], *, msn_id: str, exclude_sandbox: str
) -> frozenset[str]:
    """Node addresses ``msn_id``'s OTHER sandboxes define.

    A contract governs reading someone ELSE's documents. Reading your own instance's
    other sandbox is not a cross-instance reference at all and needs no grant — the
    `agnet` channel sandbox and the `taxonomy` sandbox are both FND's, and a product
    row keyed to a taxon node never left the instance.

    Without this, an instance was worse off than its counterparty: the farm could
    resolve FND's `txa` because the live FND->farm contract grants
    `rc.<fnd>.txa`, while FND's own `agnet` sandbox could not resolve it at all and
    every one of its 185 product taxon references read as dangling. That aborted the
    `mutate_txa` cross-sandbox cascade the moment a node address moved — after the
    taxonomy write had already landed.

    This does NOT soften the check: only addresses some document in the instance
    actually DEFINES are returned, so a reference to a node that exists nowhere is
    still dangling, which is the whole point of the check.
    """
    nodes: set[str] = set()
    for document in documents:
        try:
            parsed = parse_canonical_document_id(str(getattr(document, "document_id", "") or ""))
        except CanonicalNameError:
            continue
        if parsed.msn_id != msn_id or not parsed.sandbox or parsed.sandbox == exclude_sandbox:
            continue
        nodes |= defined_node_addrs(document)
    return frozenset(nodes)


def external_nodes_for(
    documents: Iterable[Any], grants: Iterable[ReferenceGrant], *, consumer_msn_id: str
) -> frozenset[str]:
    """Node addresses ``consumer_msn_id`` is declared to be able to reference.

    Empty when nothing is granted — an instance with no contract is self-contained
    and any reference out of it is a real dangling ref, which is the point.
    """
    documents = list(documents)
    nodes: set[str] = set()
    for grant in grants_for(grants, consumer_msn_id=consumer_msn_id):
        sandboxes = granted_sandboxes(documents, grant)
        if not sandboxes:
            continue
        for document in documents:
            try:
                parsed = parse_canonical_document_id(str(getattr(document, "document_id", "") or ""))
            except CanonicalNameError:
                continue
            if parsed.msn_id == grant.owner_msn_id and parsed.sandbox in sandboxes:
                nodes |= defined_node_addrs(document)
    return frozenset(nodes)
