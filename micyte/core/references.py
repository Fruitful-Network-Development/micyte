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
# status (including "pending", where the live FND->Trapp contract sits) declares
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
    )


def grants_for(grants: Iterable[ReferenceGrant], *, consumer_msn_id: str) -> list[ReferenceGrant]:
    """The grants that let ``consumer_msn_id`` read someone else's resources."""
    return [
        g
        for g in grants
        if g.consumer_msn_id == consumer_msn_id and g.owner_msn_id != consumer_msn_id and not g.is_refused
    ]


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
