"""Contract domain semantics — what a relationship between two instances IS.

* :mod:`micyte.domains.contracts.channel` — ``ChannelState``, the contract
  lifecycle. Only ``ACTIVE`` ``grants_channel``, which is also the admission
  predicate a closed hosted channel gates on.

Domain semantics only: no crypto, no transport, no storage. Key material lives
behind :mod:`micyte.core.crypto`; persistence and negotiation are FND-side runtime
(``contract_store`` / ``contract_negotiation`` / ``contract_handshake``).

Not to be confused with the ``contract_*`` fields on the local audit read-model
(``modules/cross_domain/network_root``), which are audit-log correspondence rows.
Same word, unrelated thing — recorded in ``docs/wiki/90`` so nobody unifies them.

This line read "Inert package scaffold." after ``channel.py`` was built; see
``docs/wiki/99-roadmap.md`` Track 3 for how that misled a census.
"""
