# L3 — Portal Shell, Runtime & UI

> Status: as-built
>
> [← Overview](00-overview-and-glossary.md)

## Purpose

L3 is the **UI layer** of the MiCyte Portal: the shell state machine that defines
*what* a portal page is (scope, chrome, focus, surface, tool registry), the Flask
host + Python runtime that compose a concrete page bundle on every request, and
the front-end JavaScript that POSTs to the runtime, validates the returned
envelope, and renders it into the IDE-style shell.

The vision is a document-processor experience (think Excel): a sandbox's datum
documents load as a standardized WORKBOOK-YAML model that modular
functions/tools/lenses operate on, with edits pipelined back to a MOS save.
This page documents how much of that is built. The short answer (see
[Vision-fit](#vision-fit)): the **write** path compiles edited WORKBOOK-YAML and
applies it to MOS; the **read/render** path projects SQL straight to JSON and
never materializes YAML. The two halves are not yet unified.

The shell package itself is a **pure state machine** — no I/O, no Flask, no
adapters (see `MyCiteV2/packages/state_machine/portal_shell/README.md:16`). The
runtime and host wrap it with side effects.

---

## File map

### Back-end — shell state machine (`MyCiteV2/packages/state_machine/`)

| Path | Role | LOC |
|---|---|---|
| `portal_shell/shell.py` | Canonical home of the shell dataclasses, the surface/tool resolvers, the reducer (`reduce_portal_shell_state`), `canonicalize_portal_shell_state`, `resolve_portal_shell_request`, the canonical-query whitelist, and `build_shell_composition_payload`. | 1787 |
| `portal_shell/shell_state.py` | Near-duplicate dataclass definitions (`PortalScope`, `PortalShellState`, `PortalShellTransition`, `PortalShellRequest`, `PortalSurfaceCatalogEntry`, `PortalShellResolution`) built on `core.scalars.as_text`. See [Open questions](#open-questions) re: duplication. | 490 |
| `portal_shell/shell_schemas.py` | All schema strings, surface IDs, routes, entrypoints, sandbox tokens, focus levels, verbs, transition kinds, and the (now empty) `REDUCER_OWNED_SURFACE_IDS`. | 185 |
| `portal_shell/shell_registry.py` | `build_portal_surface_catalog()` (10 surfaces) + `build_portal_tool_registry_entries()` (2 tools + 6 extensions). Resolves `PortalToolRegistryEntry` lazily to break the import cycle with `shell.py`. | 310 |
| `portal_shell/tool_eligibility.py` | Pure recognizer `recognize_applicable_tools(datum_doc, datum_address, registry)` — intersects a document's archetype/source-kind set (widened by the hyphae chain) against each tool's `applies_to_*`. Extensions never match. | 115 |
| `nimm/mutation_contract.py` | Mutation lifecycle constants: `DEFAULT_MUTATION_ENDPOINTS`/`ACTIONS` (`stage`/`validate`/`preview`/`apply`/`discard`), CTS-GIS + AWS-CSM action aliases, and the abstract `MutationContractRuntimeHandler`. | 125 |
| `nimm/staging.py` | `StagingArea` + `StagedValue`: stage a display value through a `Lens` (encode + validate), then `compile_manipulation_envelope()` into a `manipulate` `NimmDirectiveEnvelope`. | 116 |
| `nimm/envelope.py` | `NimmDirectiveEnvelope` (directive + AITAS context), schema `mycite.v2.nimm.envelope.v1`. | 64 |
| `aitas/` | AITAS context model (`attention`/`intention`/`time`/`archetype`/`scope`) + `merge_aitas_context`, carried inside NIMM envelopes. | — |
| `mediation_surface/` | **Empty stub** — `__init__.py:1` says "Inert package scaffold"; `README.md:3` is a placeholder. No behavior. | — |

### Back-end — runtime (`MyCiteV2/instances/_shared/runtime/`)

| Path | Role | LOC |
|---|---|---|
| `portal_shell_runtime.py` | The composition engine. `run_portal_shell_entry()` normalizes the request → resolves the surface → builds a per-surface bundle (`_bundle_for_surface`) → wraps it in `build_shell_composition_payload` → returns a runtime envelope. Also `run_system_profile_basics_action()`. | 1735 |
| `portal_palette_runtime.py` | Backs `GET /portal/api/tools/eligible` (`build_eligible_tools_response`) and `GET /portal/api/visualizers/for-sandbox` (`build_sandbox_visualizers_response`). Reads from the viz-tool registry `MyCiteV2.packages.tools`. | 243 |
| `runtime_platform.py` | Envelope/region-family contracts, surface schemas, request schemas, `build_portal_runtime_envelope` / `build_portal_runtime_error` / `attach_region_family_contract` / `surface_schema_for_surface`. | 462 |
| `portal_datum_workbench_mutation_runtime.py` | **The WRITE path.** `run_datum_workbench_mutation_action()` dispatches stage/validate/preview/apply over datum operations; `_run_workbook_mutation_action()` (line 480) compiles edited WORKBOOK-YAML → ops → migration plan → atomic MOS apply. | 1189 |
| `utilities_extensions/` | The 6 Utilities extension renderers (Email, Analytics, Newsletter, PayPal, Connect, Grantee Profile) invoked by `_build_utilities_extensions`. | — |
| `portal_workbench_ui_runtime.py` (referenced) | Builds the workbench-UI tool bundle; delegate for `system.root`. Calls into `packages/tools/workbench_ui/service.py` (the READ path). | — |

The actual SQL→JSON projection lives one layer down in the workbench-UI tool:
`MyCiteV2/packages/tools/workbench_ui/service.py` — `read_surface()` (line 586)
and `_compute_surface()` (line 630). **This is the READ path.**

### Back-end — Flask host (`MyCiteV2/instances/_shared/portal_host/`)

| Path | Role | LOC |
|---|---|---|
| `app.py` | `V2PortalHostConfig` (line 579), `create_app()` (line 1601), all routes, the `PORTAL_SHELL_MODULE_CONTRACTS` JS manifest (line 247), and `_render_surface()` (line 754). | 6175 |
| `wsgi.py` | WSGI entrypoint. | — |
| `templates/portal.html` | The shell HTML shell — embeds the bootstrap request + asset manifest, loaded by `_render_surface`. | — |

### Front-end JS (`MyCiteV2/instances/_shared/portal_host/static/`)

| Path | Role | LOC |
|---|---|---|
| `v2_portal_shell.js` | Bundle loader. Reads `PORTAL_SHELL_MODULE_CONTRACTS`, loads modules in order, owns module-registration fatal handling. | 401 |
| `v2_portal_shell_core.js` | The driver. Owns runtime POSTs (`loadShell`/`loadRuntimeView`), envelope validation (`applyEnvelope`), region dispatch (`renderRegions`), chrome (`applyChrome`), history sync, tool-action/transition dispatch, the menubar tool palette mount, and the sandbox selector. | 902 |
| `v2_portal_shell_region_renderers.js` | `PortalShellRegionRenderers` — activity-bar + control-panel renderers. | 952 |
| `v2_portal_workbench_renderers.js` | `PortalShellWorkbenchRenderer.render` — the central workbench renderer (datum grid, document tables, mutation forms). | 3752 |
| `v2_portal_system_workspace.js` | `PortalSystemWorkspaceRenderer` — the only renderer that understands the ordered sandbox→file→datum→object focus path. | 579 |
| `v2_portal_tool_surface_adapter.js` | `PortalToolSurfaceAdapter` — shared request-building + loading/error/empty wrappers for tool surfaces. | 407 |
| `v2_portal_tool_palette.js` | `PortalToolPalette` — fetches `/portal/api/tools/eligible` (or `/visualizers/for-sandbox`) and renders the menubar search/result list. | 208 |
| `v2_portal_shell_watchdog.js` | Boot-stage watchdog (deferred). | — |

---

## How it works

### The shell as a pure state machine

A portal page is fully described by a `PortalShellState` (`shell.py:217`): an
`active_surface_id`, an ordered `focus_path` (sandbox → file → datum → object,
levels indexed in `shell_schemas.py:108`), a `focus_subject`, a
`mediation_subject`, a `verb` (`navigate`/`investigate`/`mediate`/`manipulate`,
`shell_schemas.py:120`), and `chrome` flags. State is **frozen + normalizing**:
every dataclass `__post_init__` coerces and validates, so an invalid state is
unrepresentable.

The reducer `reduce_portal_shell_state` (`shell.py:940`) applies a
`PortalShellTransition` (`focus_sandbox`/`focus_file`/`focus_datum`/
`focus_object`/`back_out`/`set_verb`/`enter_surface`, `shell_schemas.py:131`) to
a canonicalized prior state and re-canonicalizes the result.
`canonicalize_portal_shell_state` (`shell.py:874`) clamps the focus path to the
surface's sandbox, seeds the anchor file, and derives verb/chrome from the
surface kind (tool surfaces force `mediate` + interface panel open).

**The reducer is effectively dead, by design.** Phase A (the "function-forward"
refactor) made every surface query-native: `REDUCER_OWNED_SURFACE_IDS` is now an
empty frozenset (`shell_schemas.py:185`), so `requires_shell_state_machine()`
always returns `False`. `resolve_portal_shell_request` (`shell.py:1400`) sets
`reducer_owned = False` unconditionally and passes any incoming `shell_state`
through as a passive value object (`shell.py:1439`). Selection now travels as
**`surface_query`** (the workbench query vocabulary) rather than reducer
transitions. The dataclasses and reducer remain in the tree but are no longer the
live control path for navigation.

### Surface catalog & tool registry

`build_portal_surface_catalog()` (`shell_registry.py:49`) returns 10 surfaces
across 3 roots — SYSTEM (`system.root` + `system.tools.workbench_ui` +
`system.tools.agro_erp`), NETWORK (`network.root`), and UTILITIES
(root + extensions + grantee-profile + tools + peripherals + a legacy
tool-exposure entry). `build_portal_tool_registry_entries()`
(`shell_registry.py:141`) returns 2 palette tools (`agro_erp`, `workbench_ui`)
plus 6 `is_extension=True` Utilities extensions. Each `PortalToolRegistryEntry`
(`shell.py:476`) declares `applies_to_archetype`/`applies_to_source_kind` used by
the palette and a reserved-but-unenforced `manipulates_datum_kinds`
(`shell.py:493`).

### Runtime entrypoints

`run_portal_shell_entry` (`portal_shell_runtime.py:1491`) is the main entrypoint:

1. `_normalize_request` (`:130`) resolves the `PortalScope` from the MOS SQL
   portal-authority snapshot (capabilities), stamping it onto the request.
2. `resolve_portal_shell_request` resolves the requested surface (unknown →
   `system.root` fallback, `allowed=False`).
3. `_bundle_for_surface` (`:1268`) builds a per-surface region bundle:
   - `system.root` **delegates to the unified workbench** (`build_portal_workbench_ui_bundle`) and rewrites the WORKBENCH-UI identifiers back to system-root identity (`:1297`–`:1342`).
   - tool surfaces (`workbench_ui`, `agro_erp`) dispatch through `_TOOL_SURFACE_BUNDLE_BUILDERS` (`:1205`).
   - `network.root` / `utilities.*` build their own control-panel + workbench regions, each wrapped by `attach_region_family_contract`.
4. `build_shell_composition_payload` (`shell.py:1553`) assembles the activity bar,
   control panel, workbench, the retired-but-present interface panel, and the
   visualization panel into a `shell_composition`.
5. `build_portal_runtime_envelope` returns the envelope (schema
   `mycite.v2.portal.runtime.envelope.v1`).

`run_system_profile_basics_action` (`:1586`) is a dedicated write action for the
SYSTEM profile-basics form (applies through `PublicationProfileBasicsService`,
appends an audit record, invalidates the projection cache).

### Flask routes (`app.py`)

| Route | Handler | Purpose |
|---|---|---|
| `GET /portal/system` | `_render_surface(SYSTEM_ROOT_SURFACE_ID)` (`:1625`) | Serve the shell HTML for the system surface. |
| `GET /portal/system/tools/<slug>` | `:1629` | Legacy tool slugs (`workbench-ui`/`agro-erp`/`cts-gis`) **302-redirect** to `/portal/system?<canonical query>`. |
| `GET /portal/network`, `/portal/utilities`, `/portal/utilities/{extensions,grantee-profile,tools,peripherals}` | `:1666`–`:1691` | Serve the shell for each surface. |
| `GET /portal/utilities/{tool-exposure,integrations}` | `:1693`,`:1701` | 302-redirect to the new surfaces. |
| `GET /portal/api/tools/eligible` | `:1707` | Palette eligibility for a selected datum. |
| `GET /portal/api/visualizers/for-sandbox` | `:1732` | Sandbox-wide visualizer discovery for the menubar search. |
| `POST /portal/api/v2/shell` | `:1822` → `run_portal_shell_entry` | **The shell runtime endpoint** the front end POSTs to. |
| `POST /portal/api/v2/system/workspace/profile-basics` | `:1847` | Profile-basics write. |
| `POST /portal/api/v2/mutations/<action>` | `:1872` → `run_datum_workbench_mutation_action` | **The mutation lifecycle endpoint** (stage/validate/preview/apply/discard) — the WRITE path. CTS-GIS spatial editing is retired; only `datum_workbench`/`datum_document` targets are accepted. |
| `POST /portal/api/v2/system/tools/workbench-ui` | `:1896` | Workbench-UI tool runtime POST. |

Every page is served by `_render_surface` (`:754`), which embeds a bootstrap
shell request + the JS asset manifest into `portal.html`. `_runtime_response`
(`:709`) validates the envelope schema and maps error codes to HTTP status
(`:659`).

### Front-end → API wiring

`v2_portal_shell.js` loads the modules declared in `PORTAL_SHELL_MODULE_CONTRACTS`
(`app.py:247`) in order, then `v2_portal_shell_core.js` takes over:

1. On boot it reads the embedded bootstrap request and `loadShell()`
   (`shell_core.js:524`) POSTs it to `/portal/api/v2/shell`.
2. `applyEnvelope` (`:487`) validates the envelope schema, then `applyChrome`
   (`:259`) sets shell layout attributes and `renderRegions` (`:357`) resolves
   each region's registered renderer module and dispatches:
   `renderActivityBar` + `renderControlPanel` (region renderers), `render`
   (workbench renderer), and `renderVisualizationPanel` (`:395`).
3. Navigation is **direct** — activity items and control-panel entries carry an
   `href` (or a `shell_request` payload to POST), not reducer transitions
   (`portal_shell_runtime.py:284`,`:318`). `dispatchTransition` (`:611`) early-
   returns unless `envelope.reducer_owned`, which is now always false — so it is
   effectively inert, matching the dead reducer.
4. The **sandbox selector** (`:814`) and the **menubar tool palette**
   (`mountMenubarToolPalette`, `:851`) both mutate `surface_query` on the current
   request and re-`loadShell()`. The palette appends picked tool-ids to
   `surface_query.tools`; the runtime turns each into a visualization-panel box.

`v2_portal_tool_palette.js` is the palette implementation: it GETs
`/portal/api/tools/eligible` (datum-scoped) or `/portal/api/visualizers/for-sandbox`
(sandbox-scoped) and renders a filterable result list whose clicks call back
into `shell_core`'s `onDispatch`.

### How a sandbox is selected, loaded, and rendered

1. The user picks a sandbox in the menubar selector → `shell_core.js:835` sets
   `surface_query.sandbox_filter`, clears `document`/`row`/`mode`, and re-loads.
2. `canonical_query_for_surface_query` (`shell.py:1121`) whitelists the workbench
   query keys (`document`, `mode`, `sandbox_filter`, `tools`, sorting, grouping,
   lens, …). For `system.root`/`workbench_ui` it also infers `sandbox_filter`
   from a canonical `lv.<msn>.<sandbox>.<name>.<hash>` document id (`:1199`).
3. `system.root` delegates to `build_portal_workbench_ui_bundle`, which calls the
   workbench-UI tool's `read_surface` (`service.py:586`).

### READ vs WRITE materialization (the central L3 story)

The vision is "load a sandbox's datum docs as runtime WORKBOOK-YAML → modular
functions/lenses → pipeline edits to a MOS save." This is **half-built**: the
two halves of the loop use different representations.

**WRITE path — uses WORKBOOK-YAML.** A workbook edit posts to
`POST /portal/api/v2/mutations/apply` with `operation=apply_workbook` and an
`edited_workbook_yaml` string. `_run_workbook_mutation_action`
(`portal_datum_workbench_mutation_runtime.py:480`) does:

```
baseline = load_workbook(store, tenant_id, sandbox)           # SQL → Workbook
edited   = workbook_codec.from_yaml(edited_yaml)              # YAML → Workbook   (:511)
ops      = compile_workbook(baseline, edited)                # diff → op sequence (:515)
plan     = plan_migration(baseline, ops)                     # rule-checked plan  (:516)
result   = execute_migration(authority_db_file, plan, ...)   # backup→write→verify(:533)
```

The WORKBOOK-YAML codec is transport-only and explicitly non-persisted
(`packages/core/datum_io/codec.py:1`, `packages/core/datum_ops/workbook.py:1`);
MOS SQL remains canonical.

**READ/render path — bypasses YAML entirely.** The workbench surface is built by
`read_surface` → `_compute_surface` (`service.py:586`,`:630`), which reads the
authoritative catalog from `SqliteSystemDatumStoreAdapter` and projects it
**directly into a JSON surface_payload** (document tables, row items, lens-
resolved cells). It imports from `adapters.sql` and `datum_semantics` — there is
**no `workbook`/`yaml` import in `service.py`**. So a sandbox is never
materialized as runtime WORKBOOK-YAML on the way to the screen; the UI renders
the SQL projection.

Net: edits *can* round-trip through WORKBOOK-YAML to MOS, but the live grid the
user reads/edits against is a direct SQL→JSON projection, not the YAML model the
vision describes. Unifying these (read also via WORKBOOK-YAML) is the open work
specced in `70-yaml-materialization-pipeline.md` *(forward reference)*.

### NIMM mutation lifecycle (the contract layer)

`packages/state_machine/nimm/` defines the *contract* for staged mutations
without performing them. `StagingArea.stage_with_lens` (`staging.py:60`) encodes
+ validates a display value through a `Lens`; `compile_manipulation_envelope`
(`staging.py:90`) emits a `manipulate` `NimmDirectiveEnvelope` carrying the
staged canonical values + AITAS context. `mutation_contract.py` fixes the
endpoint map (`/portal/api/v2/mutations/{stage,validate,preview,apply,discard}`)
and the abstract `MutationContractRuntimeHandler`. The live datum-workbench
mutation runtime implements this lifecycle directly over the datum store rather
than through a registered `MutationContractRuntimeHandler` subclass.

---

## Vision-fit

**Implemented**
- A single pure shell state machine with frozen, self-normalizing dataclasses; an unrepresentable-invalid-state design.
- One surface catalog + one tool registry; archetype/source-kind tool eligibility (`tool_eligibility.py`) and a palette endpoint + menubar UI.
- Flask host composing per-request envelopes; front-end that validates the envelope and dispatches region renderers; deterministic JS module loading with contract checks.
- The WRITE half of the vision loop: edited WORKBOOK-YAML → compile → plan → atomic MOS apply, with MOS as canonical authority.
- The standardized WORKBOOK-YAML transport convention exists and is documented as transport-only.

**Partial**
- "Document-processor" UX: the workbench renders a datum grid with lenses, but reads via a direct SQL→JSON projection, not the WORKBOOK-YAML runtime model the vision calls for. Read and write use different representations.
- Mutation lifecycle: the NIMM contract (stage/validate/preview/apply/discard, lens-staged envelopes) is fully specified, but the live runtime implements it directly rather than via a `MutationContractRuntimeHandler` subclass; `StagingArea` is not the path the workbench grid uses.
- Tool→datum applicability: `PortalToolRegistryEntry.manipulates_datum_kinds` is declared but not consumed by the eligibility predicate (`shell.py:493`).

**Absent**
- A unified materialization pipeline where the read path also loads a sandbox as runtime WORKBOOK-YAML — see `70-yaml-materialization-pipeline.md` *(forward ref)*.
- The shell reducer / focus-path navigation: retired by Phase A. `REDUCER_OWNED_SURFACE_IDS` is empty, so transitions and `dispatchTransition` are inert. Navigation is query-native.
- `mediation_surface/` — an empty package scaffold with no behavior.

---

## Open questions

1. **Dataclass duplication.** `shell.py:74`–`:589` and `shell_state.py:73`–`:491`
   both define `PortalScope`/`PortalShellState`/`PortalShellTransition`/
   `PortalShellRequest`/`PortalSurfaceCatalogEntry`/`PortalShellResolution`.
   `shell_registry.py:42` imports `PortalSurfaceCatalogEntry` from `shell_state`
   while `shell.py` defines its own. A Phase-12a comment (`shell_state.py:472`)
   says `PortalToolRegistryEntry` was de-duplicated to `shell.py` only — but the
   other dataclasses were not. Which module is canonical for each, and is the
   `shell.py` copy slated to import from `shell_state.py`?
2. **Dead-reducer cleanup.** The reducer, transitions, and `dispatchTransition`
   are inert (`REDUCER_OWNED_SURFACE_IDS` empty). Phase-A comments say the active
   state machine "is deleted in A3" (`shell_schemas.py:179`) — has A3 landed, or
   is this still scheduled removal?
3. **READ-path unification.** Will the read/render path migrate onto the
   WORKBOOK-YAML model (so the grid renders the same representation it writes), or
   will WORKBOOK-YAML stay write-only with the SQL projection as the canonical
   read view? This is the crux of `70-yaml-materialization-pipeline.md`.
4. **NIMM staging vs. live mutation runtime.** Is the `MutationContractRuntimeHandler`
   seam intended to become the single mutation path (with the datum-workbench
   runtime registered behind it), or is the contract layer now reference-only?
