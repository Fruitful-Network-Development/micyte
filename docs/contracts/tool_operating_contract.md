# Tool Operating Contract

## Status

Canonical

## Purpose

Define one stable operating contract for all portal tools so extension remains possible without shell-level drift.

This contract preserves HANUS, interface-surface mediation, and NIMM-AITAS by constraining where each concern is allowed to live.

Shell unification is complete for the active portal routes. The three region families below are the only active shell-level families in the contract.

## Fixed Shell Model

The shell is one host layout with four peer regions inside `ide-body`:

- `Activity Bar`
- `Control Panel`
- `Workbench`
- `Interface Panel`

Tools do not create parallel shells.

## Region Families

Shell region dispatch is constrained to three canonical payload families:

- `reflective_workspace`
- `directive_panel`
- `presentation_surface`

These families are shell-level contracts. Tool-specific semantics must be expressed as content inside these families, not as new shell dispatcher branches.
Retired scoped fallback keys are outside this operating contract.

### `reflective_workspace`

The workbench is the reflective plane for backing documents and structural evidence.

Required shape:

- canonical document set metadata
- selected document identity
- selected row/object identity
- structural coordinates for rows/objects
- optional additive overlays as explicit evidence

The workbench must remain read-focused unless a separate mutation contract explicitly allows writes.

### `directive_panel`

The control panel is the state recap plus legal-transition plane.

Required shape:

- current canonical context rows
- available directives for current state
- next legal selections
- dispatchable request payloads for every actionable entry

The control panel does not infer transitions client-side.

### `presentation_surface`

The interface panel is a presentation host for free-form tool-local views built from shared widget contracts.

Required shape:

- layout container intent
- widget descriptors with stable type ids
- canonical widget props and action descriptors
- normalized loading/error/empty wrappers

Tool-local richness is allowed here, but composition rules and wrapper behavior must remain uniform.

## Authority Boundaries

### Shell owns

- route/state synchronization
- region orchestration
- directive dispatch
- first-load region visibility/posture application

### Runtime owns

- canonical state calculation
- canonical query and URL projection
- region payload generation
- tool-local normalization and boundary enforcement

### Widgets own

- presentation only
- local interaction state that does not change canonical shell/runtime state

### Three-Authority Recap

The active mutation-capable architecture separates responsibilities:

- shell authority:
  - route and posture orchestration
  - region-family projection
  - dispatch handoff only
- directive authority:
  - canonical NIMM directive envelopes (`mycite.v2.nimm.envelope.v1`)
  - validated stage/preview/apply intent
- lens authority:
  - stateless display/canonical codecs used at the staging boundary
  - no operation selection or mutation permission logic

The staging boundary remains explicit: UI edits enter stage storage first, stage values compile to NIMM directives, and only runtime `apply` mutates authoritative state.

### AWS-CSM Onboarding Directive Contract

AWS-CSM onboarding actions use the same three-authority posture with a
canonical directive contract:

- envelope schema: `mycite.v2.nimm.envelope.v1`
- `directive.target_authority`: `aws_csm`
- `directive.verb`: `manipulate`
- `directive.payload.action_kind`: one of:
  - `create_profile`
  - `stage_smtp_credentials`
  - `send_handoff_email`
  - `reveal_smtp_password`
  - `refresh_provider_status`
  - `capture_verification`
  - `confirm_verified`
- `directive.payload.action_payload`: action-specific request body
- `aitas` minimum context:
  - `attention` (domain/profile/user focus token)
  - `intention=manipulate`
  - `time` (operation window token)
  - `archetype=aws_csm_onboarding`
  - `scope=portal/system/tools/aws-csm`

This contract keeps action execution in runtime authority while preserving one
query/route shell boundary and one mutation envelope grammar across tools.

`AWS-CTS` is not a current code-level tool slug in this repository. When that
term appears in planning requests for this stream, treat it as an alias that must
be normalized to the existing AWS-CSM surface or explicitly documented before
implementation.

Implementation note: `portal_aws_runtime.py` compiles action requests into
`aws_csm` NIMM manipulation envelopes before runtime execution. Email and secret
display values are projected through lenses; secret-bearing payload keys are
redacted in the envelope and remain runtime-owned.

### Cross-Tool Mutation Unification Follow-On

The active follow-on stream is
`docs/plans/portal_nimm_aitas_unification_plan_2026-04-24.md`.

Implementation work under that stream preserves:

- Control Panel dispatches directives and legal lifecycle actions
- Workbench holds authoritative rows and preview deltas
- Interface Panel hosts editing surfaces and local display state
- lenses encode/decode/validate display values only
- NIMM/AITAS envelopes carry mutation intent and interpretation context
- runtime-owned `apply` is the only authoritative mutation step

#### AWS-CSM Secure Handoff Posture

- `send_handoff_email` must not include reusable SMTP passwords in plain text.
- Operator handoff email may include host/port/username and explicit instructions
  to retrieve secrets only through controlled portal action flows.
- Emergency disclosure response must be documented and executable:
  1) rotate/stage replacement SMTP credentials,
  2) revoke old credentials in IAM/Secrets Manager,
  3) re-run provider handoff verification and capture incident timestamp.
- `reveal_smtp_password` remains the only operator-facing runtime action that can
  return password material, and should be used for bounded manual recovery only.

## Posture and Visibility Invariant

`build_shell_composition_payload()` is the sole authority for region posture and first-response visibility.

Rules:

- tool registry posture metadata is descriptive, not authoritative
- tools default to hidden workbench on first composition unless their registry entry sets `default_workbench_visible=true`
- `workbench_ui` keeps the SQL authority lens visible through that registry flag
- runtime bundles may project secondary workbench evidence but must not override first-load posture authority

## Request and Query Normalization Invariant

All shell request/query normalization must pass through one shared normalizer layer before runtime handling.

Rules:

- no duplicated normalization branches per surface
- reducer-owned surfaces preserve shared focus-stack projection keys
- runtime-owned surfaces preserve canonical query ownership
- CTS-GIS tool-local state stays body-carried; shell query is not widened for tool-local navigation
- anti-query-widening is enforced by runtime normalization, not by renderer convention

## Universal Tool Surface Invariant

Every tool surface must be executable through one universal operating path:

- canonical route under `/portal/system/tools/<tool_slug>`
- canonical shell request through `POST /portal/api/v2/shell`
- optional direct tool endpoint for tool-specific actions
- one runtime envelope with shell state, shell composition, and region payloads
- region payloads confined to `reflective_workspace`, `directive_panel`, and `presentation_surface`

## Extension Rule

To add capability, prefer one of:

- add a widget type in the interface widget registry
- extend reflective workspace document/row schema additively
- extend directive panel action descriptor vocabulary additively

Do not add:

- a new shell region
- a new shell-level renderer kind for one tool
- a second posture authority path

## Unification Closeout

The shell-unification closeout is complete for the active portal routes.

Active contract state:

- shell authority remains locked to route/state synchronization and first-load posture application
- runtime normalization is shared across shell and direct tool entrypoints
- active route dispatch uses only `reflective_workspace`, `directive_panel`, and `presentation_surface`
- wrapper states and direct-query helpers continue to flow through shared adapters and widget contracts
- top-level tool-specific shell dispatcher branches are retired from the active runtime/client paths

No public right-rail compatibility aliases remain in the active shell-region contract.

## Contract Test Matrix

Each canonical route must be covered by shell-boundary matrix tests asserting:

- canonical URL and query projection
- canonical state owner (reducer-owned vs runtime-owned)
- visible regions on first composition
- region payload family for each region
- allowed directive action set

This matrix is the regression guard against drift between shell, runtime, and tool renderers.

## Service Tool Specifics

Service tools (tool_kind = TOOL_KIND_SERVICE) follow the general operating contract above
with additional requirements specific to external service management:

- Interface panel is the primary surface; workbench is hidden by default.
- Surface payload includes `request_contract` sub-object used by JS workspace for
  all route/schema resolution (no hardcoded values in JS).
- Interface panel uses the canonical component_frames model with one component_group
  frame per tab; each tab carries a declarative `initializer` spec (server-side only).
- Peripheral data lives in `{private_dir}/utilities/tools/{tool-slug}/` outside MOS SQL.
- Standard tool state fields: `active_tab`, `engaged_frame_id` (transient, cleared each cycle).
- Standard action kinds: `select_tab`, `engage_component_frame`.

Full specification: `docs/contracts/service_tool_peripheral_package_contract.md`
Reference implementation: FND-CSM (`portal_fnd_csm_runtime.py`)
