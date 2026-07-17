# NIMM

Authority: [../../../../docs/plans/v2-authority_stack.md](../../../../docs/plans/v2-authority_stack.md)

`packages/state_machine/nimm/` owns the directive schema and mutation contract foundation.

Implemented:

- versioned directive schema: `mycite.v2.nimm.directive.v1`
- canonical verbs: `navigate`, `investigate`, `mediate`, `manipulate`
- minimal-token aliases: `nav`, `inv`, `med`, `man`
- target-address structure for file/datum/object addressing
- envelope schema: `mycite.v2.nimm.envelope.v1` (directive + AITAS context)
- staging compiler (`StagingArea`) that produces manipulation directives
- mutation contract endpoint/action constants, compatibility aliases, and runtime handler interface
- verb handler surface with explicit deferred stubs:
  - `handle_nimm_investigate`
  - `handle_nimm_mediate`
  - `handle_nimm_manipulate`

Deferred:

- tool-specific runtime semantics for non-navigation verbs
- full multi-tool mutation orchestration handlers beyond the current CTS-GIS
  and AWS-CSM adapters

CTS-GIS and AWS-CSM compile mutation-capable action requests into
`NimmDirectiveEnvelope` payloads with AITAS context before runtime mutation.
CTS-GIS compatibility action names (`stage_insert_yaml`, `validate_stage`,
`preview_apply`, `apply_stage`, `discard_stage`) map to canonical lifecycle
actions (`stage`, `validate`, `preview`, `apply`, `discard`).
