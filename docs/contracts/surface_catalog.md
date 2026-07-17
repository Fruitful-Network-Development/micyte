# Surface Catalog

The surface catalog is rooted only in `SYSTEM`, `NETWORK`, and `UTILITIES`.

Cross-tool operating invariants (region families, posture authority, and normalization ownership) are defined in `docs/contracts/tool_operating_contract.md`.

## Shared Datum-File Workbench

Every SYSTEM surface — the `system.root` anthology workspace and every tool surface
listed below emits a reflective workbench payload. The shared renderer is
`datum_file_workbench` (region kind
`mycite.v2.portal.shell.region.workbench.v2`) and materializes the current MiCyte
state through `state_reflection`, `document_collection`, `active_document`, and
optional `layered_datum_table` content.

Tool-specific UI (Diktataograph, Garland, Staged Insert, Domain Gallery, Manifest
tree, Analytics body, PayPal body) lives in the `Interface Panel` only. Tool surfaces
do not replace the workbench with tool chrome.

The portal `msn_id` bounds the portal; sandbox is the parent datum-document
grouping inside that boundary. `system.root` is bound to sandbox `system` only.
Tool surfaces are bound to their named sandbox only. URL route slugs use hyphens
(`cts-gis`, `aws-csm`), while canonical sandbox tokens used in document IDs use
underscores (`cts_gis`, `aws_csm`). Cross-sandbox datum-file navigation is not a
supported shell state.

`Workbench UI` remains a SYSTEM tool route but uses a SQL authority lens in the
standard reflective-workspace family rather than a special posture.

## SYSTEM

First-class surfaces:

- `system.root`
- `system.tools.workbench_ui`
- `system.tools.aws_csm`
- `system.tools.cts_gis`
- `system.tools.fnd_dcm`
- `system.tools.fnd_ebi`

Workspace file modes under `system.root`:

- `anthology` - the canonical system anchor file and default SYSTEM datum-file workbench
- `activity`
- `profile_basics`
- authoritative sandbox/source documents by file key

`activity` and `profile_basics` are not first-class surfaces anymore.

`anthology` is rendered as a layered datum table grouped by `layer` and `value_group`, with datum selection opening a detail lens inside `system.root`.

For migrated portals, authoritative `SYSTEM` datum/workbench/profile/grant posture is SQL-backed while preserving the same file/workbench outward shapes.

`SYSTEM` control-panel behavior is canonicalized as:

- current context rows first
- verb tabs in a compact navigation strip
- file, datum, or object selections below the current focus level

## AWS-CSM

- `system.tools.aws_csm`

`AWS-CSM` is one `SYSTEM` child service tool surface.

- It is not four separate public tools.
- Its canonical route is `/portal/system/tools/aws-csm`.
- Its control-panel context rows are:
  - `Sandbox: AWS-CSM`
  - `File: tool.<msn>.aws-csm.json`
  - `Mediation: spec.json`
- Its default posture is interface-panel-led.
- Its workbench is the shared `datum_file_workbench` over the AWS-CSM sandbox. The default reflected file is the sandbox anchor, rendering the layered datum table for `lv.<msn>.aws-csm.anchor.<hash>`.
- Its canonical query keys are:
  - `view`
  - `domain`
  - `profile`
  - `section`
- Its default Interface Panel is the primary tool surface.
- Its domain gallery lives in the Interface Panel. It is not a workbench renderer.
- A selected domain may project:
  - a user email gallery
  - an onboarding section
  - a newsletter section
- Service-tool posture is determined by required capabilities and available peripheral employment, not by a separate portal type model.
- `AWS-CSM` is operational only when the active portal can employ the authenticated peripheral package. In the live topology that means FND alone can route those external operations.

## Workbench UI

- `system.tools.workbench_ui`

`Workbench UI` is one `SYSTEM` child read-only two-pane SQL authority lens.

- Its canonical route is `/portal/system/tools/workbench-ui`.
- Its default posture uses the shared tool registry value.
- Its workbench is the default-visible spreadsheet-like SQL datum grid and stays visible on first composition through `default_workbench_visible=true`.
- It does not replace the reducer-owned `/portal/system` anthology workspace.
- It inspects authoritative SQL-backed documents only; retained host-bound/private assets and `NETWORK` derived materializations remain outside its corpus unless separately ported.
- Its `Interface Panel` shows selected-row semantic identity plus additive directive overlay summaries.
- Its canonical query keys are:
  - `document`
  - `document_filter`
  - `document_sort`
  - `document_dir`
  - `filter`
  - `sort`
  - `dir`
  - `group`
  - `workbench_lens`
  - `source`
  - `overlay`
  - `row`
- Its document-table columns are:
  - `document_name`
  - `document_id`
  - `source_kind` when source metadata is visible
  - `version_hash` with short identity badges plus full value text
  - `row_count`
- Its interpreted row-grid columns are:
  - `datum_address`
  - `layer`
  - `value_group`
  - `iteration`
  - `labels`
  - `relation`
  - `object_ref`
  - `hyphae_hash` with short identity badges plus full value text
- Its raw row-grid lens swaps interpreted row-summary cells for the canonical raw payload preview while keeping the same structural coordinates and selected-row identity.
- Its document table is keyed by `version_hash`, while its selected-document row grid is keyed by `hyphae_hash`.
- Fresh entry deliberately prefers the first available CTS-GIS authoritative document in the current document ordering and falls back to the first available authoritative document when no CTS-GIS document is present.
- Its document and datum panes both carry sticky-header intent and explicit selected-document / selected-datum-row markers.
- Its datum grid may be grouped as `flat`, `layer`, `layer_value_group`, or `layer_value_group_iteration`, with the last mode materializing a layer/value-group/iteration cell matrix while preserving canonical structural order.
- Its source and overlay visibility remain query-driven.
- Its keyboard navigation stays query-driven through runtime-owned document/row selection actions rather than new canonical navigation keys.
- It is read-only in v1.
- It must never mutate authoritative datum rows.
- Any directive overlay is additive only and may be hidden without changing authoritative row content.

## CTS-GIS

- `system.tools.cts_gis`

`CTS-GIS` is one `SYSTEM` child mediation tool surface.

- Its canonical route is `/portal/system/tools/cts-gis`.
- Its default posture is interface-panel-led.
- Its workbench is the shared `datum_file_workbench` over the CTS-GIS sandbox.
  Default shell focus is `file=anchor`; if no materialized CTS-GIS anchor document
  exists, the workbench reflects the sandbox document collection until anchor row
  material is available.
- Its dominant `presentation_surface` Interface Panel mounts one CTS-GIS-local body on the shared tab host. Diktataograph, Staged Insert, and Garland are Interface Panel content; they are not workbench renderers.
- `tab_host=shared_interface_tabs`.
- `tabs` currently materialize as `diktataograph` and `garland`.
- `default_tab_id=diktataograph`.
- The `Diktataograph` tab hosts:
  - the CTS-GIS structural navigation canvas
  - the staged insert widget
- The `Garland` tab hosts:
  - the correlated geospatial pane
  - the correlated profile pane
- `Diktataograph` is the CTS-GIS structural navigation canvas (`navigation_canvas`).
- `navigation_canvas.mode` defaults to `directory_dropdowns`.
- `navigation_canvas.source_authority` is `samras_magnitude`.
- `navigation_canvas.decode_state` blocks when magnitude decode or node bindings are invalid.
- `navigation_canvas.dropdowns` carries one dropdown per resolved structural depth.
- `navigation_canvas.active_path` carries the resolved lineage.
- `Garland` is the CTS-GIS correlated projection surface. It renders as a list of
  **component frames** (`interface_body.component_frames`), each carrying a typed payload
  and an initializer directive spec. See `docs/contracts/interface_panel_component_frame_contract.md`.
- The primary frame is a `profile` component representing the administrative entity at the
  current attention node; its `subject_slot` contains a `geospatial_projection` component.
- Legacy payload: `garland_split_projection` with `geospatial_projection` and `profile_projection`
  is preserved as a backwards-compatibility fallback and is the source of truth when
  `component_frames` is absent. The frontend normalization path synthesizes empty frames
  when only the legacy payload is present.
- Garland remains visible and stateful once a structural selection exists. Component frames
  are frozen after initial render; a changed `render_key` triggers re-render.
- `profile` frame may show blank field values when no matching profile source is resolved yet.
- `geospatial_projection` frame stays blank until the attention node or its widened intention
  resolves valid HOPS evidence.
- Node-focused widened intention keeps the selected node as the active profile while Garland
  may overlay multiple in-scope projectable source documents.
- Title fallback is blank-only when ASCII title decode is unavailable.
- In narrow posture, the CTS-GIS-local body may fall back to a vertical stack while
  preserving the same contract.
- CTS-GIS mediates on the selected anchor-file datum (`1-1-2`, msn-SAMRAS magnitude) and
  projects correlated source-file evidence into the Interface Panel. This mediation does
  NOT change the AITAS spatial value. See `docs/contracts/portal_panel_state_distinction.md`.
- CTS-GIS tool-local navigation does not widen the shared shell focus stack. The shell focus remains `sandbox -> file -> datum -> object`.
- Tool-local state is body-carried through CTS-GIS `tool_state`, not projected through new query keys.
- CTS-GIS staged insert state is carried in `tool_state.staged_insert`.
- CTS-GIS staged mutation requests run through `POST /portal/api/v2/system/tools/cts-gis/actions`, not through renderer-owned SQL or filesystem writes.
- The canonical staged insert contract is YAML-first with JSON-equivalent support via `mycite.v2.cts_gis.stage_insert.v1`.
- The `Control Panel` holds CTS-GIS-local directive, `AITAS`, source-evidence controls, and staged insert recap/actions.
- The workbench is the shared datum-file workbench over the CTS-GIS sandbox; it is not a duplicate of Garland and not a CTS-GIS-specific surface.
- CTS-GIS mode is explicit via `runtime_mode`:
  - `production_strict` consumes a compiled navigation/evidence baseline, hydrates non-default Garland projection contexts from authoritative CTS-GIS projection documents, and fails fast when compiled state is invalid.
  - `audit_forensic` exposes richer evidence and compatibility diagnostics.
- CTS-GIS runtime also emits compact model partitions for universal shell tooling:
  - `navigation_model`
  - `projection_model`
  - `evidence_model`
- When a selected node is present and no explicit tool-local intention is supplied, CTS-GIS normalizes `Intention` to `self` so Garland reflects the current node.
- Node-focused Intention actions live inside `AITAS`; `Projection Rules` is shown only for sandbox-wide attention without a selected node.
- v2.5.4 phase-B is canonical-only for CTS-GIS identifiers and storage anchors.
- Legacy CTS-GIS `maps` identifiers are rejected at `POST /portal/api/v2/system/tools/cts-gis` with `400 legacy_maps_alias_unsupported`.
- Compiled artifact authority schema is `mycite.v2.portal.system.tools.cts_gis.compiled.v1`.

## FND-DCM

- `system.tools.fnd_dcm`

`FND-DCM` is one `SYSTEM` child service tool surface.

- Its canonical route is `/portal/system/tools/fnd-dcm`.
- Its default posture is interface-panel-led.
- Its workbench is the shared `datum_file_workbench` over the FND-DCM sandbox. The default reflected file is the sandbox anchor, rendering the layered datum table for `lv.<msn>.fnd-dcm.anchor.<hash>`.
- Its canonical query keys are:
  - `site`
  - `view`
  - `page`
  - `collection`
- It normalizes hosted-site manifests into one shared read model with fixed buckets:
  - `site`
  - `navigation`
  - `footer`
  - `pages`
  - `collections`
  - `issues`
  - `extensions`
- The `Control Panel` selects site and high-level view.
- The `Interface Panel` is the primary surface for overview, pages, collections, and issue projections. The hosted-site manifest tree, raw manifest JSON, and collection metadata live in the Interface Panel.
- The workbench is the shared datum-file workbench over the FND-DCM sandbox; it is not a duplicate of the manifest tree.
- `FND-DCM` is read-only in v1.
- It may remain visible while non-operational when `webapps_root` or required capabilities are missing.

## FND-EBI

- `system.tools.fnd_ebi`

`FND-EBI` is one `SYSTEM` child analytics tool surface.

- Its canonical route is `/portal/system/tools/fnd-ebi`.
- Its default posture is interface-panel-led.
- Its workbench is the shared `datum_file_workbench` over the FND-EBI sandbox. The default reflected file is the sandbox anchor, rendering the layered datum table for `lv.<msn>.fnd-ebi.anchor.<hash>`.
- Its analytics body, summary cards, and ad-hoc evidence renderers live in the Interface Panel. They are not workbench renderers.
- Its `Control Panel` projects the unified directive panel, with FND-EBI analytics filters delivered through `tool_extensions.fnd_ebi_analytics_filters`.

## PayPal-CSM

- `system.tools.paypal_csm`

`PayPal-CSM` is one `SYSTEM` child service tool surface.

- Its canonical route is `/portal/system/tools/paypal-csm`.
- Its default posture is interface-panel-led.
- Its workbench is the shared `datum_file_workbench` over the PayPal-CSM sandbox. The default reflected file is the sandbox anchor, rendering the layered datum table for `lv.<msn>.paypal-csm.anchor.<hash>`.
- Its tool body (account summary, transaction listings) lives in the Interface Panel. It is not a workbench renderer.

## NETWORK

- `network.root`

`network.root` is the read-only portal-instance system-log workbench.

- It is not a tool and not a sandbox.
- Its canonical operational document is `data/system/system_log.json`.
- Contract correspondence is a filter/lens over the same system-log workbench.
- Event-type filtering is projected through the same root workbench.
- Selected log rows open a read-only Interface Panel detail view with linked contract detail when applicable.
- The interface panel is collapsed by default until selected-record focus exists.
- `NETWORK` has no canonical Messages/Hosted/Profile/Contracts peer-tab model in V2.

The host shell activity bar remains icon-only across all root and tool entries. Labels belong to hover titles and accessibility metadata, not to persistent bar text.
The top menubar is the only shell header.

## UTILITIES

- `utilities.root`
- `utilities.tool_exposure`
- `utilities.integrations`

`UTILITIES` is section-led rather than focus-depth-led.

- Its control panel projects `Root` and `Section` context rows.
- Its grouped selections live under `Sections`.
- Its interface panel is collapsed by default until a utilities section explicitly projects detail there.
- It does not simulate sandbox/file/datum/object depth when that context does not exist.

## Tool Posture

- Tool work pages stay under `SYSTEM`.
- Tool regions participate only through the canonical shell families:
  - `directive_panel`
  - `reflective_workspace`
  - `presentation_surface`
- Tool registry defaults are interface-panel-led.
- Tool registry posture metadata is descriptive only; shell composition remains authoritative for first-load tool posture.
- Tool workbench visibility is hidden by default (`false`).
- `workbench_ui` defaults to `true` because its primary surface is the SQL-backed datum grid.
- Retired scoped fallback keys are not part of the active surface catalog or tool posture contract.
- Tool surfaces use mutually exclusive single-click behavior between `Workbench` and `Interface Panel` by default.
- Double-clicking either tool toggle enables route-scoped lock mode that allows both panels to remain visible together.
- Tool lock is non-persistent and clears when leaving the current tool route or composition.
- Tool surfaces may still project secondary workbench content explicitly when lock mode is enabled.
- Tool configuration and exposure remain owned by `UTILITIES`.
- Service-tool posture is determined by configured capabilities and available peripherals or integrations, not by portal identity.
