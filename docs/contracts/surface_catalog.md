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

Tool-specific UI (the SQL datum grid's lenses, a farm's geospatial projection, and the
extension bodies Utilities mounts) lives in the `Interface Panel` only. Tool surfaces
do not replace the workbench with tool chrome.

The portal `msn_id` bounds the portal; sandbox is the parent datum-document
grouping inside that boundary. `system.root` is bound to sandbox `system` only.
Tool surfaces are bound to their named sandbox only. URL route slugs use hyphens
(`workbench-ui`, `agro-erp`), while canonical sandbox tokens used in document IDs use
underscores (`workbench_ui`, `agro_erp`). Cross-sandbox datum-file navigation is not a
supported shell state.

`Workbench UI` remains a SYSTEM tool route but uses a SQL authority lens in the
standard reflective-workspace family rather than a special posture.

## SYSTEM

First-class surfaces:

- `system.root`
- `system.tools.workbench_ui`
- `system.tools.agro_erp`

That is the whole list. Tool surfaces are enumerated in `TOOL_SURFACE_IDS`; a sandbox
existing does not make it a surface.

## GADGETS and PROFILE (2026-08-21)

Two roots joined the catalog with the five-axes activity bar — the operator's
2026-08-21 depiction supersedes the 2026-06-05 three-root ruling:

- `gadgets.root` (`/portal/gadgets`) — the launcher page apps and instruments moved
  to when they left the rail. Canonical query: `msn_filter` only; every card is an
  address on the Compendium root.
- `profile.root` (`/portal/profile`) — the identity surface at the rail's foot.
  Canonical query: `msn_filter`, `channel` (the in-page channel session), and with a
  channel open, `grantor_tab` / `grantee` (the grantor session's own state).

Workspace file modes under `system.root`:

- `anthology` - the canonical system anchor file and default SYSTEM datum-file workbench
- `activity`
- `profile_basics`
- authoritative sandbox/source documents by file key

`activity` and `profile_basics` are not first-class surfaces anymore.

`anthology` is rendered as a layered datum table grouped by `layer` and `value_group`, with datum selection opening a detail lens inside `system.root`.

For migrated portals, authoritative `SYSTEM` datum/workbench/profile/grant posture is SQL-backed while preserving the same file/workbench outward shapes.

`SYSTEM` had a control-panel projection — context rows first, then verb tabs in a compact
navigation strip, then file/datum/object selections below the current focus level. The
region was retired 2026-08-16 and the builders behind those three were deleted 2026-08-17
(`_system_context_items`, `_verb_tab_entries`, `_file_entries_to_navigation_groups` and
the group builders under them). None of it had a reader by then: the surface's selection
lists are built by the workbench itself.

The verb still exists in `shell_state` and still reaches the client, at
`state_reflection.nimm` — it is the tabs that are gone, not the intention they set.

## Retired surfaces

The three sections that used to sit here — `AWS-CSM`, `CTS-GIS` and `FND-DCM` — described
first-class `SYSTEM` tool surfaces. None of them is in `build_portal_surface_catalog()`
any more, and this document went on describing them long after they were gone.

- **`system.tools.cts_gis`** — excised together with its sandbox (the geospatial data moved
  to `mycelium_network`, then to `registrar`). The route is gone; the only survivors are a
  NIMM mediation `target_authority` default and some naming examples in comments.
- **`system.tools.aws_csm`** — became a peripheral package under `UTILITIES`, not a portal
  surface. Cost, tolling and inbound-mail views are Utilities extensions.
- **`system.tools.fnd_dcm`** — likewise a peripheral package; the manifest surface lives in
  the operator's Resources extension.
- **`system.tools.fnd_ebi`** and **`system.tools.paypal_csm`** were listed here too and were
  never in the catalog either. Analytics and PayPal are dashboard-side concerns.

The general rule this document now follows: a surface is first-class **iff**
`build_portal_surface_catalog()` returns it. Anything else is an extension, a peripheral or a
package, and belongs in `UTILITIES` — see `feedback_portal_features_are_extensions`.

## Workbench UI

- `system.tools.workbench_ui`

`Workbench UI` is one `SYSTEM` child read-only two-pane SQL authority lens.

- Its canonical route is `/portal/system/tools/workbench-ui`.
- Its default posture uses the shared tool registry value.
- Its workbench is the default-visible spreadsheet-like SQL datum grid and stays visible on first composition through `default_workbench_visible=true`.
- It does not replace the reducer-owned `/portal/system` anthology workspace.

### Compendium levels (2026-08-16)

The system root renders this bundle as a file manager. `surface_payload.compendium`
(`mycite.v2.portal.workbench.compendium.v1`) carries the level the request named:

- **Level 0** — `?msn_filter=<msn>` with no `sandbox_filter`: the instance's SANDBOXES as
  folders. Sandboxes are the foremost parent layer; `system` leads, the rest read
  alphabetically.
- **Level 1** — `?sandbox_filter=<sandbox>`: that sandbox's documents, as an icon/title
  gallery or a list (`?view=gallery|list`, toggled top-right of the workbench). Icons are
  keyed by the `archetype` projected into the rows-free document index — never a full
  catalog read on this path.
- **Level 2** — `?document=<id>`: the document's FACE. `?doc_view=scope` is its
  archetype's viewscope, built through `document_view_runtime.build_document_view_payload`;
  `?doc_view=raw` is the datum grid. **Anchor files are raw-only** — the anchor is the
  ground truth every drawn view resolves against, so the Scope toggle is offered as
  unavailable with that sentence on hover rather than hidden.
- A breadcrumb strip (`Compendium › <sandbox> › <document>`) heads the pane; each crumb is
  a query link that clears exactly the keys below it.
- A request naming **neither an msn nor a sandbox** gets no `compendium` key at all,
  whatever else it carries: that is the legacy corpus-reflective view, and the
  Compendium cannot place — or draw a breadcrumb for — a document with no instance.
  `_level_honest_query` has always treated it that way; the level assignment agrees.
- **The payload answers the level too.** Levels 0 and 1 do not carry
  `workspace.datum_grid`, `workspace.document_table` or `surface_payload.sections`;
  level 2 carries the grid only for the raw face. See the shell contract's transfer
  policy for the measurements.
- The **sandbox's own view (level 1)** carries a `compendium.sources` section — imported
  pins (reading from another sandbox) and created-here pins, each with the resolver's
  verdict. It rode the control panel for one day; the panel was retired on 2026-08-16
  and the section renders where the directive always pointed, inside the sandbox. It is
  present for every named sandbox, empty or not: absence means no sandbox is in view,
  emptiness means the sandbox declares nothing, and the two keep two different
  sentences. It draws at most 20 pins per bucket and states the exact totals beside the
  heading ("showing 20 of 473") — a list cut without saying so reads as a complete list.
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
- Fresh entry takes the first available authoritative document in the current ordering. (It used to prefer a CTS-GIS document; that sandbox no longer exists.)
- Its document and datum panes both carry sticky-header intent and explicit selected-document / selected-datum-row markers.
- Its datum grid may be grouped as `flat`, `layer`, `layer_value_group`, or `layer_value_group_iteration`, with the last mode materializing a layer/value-group/iteration cell matrix while preserving canonical structural order.
- Its source and overlay visibility remain query-driven.
- Its keyboard navigation stays query-driven through runtime-owned document/row selection actions rather than new canonical navigation keys.
- It is read-only in v1.
- It must never mutate authoritative datum rows.
- Any directive overlay is additive only and may be hidden without changing authoritative row content.

## NETWORK

- `network.root` carries `surface_payload.selection_strip` (2026-08-16): the view,
  contract and event-type facts the log table stands on, plus the entries it could
  stand on instead. This was the Network control panel; the region is retired and the
  selection now renders beside the rows it filters. Empty groups are dropped — a
  heading with nothing under it states nothing.

- `network.root` — the read-only portal-instance system-log workbench
- `network.browser` — the `msn_id` browser
- `network.p2p` — the inter-instance messaging centre

All three are gated on `host_config.network_enabled`. When an instance turns the network
module off, they are **absent from the catalog entirely** rather than rendered disabled: a
sub-surface that survived the flag would be a side door into a module the instance turned off.

`network.root` (the system log):

- It is not a tool and not a sandbox.
- Its canonical operational document is `data/system/system_log.json`.
- Contract correspondence is a filter/lens over the same system-log workbench.
- Selected log rows open a read-only Interface Panel detail view with linked contract detail
  when applicable.
- The interface panel is collapsed by default until selected-record focus exists.

`network.browser` (the `msn_id` browser):

- Its engine runs in one of two modes — `cached` (read a published still) or `linked` (the
  live registry). The mode is DERIVED on every read from contract state, never stored, and the
  payload carries the reason alongside the mode.
- The authority instance's own registry is local, so it browses `linked` without holding a
  contract with itself.
- Region navigation is driven by the administrative-entity profiles and the gazetteer, not by
  a hardcoded region list.
- Selecting a node yields its `msn_profile`: the contact-card fields plus one section per
  registrar document that carries a row for that `msn_id`.
- Visiting a node's website opens it with **no address bar**. Navigation is `msn_id`-based; a
  URL is a dead end that exits back to the browser.

`network.p2p` presents channel state (contract requests, acceptance, `.mss` conveyance). The
transport is not built: it moves no bytes.

The host shell activity bar remains icon-only across all root and tool entries. Labels belong
to hover titles and accessibility metadata, not to persistent bar text.
The top menubar is the only shell header.

## UTILITIES

- `utilities.root`
- `utilities.tools`
- `utilities.ports`
- `utilities.peripherals`
- `utilities.tool_exposure` / `utilities.extensions` / `utilities.grantee_profile` —
  DISSOLVED ids kept registered for recognition only; requested via the shell API they
  resolve to the Utilities landing, and their HTTP routes are gone (no more 302s).

Plus the **holdings** — what this instance holds, as opposed to Tools/Peripherals, which
report posture. Holdings are platform surfaces: they are NOT gated on
`host_config.network_enabled` (only the NETWORK tabs are — `test_network_enabled_flag`
pins this). `utilities.apps` replaced the `utilities.libraries` / `utilities.view_packages`
/ `utilities.datum_packages` stub shelves in TASK-2026-08-14-002 Phase 1:

- `utilities.apps` — installable tool packages: what ships together, what installing provisions
- `utilities.contracts` — inter-instance grants, including the authority contact
- `utilities.published` — Resource Management, the ONLY publish path

`UTILITIES` is section-led rather than focus-depth-led.

- **Every Utilities surface carries its own `surface_payload.section_nav`** (2026-08-16):
  one entry per section, the active one marked. It was a control-panel group until the
  panel was retired, and a nav in the chrome vanishes with the chrome — standing IN a
  section then left no route to a sibling but back out to the landing page. The list is
  `UTILITIES_SECTIONS` for every surface under the root, whichever builder serves it
  (`test_utilities_surface_invariants.OneRootHasOneNav` pins that the two agree).
- **`utilities.apps` owns its install target.** It is the only Utilities surface whose
  payload varies by sandbox — install readiness is computed against the target — so it
  carries `surface_payload.install_target`: one link per sandbox, each addressing itself
  with `sandbox_filter`, so the readiness reported and the URL reporting it cannot
  disagree.
- It does not simulate sandbox/file/datum/object depth when that context does not exist.
- `utilities.published` is the one holdings surface that is not read-only. Publication is a
  card mutation: `contact_card.public_stills[]` is the allowlist and the only publish path, and
  an unpublished name is refused with 404 rather than 403.

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
