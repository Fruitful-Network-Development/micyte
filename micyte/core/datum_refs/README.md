# Datum Refs

Authority: [../../../../docs/plans/v2-authority_stack.md](../../../../docs/plans/v2-authority_stack.md)

`packages/core/datum_refs/` owns the phase-02 MVP datum-ref surface.

Implemented in this phase:

- pure datum-ref parsing
- pure datum-ref validation
- pure datum-ref normalization into canonical local, dot, or hyphen text

Not implemented in this phase:

- identity logic
- MSS resolution
- HOPS or SAMRAS structures
- runtime path helpers
- port, adapter, tool, sandbox, or state-machine concerns
