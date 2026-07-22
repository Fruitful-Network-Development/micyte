# Tools & Lenses (as-built)

> Status: as-built
[← Overview](00-overview-and-glossary.md)

## Purpose

Tools and lenses are the portal's near-term focus. This page documents what
is **actually wired today** for the two subsystems and where the code diverges
from the product vision:

- **Tools** are small, self-registering visualization renderers. The menu-bar
  search bar lets an operator search them, a dropdown lists the ones eligible
  for the current selection, and clicking one adds it to the workbench by
  dispatching its `route`. Tools are discovered through the registry and
  filtered by **archetype / source-kind intersection** (widened along the
  hyphae chain) — *not* yet bound directly to a hyphae value or to a family's
  root common datum.
- **Lenses** are stateless display/canonical codecs (`decode` / `encode` /
  `validate_display`). The workbench resolves one lens per recognized datum
  family (or value-kind / overlay) and uses it to render, for example, a
  binary magnitude as its nominal ASCII. Lenses **auto-apply per family**;
  there is no Utilities-managed / Control-Panel-toggled lens UX today.

The first-class hyphae-value binding for tools and the Utilities-manage /
Control-Panel-toggle lifecycle for lenses are proposed, not built. See the
forward references in [Vision-fit](#vision-fit).

## File map

Paths are relative to the repo root. `path:line` points at the cited
definition; LOC is the file's line count.

### Tools — registry & contract

| Path | Role | LOC |
|---|---|---|
| `micyte/tools/_registry.py:19` | Global `TOOL_REGISTRY` dict (`tool_id` → `WorkbenchTool`). | 63 |
| `micyte/tools/_registry.py:22` | `register(tool)` — type-checks and inserts (overwrite by id). | — |
| `micyte/tools/_registry.py:41` | `all_tools()` — every tool, sorted by `tool_id`. | — |
| `micyte/tools/_registry.py:46` | `describe_for_palette()` — palette eligibility dicts. | — |
| `micyte/tools/_contract.py:20` | `WorkbenchTool` runtime-checkable Protocol: `tool_id`/`label`/`summary`/`route`/`applies_to_*` + `build_panel_payload`. | 51 |
| `micyte/tools/__init__.py:18` | Imports each tool module for self-registration side-effect. | 35 |
| `micyte/tools/_shared/README.md:1` | Empty placeholder stub for shared tool contracts/helpers. | 3 |

### Tools — concrete renderers

| Path | Role | LOC |
|---|---|---|
| `micyte/tools/workbench_ui_view.py:30` | `WorkbenchUiTool` palette entry; `applies_to_source_kind=("sandbox_source","system_anthology")`, no archetype. Navigates to its surface rather than painting the panel. | 71 |
| `micyte/tools/product_document_view.py:130` | `ProductDocumentViewer`; `applies_to_archetype=("agro_erp_product_profile_row",)`, no source-kind. Resolves product/taxonomy names cross-document. | 253 |
| `micyte/tools/product_document_view.py:72` | `LclNameIndex` — `node_address → display name` from `4-2-*` rows; falls back to `BinaryTextLens.decode` of the 512-bit title. | — |
| `micyte/tools/workbench_ui/service.py:468` | `WorkbenchUiReadService` — ~900-LOC read-only spreadsheet builder. | 992 |
| `micyte/tools/workbench_ui/README.md:1` | Ownership note: read-only two-pane SQL spreadsheet; overlays additive only. | 5 |

### Tool eligibility & shell registry

| Path | Role | LOC |
|---|---|---|
| `micyte/state_machine/portal_shell/tool_eligibility.py:64` | `recognize_applicable_tools` — pure archetype/source-kind intersection, widened via `derive_hyphae_chain`. | 115 |
| `micyte/state_machine/portal_shell/tool_eligibility.py:44` | `_document_archetype_set` — doc metadata archetype + per-row archetypes reached through the chain. | — |
| `micyte/state_machine/portal_shell/shell_registry.py:141` | `build_portal_tool_registry_entries` — the shell-side tool registry (workbench_ui, agro_erp, extensions). | 310 |
| `micyte/state_machine/portal_shell/shell_registry.py:165` | `workbench_ui` entry; `applies_to_source_kind=("sandbox_source","system_anthology")`. | — |
| `micyte/state_machine/portal_shell/shell_registry.py:160` | `agro_erp` entry; `applies_to_archetype=("agro_erp_taxonomy_row",)`. | — |

### Lenses

| Path | Role | LOC |
|---|---|---|
| `micyte/state_machine/lens/base.py:13` | `Lens` ABC — `decode`/`encode`/`validate_display`. | 145 |
| `micyte/state_machine/lens/base.py:31` | Built-ins: Identity / TrimmedString / SamrasTitle / EmailAddress / SecretReference / NumericHyphen / BinaryText. | — |
| `micyte/state_machine/lens/base.py:115` | `BinaryTextLens.decode` — binary → printable ASCII, `"{n} bits"` fallback. | — |
| `micyte/state_machine/lens/registry.py:25` | `DatumLensRegistry` — family → overlay → value-kind dispatch. | 86 |
| `micyte/state_machine/lens/registry.py:73` | `resolve_datum_lens(...)` module helper over the default registry. | — |
| `micyte/state_machine/lens/__init__.py:1` | Re-exports lenses + `resolve_datum_lens`. | 33 |
| `micyte/state_machine/lens/README.md:1` | Lens authority note + built-in baselines + usage pattern. | 47 |

### Palette runtime & front-end

| Path | Role | LOC |
|---|---|---|
| `fnd_app/instances/_shared/runtime/portal_palette_runtime.py:80` | `build_eligible_tools_response` — tools for the selected document. | 243 |
| `fnd_app/instances/_shared/runtime/portal_palette_runtime.py:169` | `build_sandbox_visualizers_response` — visualizers across a whole sandbox, ranked by reach. | — |
| `fnd_app/instances/_shared/runtime/portal_palette_runtime.py:59` | `_viz_tool_matches` — empty `applies_to_*` ⇒ universal; empty context ⇒ all tools. | — |
| `fnd_app/instances/_shared/portal_host/app.py:1707` | Flask `GET /portal/api/tools/eligible`. | — |
| `fnd_app/instances/_shared/portal_host/app.py:1732` | Flask `GET /portal/api/visualizers/for-sandbox`. | — |
| `fnd_app/instances/_shared/portal_host/static/v2_portal_tool_palette.js:177` | `mount` — search input + result list. | 208 |
| `fnd_app/instances/_shared/portal_host/static/v2_portal_tool_palette.js:159` | `refresh` — fetches eligible/for-sandbox, filters, renders. | — |
| `fnd_app/instances/_shared/portal_host/static/v2_portal_tool_palette.js:120` | `renderList` — dropdown items; click dispatches `{tool_id, route, ...}`. | — |

### Tests (context)

| Path | Role | LOC |
|---|---|---|
| `fnd_app/tests/unit/test_tool_eligibility.py:101` | Eligibility intersection + hyphae-chain widening + extension exclusion. | 218 |
| `fnd_app/tests/unit/test_state_machine_lens_registry.py:14` | `BinaryTextLens` ASCII decode + family/value-kind preference. | 31 |
| `fnd_app/tests/architecture/test_palette_eligibility_purity.py:75` | AST-scans `tool_eligibility.py` for I/O imports — enforces purity. | 138 |

## How it works

### Tool registry

A tool is any object satisfying the `WorkbenchTool` Protocol
(`_contract.py:20`): the attributes `tool_id`, `label`, `summary`, `route`,
`applies_to_archetype`, `applies_to_source_kind`, plus a `build_panel_payload`
method. There is no base class to subclass — `register()` only checks
`isinstance(tool, WorkbenchTool)` against the runtime-checkable Protocol
(`_registry.py:28`).

Tools self-register by calling `register(MyTool())` at module scope; the
package `__init__.py` imports each tool module purely for that side-effect
(`__init__.py:18`), so importing `micyte.tools` populates
`TOOL_REGISTRY`. `all_tools()` returns them sorted by `tool_id` for stable
ordering (`_registry.py:43`). Two concrete tools ship today:

- **Workbench UI** (`workbench_ui_view.py:30`) — the universal datum grid. It
  declares `applies_to_source_kind=("sandbox_source","system_anthology")` and
  **no** archetype, so it is offered for any sandbox-source or anthology
  document. Its `build_panel_payload` does *not* render into the visualization
  panel; it returns a marker dict with `navigates_to_surface: True`
  (`workbench_ui_view.py:61`) — selecting it from the palette navigates to its
  dedicated surface route, where `portal_workbench_ui_runtime` renders the
  full spreadsheet.
- **Product Document Viewer** (`product_document_view.py:130`) — declares
  `applies_to_archetype=("agro_erp_product_profile_row",)` and **no**
  source-kind, deliberately so it does not light up for every sandbox doc
  (the match predicate ORs archetype and source-kind). It resolves each
  product row's references against sibling `lcl`/`txa` documents via
  `LclNameIndex` (`product_document_view.py:72`), reusing `BinaryTextLens` to
  decode 512-bit binary titles.

> Note: there are **two** registries. The lightweight `WorkbenchTool` registry
> above (`micyte/tools`) is what the palette runtime consults. A separate,
> richer shell-side registry of `PortalToolRegistryEntry` objects is built by
> `build_portal_tool_registry_entries` (`shell_registry.py:141`) and consumed
> by `recognize_applicable_tools`. The two are kept in sync by hand — e.g. the
> `workbench_ui` source-kinds match in both (`workbench_ui_view.py:45` and
> `shell_registry.py:178`).

### Eligibility: archetype / source-kind intersection (widened by the hyphae chain)

`recognize_applicable_tools(datum_doc, datum_address, registry)`
(`tool_eligibility.py:64`) is the canonical, **pure** eligibility filter (its
purity is enforced by `test_palette_eligibility_purity.py`). It:

1. Derives the hyphae chain for the selected address via `derive_hyphae_chain`
   (`tool_eligibility.py:92`); an unknown address yields `()` rather than
   raising.
2. Builds the document's archetype set from `document_metadata["archetype"]`
   plus the per-row `archetype` token of every row reached along that chain
   (`tool_eligibility.py:44`) — this is the "widening" step: a tool applicable
   to an upstream rudi is offered even if the selected row itself has no
   archetype.
3. Includes a registry entry when it is **not** an extension AND either its
   `applies_to_archetype` intersects the document's archetype set OR its
   `applies_to_source_kind` intersects the document's (single-element)
   source-kind set (`tool_eligibility.py:106`).
4. Returns the matches sorted by `tool_id`.

The palette runtime (`portal_palette_runtime.py`) implements the same predicate
shape against the lightweight registry: `_viz_tool_matches`
(`portal_palette_runtime.py:59`) treats empty `applies_to_*` as universal and,
when there is no document context at all, returns every tool so first-load
search is useful.

### Palette flow: menu-bar search → dropdown → add-to-panel

This flow exists end-to-end today:

1. The front-end `v2_portal_tool_palette.js` `mount()` paints a search `<input>`
   and a results list (`v2_portal_tool_palette.js:177`).
2. `refresh()` (`v2_portal_tool_palette.js:159`) chooses a fetcher: when a
   sandbox is in context with no specific document selected it calls
   `GET /portal/api/visualizers/for-sandbox`; otherwise it calls
   `GET /portal/api/tools/eligible`. Both endpoints live in the Flask host
   (`app.py:1707`, `app.py:1732`) and delegate to `build_eligible_tools_response`
   / `build_sandbox_visualizers_response` (`portal_palette_runtime.py:80`,
   `:169`). The for-sandbox response ranks visualizers by reach (how many docs
   each can render, `portal_palette_runtime.py:227`).
3. The fetched list is filtered client-side by the search query
   (`filterTools`, `v2_portal_tool_palette.js:106`) and rendered as a dropdown
   (`renderList`, `:120`). Each `<li>` carries `data-tool-id` and `data-route`.
4. Clicking an item invokes `ctx.onDispatch({tool_id, route, datum_address,
   document_id, scope_depth})` (`v2_portal_tool_palette.js:146`). The `route`
   is the tool's canonical surface route; the shell dispatcher deep-links it
   into the unified `/portal/system?tool=<id>` workbench (per the `route`
   contract in `_contract.py:33`).

### Lens registry & built-in lenses

A lens is a stateless codec over `Lens` (`base.py:13`) with three methods:
`decode(canonical_value)` → display, `encode(display_value)` → canonical, and
`validate_display(display_value)` → tuple of issue codes. Built-ins
(`base.py:31`):

- **IdentityLens** — pass-through.
- **TrimmedStringLens** — strips whitespace.
- **SamrasTitleLens** — uppercases ASCII; validates non-empty + ASCII.
- **EmailAddressLens** — lowercases; validates `@` placement.
- **SecretReferenceLens** — never exposes secret material; rejects values
  containing `password`.
- **NumericHyphenLens** — validates hyphen-separated digit groups
  (SAMRAS / HOPS magnitudes).
- **BinaryTextLens** — decodes a printable binary string to ASCII; on
  non-printable or partial input returns `"{n} bits"` (`base.py:115`). This is
  the **nominal-ASCII** example from the vision: a datum's binary magnitude is
  rendered as readable text, with a bit-count fallback.

`DatumLensRegistry` (`registry.py:25`) maps **recognized family** →
**overlay kind** → **primary value kind**, in that precedence, to a lens
instance, defaulting to Identity (`registry.py:67`). Examples:
`nominal_babelette`/`network_babelette`/`title_babelette` → `BinaryTextLens`;
`samras`/`hops` families → `NumericHyphenLens`. The module-level
`resolve_datum_lens(...)` (`registry.py:73`) wraps a single shared
`DEFAULT_DATUM_LENS_REGISTRY`. `LensResolution` (`registry.py:14`) carries the
chosen `lens`, what it `matched_on` (`"family"` / `"overlay"` / `"value_kind"`
/ `"fallback"`), and the matched `token`.

> Note: `SamrasTitleLens`, `EmailAddressLens`, and `SecretReferenceLens` are
> defined and exported but are **not** wired into `DatumLensRegistry`'s family /
> value-kind / overlay maps — they are available for callers that select a lens
> directly, not auto-resolved by family.

### How the workbench applies lenses

The read-only workbench builder resolves and applies a lens **per row** during
projection (`workbench_ui/service.py:528`). For each row it calls
`resolve_datum_lens(recognized_family=..., primary_value_kind=...,
overlay_kind=...)` from the row's recognition render-hints, then computes a
`display_value` by `lens.decode(primary_value_token)`, falling back to joined
labels or the object ref (`service.py:533`). The resolved `lens_id` and
`matched_on` are surfaced on the row and in the interface panel's "Lens
Resolution" section (`service.py:846`). Family + lens resolution are
**presentation-only** and never rewrite canonical row identity
(`service.py:827`).

Separately, the workbench exposes a coarse **`workbench_lens` query mode** of
`"interpreted"` vs `"raw"` (`service.py:56`, default `"interpreted"`,
`service.py:34`). This is a column-set toggle (raw shows `raw_preview` +
hyphae-hash badge; interpreted shows labels/relation/object_ref) — it is *not*
the per-family `DatumLensRegistry` lens, and is not operator-managed beyond the
URL query parameter.

## Vision-fit

| Vision capability | Status | Evidence / gap |
|---|---|---|
| Menu-bar search → dropdown → add tool to interface panel | **Implemented** | `v2_portal_tool_palette.js` + `/portal/api/tools/eligible` + `/portal/api/visualizers/for-sandbox`. |
| Render a datum's nominal ASCII instead of its binary magnitude | **Implemented** | `BinaryTextLens.decode` (`base.py:115`) wired via `DatumLensRegistry` family map + applied in `service.py:528`. |
| Tools bind to a datum's **hyphae value** or a **family's root common datum** | **Absent** | Tools bind by `applies_to_archetype` / `applies_to_source_kind`, widened through the hyphae chain (`tool_eligibility.py:64`) — not to a specific hyphae value or family-root datum. Proposed first-class hyphae-flag binding: see [60-canonical-datum-and-hyphae-flags.md](60-canonical-datum-and-hyphae-flags.md) (forward ref). |
| Lenses keyed to a datum's **flagged** hyphae value (MSS abstraction-path flag) | **Absent** | Lenses resolve by `recognized_family` → overlay → `value_kind` (`registry.py:51`); there is no MSS-flag → hyphae-value match. Forward ref: [60-canonical-datum-and-hyphae-flags.md](60-canonical-datum-and-hyphae-flags.md). |
| Lenses **managed** from a Utilities page | **Absent** | No Utilities lens-management surface exists; lenses are hard-coded in `DatumLensRegistry`. Forward ref: [81-lens-authoring-guide.md](81-lens-authoring-guide.md). |
| Lenses **toggled** on/off from the Control Panel | **Absent** | Lenses auto-apply per family during projection; the only operator control is the coarse `workbench_lens=interpreted|raw` query mode. Forward ref: [81-lens-authoring-guide.md](81-lens-authoring-guide.md). |
| Tools render into a shared interface/visualization panel | **Partial** | The `WorkbenchTool` contract returns a `panel_payload` for `regions.visualization_panel` (`_contract.py:42`), but both shipped tools instead carry a `route` and navigate to a dedicated surface (`workbench_ui_view.py:61`); no shipped tool paints the panel via `build_panel_payload`. |

## Open questions

- **Which registry is canonical?** The lightweight `WorkbenchTool` registry
  (`micyte/tools`) and the shell `PortalToolRegistryEntry` registry
  (`shell_registry.py:141`) carry overlapping but separately-maintained
  eligibility metadata. A future hyphae-flag binding would need a single
  source of truth.
- **How does a hyphae "flag" become an eligibility key?** The vision defines a
  flag as "compile a datum doc's MSS along the minimum-but-complete abstraction
  path and match against a registered hyphae value." Today eligibility uses
  per-row `archetype` tokens reached through `derive_hyphae_chain`, not a
  compiled-MSS match. The mapping from MSS-flag to the existing archetype /
  family resolution is unspecified.
- **Lens lifecycle ownership.** If lenses become Utilities-managed and
  Control-Panel-toggled, where does the per-tenant enabled/disabled lens state
  live (the registry is a process-global singleton, `registry.py:70`), and how
  does it reconcile with the auto-resolution in `service.py:528`?
- **Panel vs. surface tools.** `build_panel_payload` is part of the contract
  but unused by shipped tools. Is in-panel rendering still the intended end
  state, or have surface-navigating tools superseded it?
