# Mutation Contract

## Status

Canonical

## Purpose

Define the shared mutation lifecycle contract so editable tool surfaces can stage, validate, preview, apply, and discard directive-driven changes without bypassing runtime authority.

## Canonical Lifecycle Actions

- `stage`
- `validate`
- `preview`
- `apply`
- `discard`

These actions are defined in `micyte/state_machine/nimm/mutation_contract.py` and mapped to canonical endpoint shapes.

## Canonical Endpoint Shapes

- `POST /portal/api/v2/mutations/stage`
- `POST /portal/api/v2/mutations/validate`
- `POST /portal/api/v2/mutations/preview`
- `POST /portal/api/v2/mutations/apply`
- `POST /portal/api/v2/mutations/discard`

Tool-specific actions may continue to use existing routes during compatibility windows, but they should map semantically to these lifecycle actions.

The portal host exposes the shared route family at
`/portal/api/v2/mutations/<action>`. Requests are delegated by
`target_authority` or `nimm_envelope.directive.target_authority` to the
runtime-owned CTS-GIS or AWS-CSM adapters. Tool-specific action routes remain
compatibility entrypoints and must not define independent lifecycle semantics.

## Compatibility Adapter Map

Active tool routes may retain historical action names while they migrate to the
shared lifecycle. Those names must be treated as adapters, not independent
mutation contracts.

| Tool surface | Compatibility action | Canonical lifecycle action |
| --- | --- | --- |
| CTS-GIS | `stage_insert_yaml` | `stage` |
| CTS-GIS | `validate_stage` | `validate` |
| CTS-GIS | `preview_apply` | `preview` |
| CTS-GIS | `apply_stage` | `apply` |
| CTS-GIS | `discard_stage` | `discard` |
| AWS-CSM / AWS-CTS alias | onboarding `action_kind` payloads | compile to `stage`/`validate`/`preview`/`apply` as NIMM manipulation envelopes |

Compatibility routes must still preserve the read/mutation split: read surfaces
can project state and previews, but only runtime-owned `apply` may mutate
authoritative state.

`AWS-CTS` is a planning/request alias for the repository's AWS-CSM surface. Code
uses `aws_csm` as the `target_authority`; host adapters accept the alias only at
the compatibility boundary.

## Canonical Payload Units

- `NimmDirective` schema: `mycite.v2.nimm.directive.v1`
- `NimmDirectiveEnvelope` schema: `mycite.v2.nimm.envelope.v1`
- `AitasContext` envelope fields:
  - `attention`
  - `intention`
  - `time`
  - `archetype`
  - `scope`

Example directive envelope:

```yaml
schema: mycite.v2.nimm.envelope.v1
directive:
  schema: mycite.v2.nimm.directive.v1
  verb: manipulate
  target_authority: cts_gis
  document_id: sandbox:cts_gis:sc.example.json
  aitas_ref: default
  targets:
    - file_key: sandbox:cts_gis:sc.example.json
      datum_address: 1-2-3-4-5-1
  payload:
    staged_values:
      - target:
          file_key: sandbox:cts_gis:sc.example.json
          datum_address: 1-2-3-4-5-1
        lens_id: trimmed_string
        canonical_value: MAIN STREET
        validation_issues: []
aitas:
  attention: ""
  intention: manipulate
  time: ""
  archetype: samras_nominal
  scope: sandbox
```

## Runtime Handler Boundary

Runtime implementations must expose one handler seam with explicit lifecycle methods:

- `stage(envelope)`
- `validate(envelope)`
- `preview(envelope)`
- `apply(envelope)`
- `discard(envelope)`

This seam is represented by `MutationContractRuntimeHandler` and keeps mutation orchestration in runtime, not in shell renderer code.

## Staging Boundary

`StagingArea` compiles staged values into a canonical manipulation directive envelope:

- stage values are lens-normalized display edits
- compiled directive verb is `manipulate`
- apply remains the only authoritative state mutation step

UI components may capture edits and dispatch action requests, but they must not perform authoritative writes directly.

Lens definition reference:

- lenses are stateless codecs with:
  - `decode(canonical_value)`
  - `encode(display_value)`
  - `validate_display(display_value)`
- staging always stores canonical values from lens `encode(...)`, not raw UI text.

## Compound Directive Projection

For operations that require both structure-space and datum-space intent, runtime may emit an additive compound directive projection:

- `schema`: `mycite.v2.nimm.compound.v1`
- `steps[0]`: structure-space mutation intent
- `steps[1]`: datum mutation directive

This projection is reflective metadata for preview/apply planning and does not bypass the apply-phase runtime authority boundary.
