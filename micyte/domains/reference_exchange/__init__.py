"""Reference-exchange domain semantics — what crosses between two instances.

* :mod:`micyte.domains.reference_exchange.message` — the P2P message: a routing
  header wrapped around a ``.mss``, over a small closed set of kinds.

Partial. The message form exists; **resolving a reference against a remote
instance does not** — that operation needs batching, partial failure, and a stated
rendering for an unreachable peer. See ``docs/wiki/90-network-contract-architecture.md``
§Proposed and the cooperation convention's §9.

Domain semantics only: the transport is FND-side runtime (``instance_client``),
and the grant that says a reference may be read is ``micyte.core.references``.
"""
