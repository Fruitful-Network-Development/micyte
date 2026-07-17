# State Machine

Authority: [../../../docs/contracts/portal_shell_contract.md](../../../docs/contracts/portal_shell_contract.md)

`packages/state_machine/` owns portal-shell legality, AITAS vocabulary, NIMM directives, and the SYSTEM/tool surface state model.

The retained shell model is summarized in [../../../docs/contracts/portal_shell_contract.md](../../../docs/contracts/portal_shell_contract.md).

Implemented for the MVP so far:

- minimal `aitas` attention and intention contracts
- minimal `nimm` directive normalization
- canonical portal shell request, selection, surface catalog, and tool registry contracts
- additive tool-local runtime layers such as CTS-GIS `tool_state`, which may carry richer NIMM/AITAS labels without widening the shared shell validator

Deferred in this phase:

- `mediation_surface` behavior
- tool attachment logic
- sandbox orchestration logic
- host or runtime composition logic
