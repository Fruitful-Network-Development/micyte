# Portal Shell Contract

> **MOS-authority rule:** Datum-document materialization and naming
> follow the single binding contract at
> [`mos_authority_enforcement.md`](mos_authority_enforcement.md). The
> shell never reads datum content from the filesystem.

The repository owns one neutral portal shell contract.

Canonical public entry: `/portal` -> `/portal/system`

## Behavioral Model

- One request schema: `mycite.v2.portal.shell.request.v1`
- One shell state schema: `mycite.v2.portal.shell.state.v1`
- One shell composition schema: `mycite.v2.portal.shell.composition.v1`
- One runtime envelope schema: `mycite.v2.portal.runtime.envelope.v1`
- One entrypoint descriptor schema: `mycite.v2.portal.runtime_entrypoint_descriptor.v1`

The shell state is reducer-owned only for:

- `system.root`
- reducer-owned `SYSTEM` child tool surfaces such as `system.tools.cts_gis` and `system.tools.fnd_ebi`

Shell requests may optionally carry a normalized `nimm_envelope` payload to project directive intent metadata through runtime without granting shell mutation authority.

`AWS-CSM` is a `SYSTEM` child tool surface, but it is runtime-owned and query-driven rather than reducer-owned.

`FND-DCM` is also a runtime-owned `SYSTEM` child tool surface. Its canonical query is manifest-driven rather than reducer-driven.

`Workbench UI` is also a runtime-owned `SYSTEM` child tool surface. Its canonical query is SQL-read driven rather than reducer-driven.

`/portal/network` and `/portal/utilities*` stay in the same host shell, but they do not participate in focus-path reduction.

Non-reducer roots may still project canonical query state when the host needs a stable read-only detail lens inside the workbench. `NETWORK` uses raw `surface_query` projection keys for this purpose, while runtime remains the source of truth.

For migrated portals, authoritative `SYSTEM` datum/workbench/profile/grant posture is resolved from the MOS authority database. Missing or uninitialized SQL authority is a readiness failure rather than a silent filesystem bootstrap.

## Shell Stabilization Invariants

The shell remains a narrow host with fixed orchestration duties.

Authoritative invariants:

- shell-level region dispatch is constrained to three canonical families:
  - `reflective_workspace`
  - `directive_panel`
  - `presentation_surface`
- tool-specific semantics are payload content inside those families, not new shell dispatcher kinds
- composition building in `build_shell_composition_payload()` is the sole first-load authority for region visibility/posture
- request/query normalization is centralized; drift-prone per-surface normalization branches are non-canonical
- CTS-GIS tool-local navigation and AITAS/NIMM state stay body-carried and must not widen shared shell query

The detailed cross-tool operating contract and unification closeout record are documented in `docs/contracts/tool_operating_contract.md`.

## Ordered Focus Stack

The canonical shell state carries an ordered focus stack, not a bag of optional ids.

Order:

1. `sandbox`
2. `file`
3. `datum`
4. `object`

The contract-level anchor-file invariant is:

- a fresh reducer-owned `SYSTEM` entry seeds `sandbox=system&file=anthology`
- a fresh reducer-owned tool entry seeds `sandbox=<tool-sandbox>&file=anchor`
- if a sandbox anchor file exists on disk, it must materialize as an authoritative
  sandbox document before the workbench is considered complete

`portal_scope.scope_id` / portal `msn_id` is the portal boundary, not a datum
document grouping. The first focus segment is always the active sandbox. A runtime
must not use `fnd` (or any portal id) as the datum-document sandbox segment.

`back_out` is exact and deterministic:

- `object -> datum`
- `datum -> file`
- `file -> sandbox`
- `sandbox -> no-op`

Query state mirrors runtime-owned state. Runtime computes canonical next state and canonical next route/query. The URL is a projection of canonical state, not the source of truth.

## Workbench State Reflection

The `Workbench` (the center region of `ide-body`) is **purely reflective**. It materializes
the current MiCyte state — sandbox, file, datum, object — driven by the AITAS Space value.
Navigation in, out, or shifting left/right within a level updates the AITAS Space value,
which the workbench reflects through a structured payload. There are no discrete display
modes; the content shape is always the same, and renderers decide what to show based on
which focus-stack fields are populated.

The shared renderer is `datum_file_workbench`, region kind
`mycite.v2.portal.shell.region.workbench.v2`.

### state_reflection schema

```
state_reflection:
  schema: "mycite.v2.portal.workbench.state_reflection.v1"
  current_sandbox: str   # active sandbox id
  current_file: str      # active file document_id, empty if at sandbox level
  current_datum: str     # active datum address, empty if at file level
  current_object: str    # active object id, empty if at datum level
  aitas:
    attention: str       # the id of the currently attended element
    intention: str       # "observe" | "navigate" | "investigate"
    time: str            # "current"
    archetype: str       # "datum_file_workbench" or surface-specific lens id
  nimm:
    directive: str       # current directive name ("observe_state" | "investigate_datum" | …)
    actions: list        # [{action_id, directive, script_hint}] — NIMM-backed control actions
```

`intention` shifts automatically:
- `"observe"` when at sandbox level (no file focused)
- `"navigate"` when a file is focused but no datum
- `"investigate"` when a specific datum is focused → Interface Panel activates datum focus widget

### Rendering rules (no modes)

| State | Workbench shows | Interface Panel shows |
|---|---|---|
| `current_file` empty | `document_collection.documents` card list | default widget/sections |
| `current_file` set, `current_datum` empty | `layered_datum_table` | default widget/sections |
| `current_datum` set (`intention=investigate`) | `layered_datum_table` (datum highlighted) | datum focus widget with NIMM actions |

### NIMM directive backing

Controls must not encode action semantics in the renderer. Every workbench button reads
its action from `state_reflection.nimm.actions`. Each action entry carries:
- `action_id` — semantic identifier (e.g. `"back_out"`, `"open_datum_panel"`)
- `directive` — the NIMM directive string (e.g. `"nav;self:out"`)
- `script_hint` — a preloaded script expression (e.g. `"daemon(\"nav;self:out\")"`)

The frontend binds `[data-nimm-action-id]` elements to `dispatchTransition({ kind: "nimm_directive", directive, action_id })`.

### Authoritative invariants

- Tool surfaces (CTS-GIS, AWS-CSM, FND-EBI, FND-DCM, PayPal-CSM) emit
  `region.kind = datum_file_workbench`. Tool-specific UI (Diktataograph, Garland,
  Staged Insert, Domain Gallery, Manifest tree, Analytics body, PayPal body) lives in
  the `Interface Panel` only. The workbench is never replaced by tool chrome.
- `Workbench UI` is routable at `system.tools.workbench_ui`. Its SQL grid is a
  reflective SQL authority lens — purely reflective, not a primary two-pane inspector.
  It uses `state_reflection` like every other surface.
- On tool surfaces, the Interface Panel and Workbench toggles are mutually exclusive
  by default: opening one closes the other. On non-tool (system) surfaces, both can
  be open simultaneously (for widgets and sections beside the datum table).
- `inspector` is a retired term. The canonical region key is `interface_panel`.
  CSS class `ide-interfacePanel`. Region schema `mycite.v2.portal.shell.region.interface_panel.v1`.
- Activity-bar tool clicks dispatch the `focus_sandbox` transition; the URL is a
  projection of canonical state, not the source of truth.

## SYSTEM Workspace

`SYSTEM` is the core datum-file workbench for the system sandbox.

- It is not a generic dashboard or home page.
- It cannot navigate or edit datum documents owned by tool sandboxes.
- Its default active file is the system sandbox anchor file, `anthology.json`.
- For migrated portals, `SYSTEM` anthology/profile/grant posture resolves from the MOS authority database while preserving the same file/workbench outward contract.
- The anchor file is rendered as a layered datum table grouped by `layer` and `value_group`.
- Datum rows carry structural coordinates: `layer`, `value_group`, and `iteration`.
- Selecting a datum opens a read-only detail lens inside the same workbench.
- `activity` and `profile_basics` are workspace file modes under `/portal/system`, not first-class pages.
- The control panel projects current context first, then the selectable options below the current focus.
- Canonical context rows are file-backed and may include:
  - sandbox
  - file
  - datum
  - object
  - mediation subject
- Canonical lower-focus selections may include:
  - files when the user is at sandbox level
  - datums when the user is at file level
  - datum aspects or objects when the user is at datum level
- Verb switching remains a compact tab row inside the same control panel.
- The interface panel displays **mediation output**: it reflects results from NIMM mediate
  directives against the current AITAS state. It does not own navigation state and does not
  change the AITAS spatial value. Components on the interface panel are frozen after initial
  render and re-engaged by explicit user action. See `docs/contracts/portal_panel_state_distinction.md`
  and `docs/contracts/interface_panel_component_frame_contract.md`.
- On `system.root`, `verb=mediate` opens the interface panel and binds it to the current mediation subject.

## NETWORK Workspace

`NETWORK` is the portal-instance system-log workbench.

- It is not a tool and not a sandbox.
- It is read-only and non-reducer-owned.
- Its canonical operational document is `data/system/system_log.json`.
- Contract correspondence is a filter over the same canonical system-log document, not a peer tab or child surface.
- The control panel projects:
  - one base view: `system_logs`
  - contract filters
  - event-type filters
- The workbench projects a chronological log table sorted by canonical HOPS timestamps.
- The Interface Panel projects the selected log record and any linked contract summary.
- The interface panel stays collapsed until selected-record focus exists.
- Canonical query keys for the root are:
  - `view`
  - `contract`
  - `type`
  - `record`
- `NETWORK` has no canonical Messages/Hosted/Profile/Contracts tab set in V2.

## UTILITIES Workspace

`UTILITIES` is the section-led configuration surface for shared portal controls.

- It is section-led rather than focus-depth-led.
- It is not a fake sandbox/file/datum/object stack.
- Its control panel uses the same modular selection-panel shell shape as the other roots.
- Its canonical context rows are `Root: UTILITIES` and `Section: <active section>`.
- Its selectable material is grouped under `Sections`.
- Its interface panel stays collapsed until a utilities surface explicitly projects detail there.

## Shell Chrome

- The top-level shell is `ide-shell`.
- `ide-shell` is divided into `ide-menubar` and `ide-body`.
- The top menubar is the only shell header.
- There is no second workbench pagehead.
- `ide-body` is the peer-region window for shell chrome.
- The peer shell regions inside `ide-body` are the `Activity Bar`, `Control Panel`, `Workbench`, and `Interface Panel`.
- Only the `Control Panel` and `Interface Panel` have explicit splitters and persisted width state.
- The activity bar is icon-only.
- The left rail is the `Control Panel`.
- The center region is the `Workbench`.
- The right rail is the `Interface Panel`.
- The only persistent theme selector lives in the menubar.
- Surface labels are exposed through hover titles and accessibility labels, not persistent bar text.
- Menubar shell layout controls are an icon-toggle trio in one row: `Control Panel`, `Workbench`, `Interface Panel`.
- The control panel is the canonical textual navigation surface for current context and lower-focus selections.
- Shell static assets are versioned by `portal_build_id` through one embedded shell asset manifest.

## Active Shell Topology

- `/portal` is only a public redirect and must resolve to `/portal/system`.
- `/portal/api/v2/shell` is the sole shell-composition runtime endpoint.
- `portal.html` embeds one shell asset manifest and loads one public shell boot
  chain.
- `v2_portal_shell.js` is the sole shell bootstrap loader.
- `v2_portal_shell_core.js` is the sole client module that may fetch the shell
  endpoint or own `loadShell()` / `loadRuntimeView()`.
- `portal.js` is a chrome/layout helper only. It may own theme, splitter, and
  shell-layout persistence, but it must not become a parallel shell bootstrap or
  shell-network dispatcher.
- `portal.css` is the shared shell chrome stylesheet and not a distinct shell
  pathway.
- Historical split-shell artifacts and non-canonical public shell routes remain
  retired; reintroducing them violates the one-shell contract.

### Shell Composition Keys

- `shell_composition.workbench_collapsed` reports whether the workbench is currently hidden.
- `shell_composition.regions.control_panel` and `regions.workbench` remain governed by the canonical `directive_panel` and `reflective_workspace` family contracts. The interface_panel region was removed (tools render in the menubar-search → full-screen overlay).
- Retired scoped fallback keys are outside the active shell composition contract and must not reappear in runtime emission or client dispatch.
- Composition building, not upstream region defaults, owns the final root-vs-tool visibility posture for `Workbench`.
- On the first V2 shell hydration, server composition wins over any stored workbench-open preference; stored layout state only resumes after hydration and user interaction.
- Client chrome publishes route-scoped tool lock state through `data-tool-panel-lock` on `ide-shell`.

## Tool Contract

- Tool work pages are `SYSTEM` child surfaces.
- `AWS-CSM` is the canonical AWS service tool surface under `SYSTEM`.
- `CTS-GIS` is the canonical structural/spatial mediation tool surface under `SYSTEM`.
- `FND-DCM` is the canonical hosted-manifest control surface under `SYSTEM`.
- `Workbench UI` is the canonical read-only two-pane SQL authority lens under `SYSTEM`.
- `AWS-CSM` has one public route: `/portal/system/tools/aws-csm`.
- `CTS-GIS` has one public route: `/portal/system/tools/cts-gis`.
- `FND-DCM` has one public route: `/portal/system/tools/fnd-dcm`.
- `Workbench UI` has one public route: `/portal/system/tools/workbench-ui`.
- `AWS-CSM` uses runtime-owned query keys: `view`, `domain`, `profile`, `section`.
- `FND-DCM` uses runtime-owned query keys: `site`, `view`, `page`, `collection`.
- `Workbench UI` uses runtime-owned query keys: `document`, `document_filter`, `document_sort`, `document_dir`, `filter`, `sort`, `dir`, `group`, `workbench_lens`, `source`, `overlay`, `row`.
- `CTS-GIS` does not widen shell query. Its tool-local navigation and projection state is body-carried in the tool request/runtime payload.
- `CTS-GIS` runtime mode is explicit and body-carried (`runtime_mode`):
  - `production_strict` (compiled navigation/evidence baseline, fail-fast on invalid compiled state)
  - `audit_forensic` (expanded diagnostics and source forensics)
- `CTS-GIS` production runtime emits compact hot-path models:
  - `navigation_model`
  - `projection_model`
  - `evidence_model` (lazy by default)
- `AWS-CSM` control-panel context is file-backed and projects:
  - `Sandbox: AWS-CSM`
  - `File: tool.<msn>.aws-csm.json`
  - `Mediation: spec.json`
- `FND-DCM` control-panel context is selection-backed and projects:
  - `Sandbox: FND-DCM`
  - `Site: <selected site>`
  - `View: <selected view>`
- `Workbench UI` control-panel context is SQL selection-backed and projects:
  - `Document: <selected document>`
  - `Version: <selected version_hash short identity>`
  - `Selected Row: <active datum address>`
  - `Row Identity: <selected hyphae_hash short identity>`
  - `Grouping: <active grouping mode>`
  - `Lens: <active workbench lens>`
  - `Source: <active source visibility>`
  - `Overlay: <active overlay visibility>`
- `CTS-GIS` control-panel context is file-backed and projects:
  - `Sandbox: CTS-GIS`
  - `File: tool.<msn>.cts-gis.json`
  - `Mediation: spec.json`
- Tool configuration, enabling, exposure, integration state, vault, peripherals, and control surfaces belong under `UTILITIES`.
- Tool registry posture fields serialize the shared tool default (`interface_panel_primary`) as compatibility metadata.
- `Workbench UI` uses the shared registry posture and keeps the SQL-backed workbench lens visible by default through composition authority.
- `Workbench UI` does not replace the reducer-owned `SYSTEM` anthology workspace at `/portal/system`.
- `Workbench UI` inspects authoritative SQL-backed documents only; retained host-bound/private assets and `NETWORK` derived materializations remain outside its corpus unless separately ported.
- Tool compositions default to `regions.workbench.visible=false` unless the registry declares `default_workbench_visible=true`.
- Tool composition building always normalizes tool surfaces to `regions.interface_panel.visible=true` on the first server response, while `Workbench UI` also keeps the workbench visible on first composition.
- Secondary-evidence workbench content is explicit opt-in per tool runtime.
- Tool runtimes may project workbench content, but they do not open the workbench on first composition.
- `FND-DCM` workbench evidence is raw manifest JSON, collection metadata, and normalization evidence rather than a second primary workspace.
- `Workbench UI` workbench evidence is the first-class two-pane spreadsheet-like SQL view: a document table keyed by `version_hash` plus a selected-document row grid keyed by `hyphae_hash`, with additive overlay inspection in the `Interface Panel`.
- `Workbench UI` projects explicit selected-document and selected-row markers, sticky-header intent for both panes, short semantic-identity badges, and query-driven grouping/lens/source controls.
- `Workbench UI` keyboard navigation and next/previous actions always resolve to canonical `document` and `row` query changes rather than introducing new navigation-specific query keys.
- fresh `Workbench UI` selection may intentionally prefer a CTS-GIS authoritative document when one is available; that changes only the tool-local inspection default, not the reducer-owned `SYSTEM` anthology default
- Tool surfaces use mutually exclusive single-click behavior between `Workbench` and `Interface Panel` by default.
- Tool surfaces may lock co-visible behavior by double-clicking either `Workbench` or `Interface Panel` toggle.
- Tool lock is route-scoped and non-persistent; leaving the tool route or switching composition clears the lock.
- In tool lock mode, both the `Workbench` and the `Interface Panel` may stay visible when secondary evidence is explicitly shown.
- Shared tool rendering now normalizes direct-query request building plus wrapper states for `loading`, `error`, `empty`, and `unsupported` through one shell-side adapter before specialized or generic renderers run.
- A service tool may remain visible while `operational=false` when an external integration or required capability is missing.
- Service-tool posture comes from peripheral and integration availability, not from portal identity or portal "types".
- `Workbench UI` is read-only, surfaces additive directive summaries only, and must never mutate authoritative datum rows through overlay state.
- Shared directive snapshots/events may only be imported from explicit normalized manifests; runtime must not infer shared overlays from historical tool-local files.
- All tools attach to the same interface surface. Service-tool behavior is distinguished by whether the tool can employ the portal's authenticated peripheral package, not by a separate class of portal.
- All tool region payloads must conform to the three canonical shell region families declared in this contract.

Default tool posture is interface-panel-led; `Workbench UI` is a standard tool with a default-visible SQL authority lens in the workbench.

### CTS-GIS Tool-Local State

- `CTS-GIS` remains reducer-owned only at the shell level. The shared shell focus stack stays:
  - `sandbox`
  - `file`
  - `datum`
  - `object`
- CTS-GIS-local structural navigation does not add a new shell depth below `object`.
- The canonical CTS-GIS request body may carry `tool_state`:
  - `tool_state.active_path`
  - `tool_state.selected_node_id`
  - `tool_state.nimm_directive`
  - `tool_state.aitas.attention_node_id`
  - `tool_state.aitas.intention_rule_id`
  - `tool_state.aitas.time_directive`
  - `tool_state.aitas.archetype_family_id`
  - `tool_state.source.attention_document_id`
  - `tool_state.selection.selected_row_address`
  - `tool_state.selection.selected_feature_id`
- Legacy request-body field aliases remain confined to request-normalization compatibility and do not widen shell-region contracts:
  - `mediation_state.attention_node_id`
  - `mediation_state.intention_token`
  - top-level `selected_row_address`
  - top-level `selected_feature_id`
- Alias retirement timing and migration gates are tracked in `docs/contracts/cts_gis_legacy_alias_retirement_timeline.md`.

### CTS-GIS NIMM/AITAS Crosswalk

- Shared shell AITAS stays minimal and unchanged.
- CTS-GIS adds a richer tool-local AITAS layer without widening the shared shell validator.
- CTS-GIS keeps node-focused `Attention`, `Intention`, `Time`, and `Archetype` inside the tool-local `AITAS` control-panel group.
- CTS-GIS uses a separate `Projection Rules` group only when no node-focused selection is active and Garland is still at sandbox-wide attention.
- CTS-GIS tool-local labels are:
  - `Attention` = current tool-local navigation root
  - `Intention` = current tool-local projection rule
  - `Time` = tool-local temporal directive
  - `Archetype` = tool-local structure-family directive
- CTS-GIS uses `nimm_directive` as a tool-local directive label inside the request/runtime payload. This is additive tool runtime state, not a widened shared shell directive contract.

### CTS-GIS Interface Body

- The dominant `presentation_surface` region mounts one CTS-GIS-local interface body.
- The CTS-GIS interface body stays on the shared Interface Panel host and does not create extra shell regions.
- `tab_host` is `shared_interface_tabs`.
- `tabs` currently materialize as:
  - `diktataograph`
  - `garland`
- `default_tab_id` is `diktataograph`.
- The CTS-GIS interface body is magnitude-first and role-shaped.
- The shared tab host renders:
  - `Diktataograph` tab
  - `Garland` tab
- The `Diktataograph` tab hosts:
  - `navigation_canvas`
  - the staged insert widget
- The `Garland` tab hosts:
  - `Garland` geospatial pane (`geospatial_projection`)
  - `Garland` profile pane (`profile_projection`)
- `Diktataograph` is emitted through `navigation_canvas`.
- `navigation_canvas.mode` is explicit and defaults to `directory_dropdowns`.
- `navigation_canvas.source_authority` is `samras_magnitude`.
- `navigation_canvas.decode_state` is fail-closed only when no valid structure can be recovered, and may be:
  - `ready`
  - `blocked_invalid_magnitude`
- `navigation_canvas.dropdowns` carries the directory payload:
  - `depth`
  - `parent_node_id`
  - `selected_node_id`
  - `options`
- every dropdown option carries:
  - `node_id`
  - `title`
  - `display_label`
  - `selected`
  - `shell_request`
- CTS-GIS options may additionally carry semantic `action` descriptors (`select_node`, `set_intention`, `set_time`, `select_feature`, `toggle_overlay`) so universal shell adapters can dispatch stable intent without per-entry request envelope expansion.
- `navigation_canvas.active_path` carries the currently resolved structural lineage.
- Root display labels render `1 NEG` through `8 SWG`.
- Deeper display labels render `<node_id> <ascii_title>`, and title output is blank when ASCII decoding fails.
- duplicate node rows and out-of-range overlay rows remain diagnostics but do not block bare node-id navigation when the structure itself is valid.
- `Garland` materializes as `garland_split_projection` with:
  - dominant `geospatial_projection`
  - secondary `profile_projection`
- Garland remains stateful for the selected SAMRAS node once structural navigation resolves.
- `profile_projection` may materialize a blank current-profile state from the selected node id plus ASCII title overlays even when no matching profile source is available yet.
- `geospatial_projection` populates when the focused SAMRAS node or its widened intention scope resolves one or more matching profile sources with projectable HOPS geometry.
- node-focused widened intention keeps `profile_projection` anchored to the selected node while `geospatial_projection` may overlay multiple in-scope projectable source documents.
- explicit source-document selection may still pin row/detail evidence, and changing Intention preserves that pin unless the user explicitly switches source documents.
- when a request supplies `selected_node_id` or tool-local `Attention` without an explicit `Intention`, CTS-GIS normalizes `tool_state.aitas.intention_rule_id` to `self` so Garland reflects the current selected node rather than a descendant render set.
- when node-focused intention is explicit, CTS-GIS returns the canonical token as one of `self`, `<attention_node_id>-0`, `<attention_node_id>-0-0`, or `branch:<node_id>`.
- Historical `layout` / `narrow_layout` fields remain compatibility metadata for CTS-GIS-local panel composition, but the canonical outer host is the shared tab frame.
- In narrow posture, the same regions may stack vertically within their active tab while preserving the same contract.

### CTS-GIS Evidence Precedence

- Tool governance file: `private/utilities/tools/cts-gis/spec.json`
- Tool anchor file: `data/sandbox/cts-gis/tool.<msn>.cts-gis.json`
- Structural authority: `data/payloads/cache/<corpus>.msn-administrative.json`
- Tool-anchor fallback: `tool.<msn>.cts-gis.json` only when the same `msn-SAMRAS` datum is available there
- Label evidence: `data/sandbox/cts-gis/sources/<corpus>.msn-administrative.json`
- Spatial evidence: GeoJSON lens or equivalent cache derived from payload/payload-cache material
- v2.5.4 phase-B is canonical-only:
  - tool id: `cts_gis`
  - route/storage slug: `cts-gis`
  - document ids: `sandbox:cts_gis:*`
  - tool anchor pattern: `tool.<msn>.cts-gis.json`
- Requests that provide legacy CTS-GIS `maps` identifiers are rejected at `POST /portal/api/v2/system/tools/cts-gis` with:
  - HTTP `400`
  - `error.code=legacy_maps_alias_unsupported`
- Compiled artifact authority for strict mode is `mycite.v2.portal.system.tools.cts_gis.compiled.v1` at `data/payloads/compiled/cts_gis.<scope_id>.compiled.json`.


## Runtime Latency Guardrail

`POST /portal/api/v2/shell` must avoid recomputing full datum-recognition
workbench projections for unchanged authority state on every request.

Canonical runtime guardrail:

- system workbench projection may be cached in-process when keyed by:
  - portal instance id
  - authority DB path
  - authority DB `mtime`
- cache must be invalidated when authority state mutates (write paths) or when
  authority DB `mtime` changes
- host startup may prewarm this projection so the first interactive shell load
  does not pay full datum-recognition cost

Evidence anchor: `benchmarks/results/portal_shell_latency_hotfix_2026-04-25.json`.
