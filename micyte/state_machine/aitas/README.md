# AITAS

Authority: [../../../../docs/plans/v2-authority_stack.md](../../../../docs/plans/v2-authority_stack.md)

`packages/state_machine/aitas/` owns the AITAS context model used by NIMM envelopes.

Canonical fields:

- `attention`
- `intention`
- `time`
- `archetype`
- `scope`

Utilities:

- `merge_aitas_context(defaults, overrides)` for deterministic default+override merges

CTS-GIS now adds an additive tool-local AITAS layer in runtime payloads only:

- `attention_node_id`
- `intention_rule_id`
- `time_directive`
- `archetype_family_id`

CTS-GIS may carry richer tool-local AITAS semantics, but the shared model remains a normalization envelope and does not perform mutation itself.
