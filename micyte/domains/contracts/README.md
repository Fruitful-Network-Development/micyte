# Contracts Domain

Status: **built** (2026-08-02). Domain semantics only.

- `channel.py` — `ChannelState`, the contract lifecycle. Only `ACTIVE`
  `grants_channel`, which is also the admission predicate a closed hosted channel
  gates on. The shared word is convergence, not collision: "may this channel carry
  traffic?" was always this question.

No crypto, no transport, no storage here. Key material is behind
`micyte/core/crypto`; persistence, handshake and negotiation are FND-side runtime
(`contract_store.py`, `contract_handshake.py`, `contract_negotiation.py`,
`contract_sequence_store.py`).

The **Manager/Subordinate** model this package was originally reserved for was
never built and is **superseded** (2026-08-04): a member binds *references* to
datums it already holds, and the counterparty resolves them — returning a filled
document would create a second copy that drifts on the next edit.

Not to be confused with the `contract_*` fields on the local audit read-model
(`modules/cross_domain/network_root`), which are audit-log correspondence rows.

Design spec: [`90-network-contract-architecture.md`](../../../docs/wiki/90-network-contract-architecture.md)
