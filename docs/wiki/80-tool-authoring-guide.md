> Status: how-to
>
> [← Overview](00-overview-and-glossary.md)
>
> Rewritten 2026-08-23. The procedure was always sound; its WORKED EXAMPLE was
> `workbench_ui_view.py`, retired 2026-08-14 (`cf17ec53`), so a reader following this page
> was told to model their tool on a file that no longer exists. It now models it on
> `pim_overview.py`, which is the smallest complete tool in the tree — five attributes,
> one method — and was written the week this page was fixed, so it demonstrates the
> contract as it actually stands.

# How to author a new workbench tool

## Goal

Teach you how to add a new **workbench tool** to the MiCyte Portal: implement
the tool contract, register it so the portal can see it, declare which datums it
applies to, add the shell registry entry that lets it appear in the palette, and
then verify that it shows up in the menu-bar tool search and mounts into the
interface panel.

Tools (and lenses) exist to view and manage **hyphae** and **MSS** forms of
datums and datum-documents. A tool is a small read-shaped renderer: given a
selected datum context (sandbox + document + datum address) it produces a *panel
payload* the JS renderer paints into the workbench visualization panel.

> **Binding nuance (read this first).** Today a tool binds to datums by
> `applies_to_archetype` / `applies_to_source_kind` — widened along the datum's
> hyphae chain. It does **not** yet bind by a first-class *hyphae value* (e.g. a
> family's root common datum). This guide shows binding as it works today; see
> [Future: hyphae-value binding](#future-hyphae-value-binding) for the intended
> direction.

## Prerequisites

### Where tools live

| Concern | Path |
|---|---|
| Tool contract (protocol) | `micyte/tools/_contract.py` |
| Tool registry | `micyte/tools/_registry.py` |
| Package import wiring | `micyte/tools/__init__.py` |
| Worked-example tool (smallest complete) | [`micyte/tools/pim_overview.py`](../../micyte/tools/pim_overview.py) |
| Worked-example read service | `micyte/tools/workbench_ui/service.py` |
| Second example (content-resolving) | `micyte/tools/product_document_view.py` |
| Shell registry entry (palette target) | `micyte/state_machine/portal_shell/shell_registry.py` |
| `PortalToolRegistryEntry` dataclass | `micyte/state_machine/portal_shell/shell.py` |
| Eligibility recognizer (pure) | `micyte/state_machine/portal_shell/tool_eligibility.py` |
| Palette runtime | `fnd_app/instances/_shared/runtime/portal_palette_runtime.py` |
| Eligible-tools HTTP endpoint | `fnd_app/instances/_shared/portal_host/app.py` |
| Palette front-end | `fnd_app/instances/_shared/portal_host/static/v2_portal_tool_palette.js` |

### The contract

Every tool is a Python object that satisfies the `WorkbenchTool` `Protocol`
defined in `micyte/tools/_contract.py:20`. It is intentionally
minimal — a handful of identifying attributes and one method
(`_contract.py:30`):

```python
class WorkbenchTool(Protocol):
    tool_id: str
    label: str
    summary: str
    route: str
    applies_to_archetype: tuple[str, ...]
    applies_to_source_kind: tuple[str, ...]

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str,
        document_id: str,
        datum_address: str,
    ) -> dict[str, Any]:
        ...
```

- `tool_id` — the global key the tool is registered under and the value carried
  on `surface_query.tool`.
- `label` / `summary` — what the palette search renders for each item.
- `route` — the surface route the menu-bar palette stamps onto each item's
  `data-route` attribute; the JS `renderList` reads it and dispatches it on click
  (`_contract.py:33`).
- `applies_to_archetype` / `applies_to_source_kind` — the eligibility filters
  (see [step 3](#3-declare-what-the-tool-applies-to)).
- `build_panel_payload(...)` — returns the dict the JS renderer consumes. Keep
  it **read-shaped** (no mutations of the datum store).

The registry (`_registry.py`) is a plain dict keyed by `tool_id`. `register()`
(`_registry.py:22`) type-checks the object against the protocol and adds it;
`all_tools()` (`_registry.py:41`) returns every tool sorted by `tool_id`; and
`describe_for_palette()` (`_registry.py:46`) renders the registry as the palette
eligibility dicts.

## Step-by-step

### 1. Implement the `WorkbenchTool` contract

Create `micyte/tools/<your_tool_id>.py` with a class that carries the
five attributes and `build_panel_payload`. Model it on
[`micyte/tools/pim_overview.py`](../../micyte/tools/pim_overview.py) — the smallest
complete tool in the tree, and short enough to read in one sitting:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._registry import register


class MyTool:
    tool_id = "my_tool"
    label = "My Tool"
    summary = "Short, searchable description of what this tool views."
    route = WORKBENCH_UI_TOOL_ROUTE
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ("sandbox_source",)

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str,
        document_id: str,
        datum_address: str,
    ) -> dict[str, Any]:
        # Read-only: compose the payload from the selected datum context.
        return {
            "schema": "mycite.v2.portal.workbench.tool.my_tool.v1",
            "sandbox_id": sandbox_id,
            "document_id": document_id,
            "selected_row_address": datum_address,
        }
```

Notes drawn from the real tools:

- [`micyte/tools/pim_overview.py`](../../micyte/tools/pim_overview.py) paints the panel
  directly: `build_panel_payload` returns a `record_table` and the tool holds no state.
  This is the shape to copy unless you have a reason not to.
- A tool may instead NAVIGATE to its own surface, returning only a schema marker from
  `build_panel_payload` and doing its rendering in a read service. That was
  `workbench_ui_view`'s shape until it was retired 2026-08-14; the heavy grid rendering it
  delegated to still lives in
  [`micyte/tools/workbench_ui/service.py`](../../micyte/tools/workbench_ui/service.py).
  Reach for it only when the surface genuinely cannot be a panel.
- `micyte/tools/product_document_view.py:130`
  (`ProductDocumentViewer`) is the opposite pattern: its `build_panel_payload`
  (`product_document_view.py:144`) reads the sandbox's documents and resolves a
  full product table *inside* the payload. Use this pattern when your tool
  renders content directly into the panel.

If your tool needs more than trivial assembly, put the read logic in a sibling
service module (as `workbench_ui/` does) and keep the tool class as the
registry-facing shell.

### 2. Register it

Two things make the tool discoverable. First, self-register at module scope —
the last line of [`pim_overview.py`](../../micyte/tools/pim_overview.py) is the model:

```python
# Self-register on import.
register(MyTool())
```

Second, import your module from the package `__init__` so the registry is
populated whenever a consumer imports `micyte.tools`. Add it to the
side-effect import block in `micyte/tools/__init__.py` (alongside
`pim_overview`, `artifacts_viewer`, `product_document_view`):

```python
from . import (
    cts_gis_admin,        # noqa: F401
    cts_gis_district,     # noqa: F401
    cts_gis_map,          # noqa: F401
    my_tool,              # noqa: F401  <-- add this
    product_document_view,  # noqa: F401
    pim_overview,    # noqa: F401
)
```

Import order is irrelevant: `all_tools()` sorts by `tool_id` on read.

### 3. Declare what the tool applies to

Eligibility is the OR of two intersections, computed against the selected
document's tokens:

- `applies_to_archetype` — matches the document's *archetype set*. That set is
  derived from `document_metadata` **and** widened by walking the datum's hyphae
  chain (`tool_eligibility.py:44`, `_document_archetype_set`). This is how a tool
  applicable to an upstream rudi's archetype is still offered for a downstream
  datum.
- `applies_to_source_kind` — matches the document's `source_kind` (e.g.
  `sandbox_source`, `system_anthology`).

Pick the narrowest binding that is correct:

- `workbench_ui` is the universal grid, so it binds by source kind to both
  `sandbox_source` and `system_anthology`. A tool launched by ADDRESS instead — a hub or
  an instrument — declares neither, which is how `pim_overview` and `artifacts` say "open
  me against the instance, not against the document in focus".
- `product_document` is specific to one archetype, so it binds *only* by
  `applies_to_archetype=("agro_erp_product_profile_row",)` and deliberately
  leaves `applies_to_source_kind` empty
  (`product_document_view.py:137`). The comment there explains why: because the
  match predicate ORs the two, declaring `sandbox_source` would make the viewer
  eligible for every sandbox document, not just product profiles.

An empty `applies_to_*` pair means "universal" in the palette runtime
(`portal_palette_runtime.py:75`) — the tool matches every datum. Use that
sparingly.

### 4. Add a `PortalToolRegistryEntry`

The viz registry above is what the *menu-bar search* consults. To also be a
first-class **palette target** (with a surface, capabilities, and read/write
posture), add a `PortalToolRegistryEntry` to the tuple returned by
`build_portal_tool_registry_entries()` in
`micyte/state_machine/portal_shell/shell_registry.py:141`. Model it on
the `workbench_ui` entry (`shell_registry.py:165`):

```python
PortalToolRegistryEntry(
    tool_id="my_tool",
    label="My Tool",
    surface_id=MY_TOOL_SURFACE_ID,        # a known tool surface id
    entrypoint_id=MY_TOOL_ENTRYPOINT_ID,
    route=MY_TOOL_ROUTE,
    tool_kind=TOOL_KIND_GENERAL,
    surface_posture=SURFACE_POSTURE_PALETTE_TARGET,
    read_write_posture="read-only",
    required_capabilities=("datum_recognition",),
    default_enabled=True,
    default_workbench_visible=True,
    applies_to_source_kind=("sandbox_source",),
    summary="Short description of the tool.",
),
```

The dataclass is defined in
`micyte/state_machine/portal_shell/shell.py:477`; its
`applies_to_archetype` / `applies_to_source_kind` fields are at
`shell.py:490`. Its `__post_init__` enforces the contract (`shell.py:502`):
`surface_posture` **must** be `SURFACE_POSTURE_PALETTE_TARGET`,
`read_write_posture` must be `read-only` or `write`, and a non-extension entry's
`surface_id` must be a known tool surface. For a dedicated surface you will also
add a `PortalSurfaceCatalogEntry` to `build_portal_surface_catalog()`
(`shell_registry.py:49`) and define the route/surface/entrypoint constants in
`shell_schemas.py` (the `WORKBENCH_UI_TOOL_*` constants are the template; the
route lives at `shell_schemas.py:84`).

> If your tool simply rides the universal workbench surface (like the two
> example tools, which both set `route = WORKBENCH_UI_TOOL_ROUTE`), you do not
> need a new surface — only the viz registration in steps 1–3. The
> `PortalToolRegistryEntry` is what gives a tool its own palette-target identity
> and posture.

### 5. Verify it appears in `/portal/api/tools/eligible`

The palette runtime `build_eligible_tools_response(...)`
(`portal_palette_runtime.py:80`) reads the viz registry via `all_tools()`,
filters with `_viz_tool_matches` (`portal_palette_runtime.py:59`), and returns
`{schema, tools: [{tool_id, label, summary, route}, ...]}`. The Flask endpoint is
`GET /portal/api/tools/eligible` at
`fnd_app/instances/_shared/portal_host/app.py:1707`.

Quick checks:

```python
# With no document context, every registered tool is returned (welcome screen).
from fnd_app.instances._shared.runtime.portal_palette_runtime import (
    build_eligible_tools_response,
)
out = build_eligible_tools_response(
    tenant_id="fnd", document_id="", datum_address="", datum_store=None
)
assert any(t["tool_id"] == "my_tool" for t in out["tools"])
```

```bash
# Live endpoint (no datum context returns all tools).
curl -s "http://localhost:PORT/portal/api/tools/eligible" | python -m json.tool
```

With a real document selected, the response narrows to the tools whose
`applies_to_*` match — so confirm your tool appears for a document of the
archetype / source_kind you bound to, and does **not** appear for others.

> The standalone pure recognizer used by the shell-side palette is
> `recognize_applicable_tools(...)` (`tool_eligibility.py:64`). It applies the
> same archetype/source_kind logic (plus the hyphae-chain widening) and is what
> the architecture/unit tests pin.

### 6. Confirm it mounts in the interface panel

The front-end is `v2_portal_tool_palette.js`. `mount(target, ctx)`
(`v2_portal_tool_palette.js:177`) renders a search input plus a results list and
calls `refresh`, which fetches the eligible tools and hands them to `renderList`
(`v2_portal_tool_palette.js:120`). `renderList` paints each tool's `label` and
`summary`, stamps the `route` onto the item's `data-route` attribute, and on
click invokes `ctx.onDispatch(...)` with `{tool_id, route, datum_address,
document_id, scope_depth}`.

So once your tool is returned by the endpoint, the palette will show it in the
search list automatically, and clicking it dispatches your `route`. Type part of
your `label`/`summary`/`tool_id` into the search box to confirm `filterTools`
matches it.

## Worked example: `workbench_ui` end-to-end

`workbench_ui` is the universal SQL-backed datum grid and the cleanest tool to
trace from registration to render:

1. **Contract object** —
   [`micyte/tools/pim_overview.py`](../../micyte/tools/pim_overview.py) defines `PimOverview`
   with `tool_id="workbench_ui"`, `route=WORKBENCH_UI_TOOL_ROUTE`, and
   `applies_to_source_kind=("sandbox_source", "system_anthology")`
   (its `applies_to_*` are empty — it is launched by address).
2. **`build_panel_payload`** — returns just a schema marker
   returns a `record_table` rather than *navigating to its own
   surface* rather than painting into the panel.
3. **Self-register** — `register(WorkbenchUiTool())` at
   the last line of `pim_overview.py`, and the module is imported from
   `micyte/tools/__init__.py` so the registry is populated on import.
4. **Surface rendering** — the actual two-pane document table + datum grid +
   directive overlay is produced by `WorkbenchUiReadService`
   (`micyte/tools/workbench_ui/service.py:468`); its `read_surface`
   (`service.py:586`) reads the authoritative catalog, projects rows, resolves
   lenses, and emits `interface_panel_sections` + a `surface_payload`. (Scope
   notes live in `micyte/tools/workbench_ui/README.md`.)
5. **Palette target** — the matching `PortalToolRegistryEntry`
   (`shell_registry.py:165`) declares it `read-only`,
   `default_workbench_visible=True`, and `applies_to_source_kind=("sandbox_source",
   "system_anthology")`, mirroring the viz attributes so the eligibility logic
   agrees from both directions.
6. **Endpoint + palette** — `build_eligible_tools_response`
   (`portal_palette_runtime.py:80`) returns it whenever a `sandbox_source` or
   `system_anthology` document is selected (and always when no document is
   selected), and `v2_portal_tool_palette.js` renders and dispatches it.

For a tool that resolves and renders content *into* the panel rather than
navigating away, read `product_document_view.py:130` alongside this — same
contract, different `build_panel_payload` strategy.

## Pitfalls

- **A workbench tool renders; it does not write on a schedule.** If what you are
  building runs on a CONDITION rather than for a person — the user's "task rabbit"
  — it belongs in [`micyte/automation`](../../micyte/automation/), not here.
  `micyte.tools.register` refuses anything carrying a `routine_id`, and
  `micyte.automation.register` refuses anything carrying `route` /
  `build_panel_payload` / `applies_to_archetype`. The distinction is enforced at
  both doors because a taxonomy nothing enforces is a naming convention.
- **Eligibility is by declaration.** A registry entry that declares neither
  `applies_to_archetype` nor `applies_to_source_kind` is never offered. (The
  `is_extension` flag that used to exempt Utilities extension entries from the
  palette was removed in the Phase 3 taxonomy; no entry had raised it since those
  tools were dissolved.)
- **The eligibility recognizer must stay pure.** `tool_eligibility.py` is
  AST-scanned by `fnd_app/tests/architecture/test_palette_eligibility_purity.py`
  for forbidden imports (`os`, `sys`, `pathlib`, `sqlite3`, adapters, ports,
  instances, …) and for any top-level cache/handle/session state. Keep all
  eligibility logic data-driven off the registry entry's `applies_to_*` tuples;
  never add I/O there.
- **Keep `build_panel_payload` read-shaped.** Tools view and inspect; they do
  not mutate the datum store. `WorkbenchUiReadService` is explicit that it stays
  read-only and that mutation slots are emitted by the workbench runtime, not the
  tool (`workbench_ui/service.py:829`). Compose payloads from reads only.
- **Archetype OR source_kind, not AND.** Because the predicate ORs the two
  bindings, declaring a broad `source_kind` alongside a narrow archetype makes
  your tool eligible for far more documents than intended — see the explicit
  comment on `product_document_view.py:137`.
- **Two registries, kept in sync.** The viz registry (`_registry.py`) feeds the
  menu-bar search; the shell `PortalToolRegistryEntry` list (`shell_registry.py`)
  feeds palette-target identity. Their `applies_to_*` should agree, as
  a registered tool keeps them in step with `shell_registry`.
- **Metadata key names matter.** The palette runtime reads
  `datum_template_archetype` and `samras_family` from `document_metadata`
  (`portal_palette_runtime.py:107`), while the pure recognizer reads the
  `archetype` key (`tool_eligibility.py:44`). When you wire test fixtures, use
  the key the path under test actually reads. **A write path that CREATES a
  document must stamp it too** — `save_invoice`/`save_sale` build theirs with
  `_archetype_metadata(name)`. Created with `metadata={}` a document carries no
  archetype at all, so the palette can never offer the viewer written for it, and
  nothing fails: the named-document tools resolve by `canonical_name` and keep
  working, so only discovery goes quiet.
- **A second writable record table is not a second renderer.** The
  `editable_table` container (`micyte/tools/_editable_table.py`) takes its field
  set from the payload — column 0 is the record's server-assigned identity, the
  declared `fields` fill the rest, and `save_route`/`sandbox_id` say where the row
  POSTs. `inventory_manager` (supply batches) and `sales_manager` (sales) share
  it. **Never give the container a fallback sandbox**: it used to read
  `payload.sandbox_id || "<a_farm_sandbox>"` and put that name in the request
  body, so a payload that had lost its farm wrote into one particular farm's
  books. With no sandbox it disables saving and says so.
- **A row's buttons are declarations, not renderer branches.** `row_actions`
  (`post_action` / `toggle_action` / `nav_action`) carries them in the payload.
  The renderer used to know the supply batch's *Retire* toggle and its *Plan into
  plots* jump by name, so the third record type's action would have been a third
  branch in a renderer whose whole point is not to know what a record is. A row
  action restates the row and merges its own keys in, and it always sends
  **date-kind fields blank** — every write route reads an omitted date as "keep
  the one on file", so an action must never re-stamp the record to today.
- **A derived figure is a `computed_columns` entry, not a field.** A field gets an
  input box and posts under its name; giving one to a server-derived number lets
  the operator type a value the write route ignores. On-hand in the offering table
  is the case: it comes from the farm's supply batches, and an input there would
  let a catalog assert stock the farm's own records do not support.
- **A published artifact has to stand alone.** A still is published by itself, so
  anything it needs in order to be read has to be *in* it. The offering row stores
  its listing NAME rather than resolving the product's label from `lcl`, because
  the alternative is publishing a farm's entire node tree to name two vegetables —
  discovered by publishing one and getting back `1-1-5-2 | $3.00 / lb`.

- **Money is an integer count of cents, never text and never a float.** Every money field
  — an offer's price, a sale's price, a supply batch's cost, a contract's cost — is a
  magnitude against the sandbox's fiat datum (`micyte/core/datum_ops/fiat_datum.py`),
  and `parse_cents` / `format_cents` are the only place it changes representation.
  Half a cent is *refused*, not rounded — rounding picks a side of the operator's
  intent and records the result as though it were what they typed. The tools layer
  formats for display; the port carries `price_cents: int`, because a port that hands
  a storefront `"$4.00"` has made the storefront parse money out of a string.

  An **amount** is not money and stays a nominal: `"10 lbs"` is a label carrying its own
  unit, and nothing totals it. What a batch cost and what its produce sells for are the two
  ends of one ledger, so those two must be the same kind of value or nothing can subtract
  them — and normalizing a cost to cents made the contract dedup strictly better, since
  `"$40"`, `"40.00"` and `" $40.00 "` were three signatures that each minted a row and
  double-counted the invoice draw-down.

- **A price marker is NOT network-wide, so never hardcode its address.** Every other
  column kind maps to a marker that means the same thing everywhere; the fiat
  babelette lives wherever a given sandbox's anchor allocated it. Resolve it with
  `find_fiat_chain(anchor_doc)`, which identifies the chain **structurally** — by what
  it is made of, not where it sits or what it is called — so a sandbox provisioned
  differently, and a still that arrived from another network, both read correctly.
  A sandbox with no chain gets a refusal naming the provisioner; it does not get a
  default address, because the same `3-1-N` names a different field in every
  namespace and a guess would price a product against another field's meaning.

- **A record document should carry the definitions of the markers it uses.**
  Recognition resolves an `rf.3-1-N` through `document.anchor_rows`, and every document
  in the live store carries **zero** of them — so every reference reads as
  `unresolved_anchor`, no family is recognized, and *no lens binds anywhere in the raw
  workbench*, not even the title decoder. The write path now attaches the **minimum
  abstraction closure** (`abstraction_closure`) rather than the whole anchor, which is
  a few dozen rows instead of a farm's entire lcl-SAMRAS bitstream. It fixes the raw
  workbench, and it makes a published still stand alone without the exporter arranging
  anything.

- **Resolve a lens per BINDING, not per row.** The row-level `recognized_family` is the
  *first* family recognized on the row — right for a single-value datum, wrong for a
  record row, where an offering leads with an lcl reference and would render its price
  with the node-address lens. Each `reference_binding` carries its own
  `expected_value_kind`, and that is what a cell overlay resolves from.

## Publishing a document

`export_registry_still` → `private/stills/<name>.mss` → *Utilities > Resource
Management* → `GET /__mss/public/stills/<name>.mss`. Four steps, and they agree on
**one identifier**: the filename stem is the still's name, which is the key
`held_stills()` indexes by, the name the contact card's allowlist carries, and the
name the serve route takes. The exporter once wrote `stl.<msn>.<name>.mstl` and
matched none of them, so an export was invisible to the surface that publishes it.
Publication itself is a **card mutation** and there is no other publish path —
dropping a file in the stills directory holds it privately, nothing more.

## Testing your tool

Add and run the tests that pin the contract for the surfaces you touched:

- **Eligibility logic** — `micyte/tests/unit/test_tool_eligibility.py`
  exercises `recognize_applicable_tools` (extensions excluded, archetype match,
  source_kind match, hyphae-chain widening, deterministic ordering, empty/unknown
  address). Add a case that asserts your `applies_to_*` binding matches the
  documents you expect and rejects the ones you don't.
- **Palette response + endpoint** — `fnd_app/tests/integration/test_tool_palette.py`
  drives `build_eligible_tools_response` and the `GET /portal/api/tools/eligible`
  endpoint, and asserts each tool entry carries `label`, `summary`, and the
  dispatch `route`. It already checks that `cts_gis` and `workbench_ui` appear in
  the no-context response; extend the assertions to include your `tool_id`.
- **Purity guard** — `fnd_app/tests/architecture/test_palette_eligibility_purity.py`
  is your safety net if you were tempted to add I/O to the recognizer. Run it to
  confirm you didn't.

Run them with the project's test runner (e.g.
`python -m pytest micyte/tests/unit/test_tool_eligibility.py
fnd_app/tests/integration/test_tool_palette.py
fnd_app/tests/architecture/test_palette_eligibility_purity.py`).

## Future: hyphae-value binding

Today a tool binds by **archetype / source_kind**, widened along the hyphae
chain — not by a first-class **hyphae value** (e.g. binding directly to a
family's *root common datum*). `PortalToolRegistryEntry.applies_to_hyphae_value`
and the third branch of `recognize_applicable_tools` are in place; no production
entry sets one yet. When hyphae-value binding lands, a tool will be able to
declare the specific hyphae value (root common datum of a family) it operates on,
rather than approximating that intent through archetype tokens.

A field that once claimed this ground, `manipulates_datum_kinds`, was removed
instead of wired: it described what a tool WRITES, which is not an eligibility
question at all, and it went a year normalized, serialized and read by nothing.
Reserving a field for a future check is how that happens — the check arrives
somewhere else, and the field stays behind looking like a guarantee.

For the canonical-datum and hyphae-flag model that this future binding will key
off, see [60 — Canonical datum and hyphae flags](60-canonical-datum-and-hyphae-flags.md)
(forward reference).

## See also

- [40 — Tools and lenses as-built](40-tools-and-lenses-asbuilt.md)
- [60 — Canonical datum and hyphae flags](60-canonical-datum-and-hyphae-flags.md)
- [82 — Demo sandbox cookbook](82-demo-sandbox-cookbook.md)
