# Reference Exchange Domain

Status: **partial**. Domain semantics only.

- `message.py` — the P2P message: a routing header wrapped around a `.mss`, over a
  small closed set of kinds (establish a contract channel, the replies that settle
  it, and the traffic that follows).

**Still missing, and it is the important half:** resolving a reference against a
*remote* instance. The transport under it works (`instance_client.py` sends;
sealed traffic returns), but the read operation on top of it is undesigned — it
needs batching, partial failure, and a stated rendering for an unreachable peer.

The grant that says a reference *may* be read is `micyte/core/references.py`
(contract-declared `rc.<owner_msn>.<resource>`). "This reference resolves" and
"this reference is allowed" are different questions; inferring the second from the
first makes every accidental collision legal.

The reference form itself — `hy.<msn>.<sandbox>.<document>.<version_hash>.<address>`,
a hyphae's header without its payload — is specified in
`/srv/agentic/knowledge/micyte_network_cooperation_convention_2026_08_04.md` §3.

Design spec: [`90-network-contract-architecture.md`](../../../docs/wiki/90-network-contract-architecture.md)
