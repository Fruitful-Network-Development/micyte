# Portal Shell Contract

> **MOS-authority rule:** Datum-document materialization and naming
> follow the single binding contract at
> [`mos_authority_enforcement.md`](mos_authority_enforcement.md). The
> shell never reads datum content from the filesystem.

The repository owns one neutral portal shell contract.

Canonical public entry: `/portal` -> `/portal/compendium`

> **Naming (2026-08-16):** the system root's public route and label are
> **Compendium**. `/portal/system` remains as a query-preserving 302 so old
> bookmarks keep working; internal surface ids stay `system.*`. The rename exists
> because the page and the `system` SANDBOX are different things and shared a
> name.

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
- Context and lower-focus selection were projected into the control panel — context rows
  (sandbox, file, datum, object, mediation subject) above, the selectable level below,
  and verb switching as a compact tab row. The region was retired 2026-08-16 and those
  builders deleted 2026-08-17. **The Compendium states the same thing as a place rather
  than a panel**: the breadcrumb `Compendium › <sandbox> › <document>` names the context,
  and the level below is the shelf, the gallery, or the document's own face. The verb
  survives in `shell_state` and reaches the client at `state_reflection.nimm`; only the
  tab row is gone.
- Mediation output was the interface panel's job, frozen after initial render and
  re-engaged by explicit action. That region went earlier, with the tool overlay. The
  component-frame lifecycle it defined is still live and still dispatched through
  `__MYCITE_V2_CONTAINER_RENDERERS` — see
  `docs/contracts/interface_panel_component_frame_contract.md`, which is retained for that
  model alone. `verb=mediate` no longer opens a region; the datum cell editor's
  MEDIATION tab is an inline pane beside the grid.

## NETWORK Workspace

`NETWORK` is the portal-instance system-log workbench.

- It is not a tool and not a sandbox.
- It is read-only and non-reducer-owned.
- Its canonical operational document is `data/system/system_log.json`.
- Contract correspondence is a filter over the same canonical system-log document, not a peer tab or child surface.
- The base view (`system_logs`), the contract filters and the event-type filters were a
  control-panel group. They are now `surface_payload.selection_strip`, rendered above the
  log table by the surface that owns them — the filters travel with the thing they filter.
- The workbench projects a chronological log table sorted by canonical HOPS timestamps.
- The selected log record and any linked contract summary were the interface panel's, and
  render in the workbench alongside the table now. There is no collapsed-until-focus
  region: with no record selected the surface simply shows none.
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
- Its `Sections` group was a control-panel selection list; it is now
  `surface_payload.section_nav`, stamped on every Utilities surface — one entry per
  section, the active one marked. A page's own navigation belongs to the page.
- `Root: UTILITIES` and `Section: <active section>` were context rows. The surface states
  its section in its own heading, so the rows were repetition and are not reproduced.
- Detail that a utilities surface projects renders in the workbench with the surface,
  not into a separate region.

## Shell Chrome

- The top-level shell is `ide-shell`.
- `ide-shell` is divided into `ide-menubar` and `ide-body`.
- The top menubar is the only shell header.
- There is no second workbench pagehead.
- `ide-body` is the peer-region window for shell chrome.
- **`ide-body` is two columns (2026-08-16): the `Activity Bar` and the `Workbench`.**
  The `Interface Panel` went with the tool overlay; the `Control Panel` followed. There
  is no splitter, no persisted width state, and no region toggle in the menubar — a
  shell with one content region has no boundary to drag.
- The activity bar is icon-only **on a desk**. It is the rail you navigate WITH; the
  workbench is what answers.
- **On a phone the rail is a drawer, and a named one (2026-08-17).** Below 700px
  `ide-body` is ONE column, the rail is off-canvas, and a menu button
  (`[data-shell-rail-toggle]`, first in the menubar) slides it over the workbench.
  Every rail item carries a `.ide-activitylabel`; CSS draws it in the drawer and hides
  it in the column. One DOM, two readings — a rail rebuilt per breakpoint is a rail
  that can disagree with itself. The drawer closes on Escape, on a tap outside, and on
  navigating, and focus returns to the button that opened it.
- **The rail can never be taller than its box.** `.ide-railBody` (the nav plus, on a
  phone, the relocated menubar chrome) is the only scroller; the logo above and the
  instance switcher below are pinned. This is not a phone rule — it was written
  because a phone in LANDSCAPE is a desk width, and there the switcher fell below the
  fold.
- The only persistent theme selector lives in the menubar **on a desk**; on a phone it
  and the tool search move into the drawer, as the shell's chrome rather than the
  page's. The nodes are MOVED, never rebuilt, so their bindings travel with them.
- Surface labels are exposed through hover titles and accessibility labels, not persistent bar text.
- **A channel is on the rail of the instance that HOSTS it (2026-08-17).** The gate is
  the sandbox the channel declares, checked against the sandboxes the active instance
  holds — never a list of msns. Gating only on the portal-wide `tool_exposure` policy
  put AGNET on all four instances' rails when one hosts it. Fails OPEN on an unreadable
  store, like every other rail gate.
- **A surface owns its own navigation.** What a page needs in order to move within
  itself rides that page's `surface_payload`, never a shell region: `section_nav`
  (Utilities' sections, the Network tabs), `selection_strip` (Network's contract and
  event-type filters), `install_target` (the marketplace's install sandbox), and
  `compendium.sources` (a sandbox's imported and created pins). A nav in the chrome
  vanishes the moment the chrome does; a nav on the page cannot.
- **...and OWNING it means drawing it (2026-08-17).** A surface whose payload carries
  `section_nav` and whose renderer never calls `renderSectionNav` has a nav in name
  only. Every Network surface renders through a module of its own rather than through
  `renderGenericSurface`, and not one of them drew it — so the rail's own Network
  destination had no route to any sibling. `renderSectionNav` is exported from the
  shared workbench renderer for the same reason `renderSelectionStrip` is: one
  implementation, several callers.

### The Network module is a map (2026-08-17)

Operator directive: orient the Network page like Apple Maps on a phone or Google Maps
in a browser — *"the difference mainly being that the polygons built from the FND
resource offered up are the bases for giving the map view its sense of context"*.

- **`network.root` IS the map.** Edge to edge, filling the workbench. The system-log
  workspace that owned this route became a contract's history in the inbox.
- **The ground is a datum document, not a tile service.** The boundaries come from the
  registrar's published register, carried to an instance by a live contract. Add an msn
  to the registry and the map redraws. Nothing here may imitate cartography the register
  does not contain.
- **Three controls float over it and nothing else** — profile, inbox, gear. Each is an
  ADDRESS (`/portal/network/profile`, `/portal/network/inbox`,
  `/portal/network/browser`), not a dispatch, and the same three ride every page in the
  module so the module has one chrome rather than a chrome per page. On a page they are
  a row in flow; only over the map do they float.
- **Search lives in a bottom sheet** with peek / half / full detents, and searches
  everything the map DRAWS — the pins and the boundaries. Searching only the pins
  returned nothing on the authority instance, whose map is 518 boundaries and 0 profiles.
- **The Browser tab is retired as a TAB.** Its surface, route and payload are the gear's
  destination, relabelled "Network settings"; old bookmarks still resolve. `network.p2p`
  likewise survives for bookmarks and is reachable by no control.
- **The inbox is contracts, not messages.** One item per contract — a contract REQUEST
  is a contract in an early state, not a second kind of thing — and the detail pane
  shows the contract's lifecycle. **There is no per-contract message log in this build,
  and the page says so** rather than implying a conversation nobody has had.
- **A full-bleed surface asks for its frame.** `data-fullbleed` on `#v2-workbench-body`,
  set by the renderer that wants it and cleared for every other surface; `.viewport`
  drops its padding through `:has()`. The height chain from `.ide-workbench` down is
  otherwise indefinite, and a percentage height resolves against nothing.
- **The instance switcher opens where the rail IS.** In a column it flies out beside
  the button; in the phone drawer it opens inside, above the button, at the drawer's
  width. `position: fixed` cannot be trusted there — the drawer is `transform`ed, and
  a transformed ancestor becomes the containing block for a fixed descendant, so
  viewport coordinates land inside the drawer instead. The shell declares which mode
  the rail is in (`data-rail-mode` on `.ide-shell`) and the renderer reads it; it must
  never re-derive the breakpoint.
- Shell static assets are versioned by `portal_build_id` through one embedded shell asset manifest.

#### The map takes the browser's gestures (2026-08-18)

Operator directive: the map is navigated the way a maps app is navigated — two fingers
zoom it, sliding moves it — and the slide-up panel is where ordinary website mechanics
apply. The failure the directive names is the governing constraint: *a map that zooms
the PAGE leaves a full-bleed surface with nothing to scroll, and the reader is stuck.*

- **`touch-action: none` on the map, and only where the map IS the page.** It is added
  by `attachMapPanZoom` itself under `opts.touch`, so the declaration and the handlers
  that must exist once the browser is out arrive together. The same map embedded in a
  scrolling document does NOT opt in: taking the browser's gestures there would trap a
  reader inside a figure.
- **Three refusals on top of the declaration**, because browsers disagree about it:
  iOS's own `gesturestart`/`gesturechange`/`gestureend`, a multi-touch `touchmove`, and
  the `ctrl+wheel` that a trackpad pinch arrives as. All non-passive.
- **North is fixed.** Rotation and tilt are refused, not unimplemented — the directive
  asks for no change of cardinality, and refusing the gesture is what guarantees it.
  Every finger that is not part of a pinch is a pan, so there is no ambiguity to
  resolve.
- **The clamp asks the SVG what it SHOWS**, via the root CTM, rather than assuming the
  visible window is the whole viewBox. That assumption holds only for an exact `meet`
  fit; under the shell's `slice` it permitted no panning at the opening zoom at all.
  Content narrower than the window is centred, not pinned. Zooming out stops where the
  whole ground fits, and never above 1, so an embedded `meet` map keeps its old floor.
- **A marker never draws larger than at the opening zoom.** Constant screen size in both
  directions is right for a map that only zooms in; this one zooms out to the whole
  extent, where full-size markers over a smaller ground merge into a clump.
- **Click suppression after a gesture is a DEADLINE, not a flag.** A pinch produces no
  click, and a flag set for a click that never arrives is still set when the next real
  one comes.
- **One scroller per surface.** In the sheet, the sheet scrolls and nothing inside it
  does. A list with its own scrollbar inside the panel eats the drag and leaves the
  panel where it was.
- **The panel is drawn in front of the map's chrome**, and the map's zoom stack rides
  the top of the sheet. Covered is not vanished: both come back as the sheet comes down.
- **There is a way back out of a zoomed page.** Prevention covers what starts on the
  map; it cannot cover an OS accessibility zoom or a gesture that began on the menubar.
  The shell watches `visualViewport` and, when the page is genuinely scaled, hands the
  browser's gestures back to the map (`data-page-zoomed`) and shows one control that
  returns the scale to 1. The document's own viewport meta never disables page zoom —
  taking it away from everyone who needs it is a worse trap than the one being escaped.


#### The shell is the visible viewport (2026-08-18)

Operator: *"the bottom of the screen still appears too low and makes it very difficult to
access things like the search overlay on the network page, or even the instance switcher
in the side bar."*

- **No rule may give `.ide-shell` a `min-height` in `vh`.** A min-height clamps a height,
  so a `vh` floor under a `dvh` height wins every time — and `vh` on a phone browser is
  the LARGE viewport, the window with its chrome retracted. Two such floors were declared
  900 lines apart, and the `dvh` height added on 2026-08-16 never applied. Everything
  anchored to the shell's bottom went below the fold with it.
- **The sizing does not live in a `max-width` query.** A phone in landscape is 844px wide
  and enters no phone query; `dvh` and `vh` are the same number on a desk, so declaring
  `dvh` at every width costs the desktop nothing.
- **A control on the bottom edge keeps a gutter under it.** The band a phone draws its own
  toolbar and home indicator in is not a place to put a 44px target, and the one control
  in it is the instance switcher.
- **A soft keyboard is not a shorter viewport.** `dvh` does not see one — the visual
  viewport does. The loss is published as `--kb-inset` on `.ide-shell` and the two
  surfaces that sit on the bottom edge (the network sheet, the rail drawer) subtract it. A
  scale above 1.05 is a zoomed page, not a keyboard, and the inset stands down for it.

*Harness limit, recorded so the evidence is read correctly: headless Chromium resolves
`vh`, `lvh`, `dvh` and `svh` to one number, so the condition itself cannot be produced by
viewport emulation. The mechanism is proven by a control page where the large viewport is
forced larger than the window; the geometry is measured at two window heights; the
keyboard response is driven through the real `visualViewport` listener.*

#### A record table's filters are part of the canonical URL (2026-08-18)

`micyte.tools._record_view` narrows a table with `<prefix>_q` and `<prefix>_f_<column>`.
The canonical query keeps only the keys it names, and none of these were among them —
measured live, **every facet and search box on the jobs, contacts and ledger tables posted
a parameter the shell threw away**, so the table came back unfiltered and read as though
the filter had matched everything.

- Kept by SHAPE, not by name: enumerating every table's prefix times every column it
  facets drifts the first time a facet is added. The shape is still bounded — lowercase, a
  prefix of at most 32 characters, one of the two spellings.
- The two spellings have ONE declaration, in `shell_schemas`, which the canonical query
  and `_record_view` both already import.
- **A facet's VALUE and its LABEL are different things.** The value is what the URL carries
  and what a row is matched on; the label is what the dropdown draws. They are the same
  string for most facets and deliberately not for a place, a month or a trade — a filter
  keyed on a name stops matching the day somebody corrects the name.


### Transfer policy (2026-08-16)

- **The surface payload crosses the wire once.** `envelope.surface_payload` is the
  authority; `regions.workbench` omits its copy and the client falls back to the
  envelope's. (A region carrying a genuinely different payload keeps it.)
- **The payload answers the level the request named**, exactly as the canonical query
  does. At Compendium levels 0 and 1 the legacy `workspace.datum_grid`,
  `workspace.document_table` and `surface_payload.sections` are not sent; at level 2
  the grid is sent only for the RAW face. The legacy corpus-reflective view (no msn and
  no sandbox named) is untouched — there the two-column workbench IS the surface.
- **A section states its own cut.** The sandbox Sources section draws at most 20 pins
  per bucket and reports the exact totals beside the heading; the full register is the
  sources manager.
- **A sandbox's sources are ITS instance's (2026-08-17).** `resolve_sources` takes the
  msn and looks the manifest up at `(msn, sandbox, name)`. Keyed on the name alone, the
  four instances' `system` sandboxes collapsed onto one entry and a single manifest
  answered for all of them — measured: 473 identical pins on every instance, two of
  which hold no manifest at all. Row RESOLUTION stays tenant-wide on purpose: the farm
  manifests pin documents in FND's `registrar` and `taxonomy`, and scoping the corpus
  would report 473 legitimate cross-instance pins as missing.
- **Versioned assets are immutable, unversioned assets are not.** A `/portal/static/`
  or `/assets/` request carrying `?v=` answers `public, max-age=31536000, immutable`;
  without it, `no-cache`.
- **Compressible responses are compressed by the app**, not by whatever fronts it:
  `text/css`, `text/javascript`, `application/javascript`, `application/json`,
  `text/html` and `image/svg+xml` over 1 KB, with `Vary: Accept-Encoding` set whether
  or not the response was compressed.
- **The boot watchdog waits while scripts are still arriving** (up to a 45 s ceiling)
  rather than declaring the bundle dead on a timer. A slow link is not a failure.
- Measured effect on a 390x844 phone, cold load of the Compendium shelf:
  **2366 KB → 314 KB**; the level-0 shell response **1009 KB → 31.7 KB** uncompressed,
  5.8 KB on the wire.

## Active Shell Topology

- `/portal` is only a public redirect and must resolve to `/portal/compendium`.
- `/portal/system` is a query-preserving 302 to `/portal/compendium`. It carries no
  behaviour of its own; every key of the request survives the redirect.
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
- `shell_composition.regions` is exactly `{activity_bar, workbench}`. `regions.workbench`
  is governed by the canonical `reflective_workspace` family contract. The
  interface_panel and control_panel regions were removed, and with the control panel
  went `shell_composition.control_panel_collapsed` and the `chrome.control_panel_collapsed`
  field of the persisted shell state (an older stored value is read and ignored).
- **No shell surface renders in an overlay (2026-08-16).** Tools, app hubs, channels and
  the datum cell editor all render as WORKBENCH content. `#portalToolOverlay` and
  `#portalDatumOverlay` are retired, and with them the last shell state that had no
  address: a tool's open-ness and its active tab are now query keys, so every screen the
  operator can reach is a URL they can bookmark, share and reload onto.
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
- The **Compendium** widens that set with the keys that name its level and its faces:
  `view` (`gallery` | `list`, level 1) and `doc_view` (`scope` | `raw`, level 2). Legacy
  `mode=datums` canonicalizes to `doc_view=raw`. Tool and channel hosting adds `tool`,
  `channel`, `erp_tab`, `brevat_tab`, `oveure_tab` and `viewscope_root`.
- **The canonical query addresses the LEVEL the request named.** A request naming no
  document must not gain one, a request naming a sandbox keeps it, and the open face
  (`doc_view`) is part of the address. The workbench read service canonicalizes the
  document it AUTO-SELECTS into its workspace query; the Compendium must not inherit that,
  or a reload lands where the operator never went.
- `CTS-GIS` does not widen shell query. Its tool-local navigation and projection state is body-carried in the tool request/runtime payload.
- `CTS-GIS` runtime mode is explicit and body-carried (`runtime_mode`):
  - `production_strict` (compiled navigation/evidence baseline, fail-fast on invalid compiled state)
  - `audit_forensic` (expanded diagnostics and source forensics)
- `CTS-GIS` production runtime emits compact hot-path models:
  - `navigation_model`
  - `projection_model`
  - `evidence_model` (lazy by default)
The four "control-panel context" projections below name what each tool treats as its
identifying context. That is still true of the tools; the region that DREW those rows was
retired 2026-08-16. Where a tool needed its context visible it now states it in its own
surface — the Compendium's breadcrumb, `section_nav`, `selection_strip`. Read these as the
context each tool has, not as a pane it fills.

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
- CTS-GIS keeps node-focused `Attention`, `Intention`, `Time`, and `Archetype` as a
  tool-local `AITAS` group. It was a control-panel group; with the region retired
  2026-08-16 the group renders inside the tool's own workbench surface. Tool-local is
  the operative word — this never went through the shared shell validator, which is why
  the crosswalk survived the region unchanged.
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
