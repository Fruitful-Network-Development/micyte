# Portal Vocabulary Glossary

Canonical vocabulary for shell/docs/runtime alignment after the AITAS/NIMM workbench contract break.

| Retired or Parallel Term | Canonical Term | Status | Replacement |
|---|---|---|---|
| public right-rail compatibility aliases | `Interface Panel` | Removed — region deleted (tools render in the menubar-search → full-screen overlay) | None |
| Header text buttons for `Control Panel` / `Workbench` | Menubar: `Control Panel` icon-toggle + right-aligned tool search (the `Workbench` and `Interface Panel` toggles were removed) | Canonical | N/A |
| Tool free-form panel coexistence wording | Tool default single-click exclusivity + double-click route lock mode | Canonical | N/A |
| `stacked_focus_panel` | `focus_selection_panel` | Legacy removed; canonical contract retained | Removed |
| `operational-status` surface language | Unified shell/tool posture language | Legacy removed; canonical contract retained | Removed |

Notes:

- CTS-GIS phase-B (v2.5.4) removes legacy CTS-GIS alias acceptance from active contracts.
- The canonical shell chrome language is `ide-shell`, `ide-menubar`, `ide-body`, `Activity Bar`, `Control Panel`, `Workbench`, and `Interface Panel`.

## Disambiguation: Workbench (region-family vs surface-specific renderers)

The word `workbench` is overloaded. The canonical disambiguation is:

| Term | Definition |
|---|---|
| `Workbench` (region-family) | The center region of the three-panel portal layout. Every surface emits a region-family-`workbench` content payload. |
| `datum-file workbench` | The shared workbench renderer used on every surface (SYSTEM and every tool surface). It is **purely reflective**: it materializes the current MiCyte state (sandbox → file → datum → object) through `state_reflection`, `document_collection`, `active_document`, and optional `layered_datum_table` fields. The workbench has **no discrete modes** — content is determined by which focus-stack levels the AITAS Space value contains. When no active document is in focus, `document_collection.documents` is rendered as a card list; when a document is focused, `layered_datum_table` is rendered. Region kind: `datum_file_workbench`, schema `mycite.v2.portal.shell.region.workbench.v2`. |
| `AITAS Space value` | The engine behind the workbench's reaction. Updated on every navigation event (in, out, left, right within a level). The AITAS fields `attention`, `intention`, `time`, `archetype` describe the current observational posture. When `intention === "investigate"` and `current_datum` is set, the Interface Panel automatically displays the datum focus widget. |
| `NIMM directive` | A preloaded, state-contextualized action script that backs control panel buttons and workbench interactions. Each `nimm.actions` entry carries `{action_id, directive, script_hint}`. Controls must not encode action semantics in the renderer; they read them from `nimm.actions`. |
| `sandbox` | The highest datum-document grouping inside a portal `msn_id`. A datum-file workbench may focus only one sandbox at a time. |
| `SYSTEM datum-file workbench` | The datum-file workbench instantiated against the `system` sandbox only (anchor `anthology`). Reachable at `/portal/system`. |
| `tool datum-file workbench` | The same shared workbench instantiated against a tool sandbox such as `cts-gis`; its default anchor token is `anchor`. |
| `Workbench UI` (tool) | The SQL authority lens at `/portal/system/tools/workbench-ui`. Purely reflective: its workbench materializes the SQL authority data through the same `state_reflection` contract. It is not a primary or stand-alone tool; its data flows through the state machine and is observed through the interface surface. |
| `NETWORK system-log workbench` | The system-log surface workbench renderer (region-family-`workbench`). Distinct from the datum-file workbench; logs are not datum documents. |

## Interface Panel vs Inspector (retired)

`Inspector` is a retired term. The canonical name for the right-rail observation region is **Interface Panel** (`regions.interface_panel`, CSS class `ide-interfacePanel`).

The Interface Panel serves two roles depending on AITAS state:

1. **Widget/section mode** (system and non-tool surfaces): Displayed beside the workbench simultaneously. Shows tool-specific widgets and section content.
2. **Datum focus mode** (when `aitas.intention === "investigate"` and `current_datum` is set): Displays the `renderDatumFocusWidget` — a structured view of the focused datum's row data, hyphae hash, and available NIMM directive actions.

**Toggle exclusivity rule:** On tool surfaces (`shell-composition === "tool"`), opening the Interface Panel closes the Workbench, and vice versa. On non-tool (system) surfaces, both panels can be visible simultaneously. The user may override the exclusivity by choosing to lock both panels open.

## Disambiguation: MSS (document version hash vs SAMRAS magnitude)

`MSS` (Monotonic Structured Serialization) appears in two distinct contexts that must
not be confused:

| Term | Definition |
|---|---|
| `MSS document version hash` (`mos.mss_sha256_v1`) | The SHA-256 over the canonical (`MSS`) form of an entire datum document. Stored as `documents.version_hash`. The MSS form is the indiscriminate inclusion of every row of the document, ordered canonically by `(layer, value_group, iteration)` with every reference datum address materialized. Computed by `micyte/core/mss/datum_identity.py::compute_mss_hash`. |
| `MSS bitstream` (`canonical_v2`) | The SAMRAS magnitude bitstream used by the SAMRAS structural abstraction (e.g. `1-1-2` `msn`, `1-1-3` `ruigi`). Composed of unary widths, fixed-width stop counts, and breadth-first child counts. Decoded and regenerated by `micyte/core/samras/`. Not the same thing as a document version hash; it lives inside a single datum row. |

When ambiguous, prefer `MSS document version hash` for the document-level identity
and `SAMRAS magnitude bitstream` for the row-level structural abstraction.

## Disambiguation: Hyphae value (MOS canonical identity vs CTS-GIS source-generation)

`Hyphae value` also appears in two distinct contexts:

| Term | Definition |
|---|---|
| `Hyphae value (MOS)` | The canonical minimal abstraction identity of a single datum: the ordered set of every preceding rudi datum (`0-0-1` … `0-0-K`) needed to abstract that datum, even if not directly referenced. The chain is derived by `micyte/core/mss/datum_identity.py::derive_hyphae_chain` and stored serialized in `datum_row_semantics.hyphae_chain_json`. Binary payloads (`stl.`) encode this hyphae value; their decompiled JSON form is the `cptr.` cached source. |
| `Hyphae value (CTS-GIS)` | A specialisation of the same idea for the CTS-GIS `filament datum` source-generation pipeline: the derived connective value used when composing a source datum file from its filament-datum relationship chain, preserving primary boundary and additive collection intent. |

The CTS-GIS `filament datum` and its hyphae-value usage live in the
`packages/modules/cross_domain/cts_gis/` module; the MOS hyphae value is a property of
*every* datum and is computed by the core MSS library.

## CTS-GIS Terms

- **filament datum**: a source-file owner binding row (typically `7-*`) used as the forward-facing access point for a profile source, including primary and additive collection references for projection mediation.
- **hyphae value (CTS-GIS)**: the derived connective value used when composing a source datum file from its filament datum relationship chain, preserving primary boundary and additive collection intent across source-generation workflows. (See above for disambiguation against the MOS hyphae value.)

## Datum-Document Naming Terms

- **canonical document id**: a `lv.<msn>.<sandbox>.<name>.<hash>` / `stl.<msn>.<name>.<hash>` / `cptr.<msn>.<name>.<hash>` identifier. Validated by `micyte/core/document_naming/`.
- **legacy alias**: a pre-canonical document identifier (`system:anthology`, `sandbox:<tool>:<filename>.json`). Retained on the `documents.legacy_alias` column for one cycle of compatibility.
- **anchor**: the canonical entry document of a sandbox. Named `anthology` for the system sandbox; named `anchor` for every other sandbox. Carries `documents.is_anchor = 1`.
- **canonical name**: the authoritative document name segment inside the canonical id (`anthology`, `anchor`, `address_nodes`, `administrative`, `247_17_77_1`, …). Used as the primary workbench/gallery label.
- **raw document name**: the compatibility filename token from disk (`tool.<msn>.cts-gis.json`, `sc.<msn>.msn-address_nodes.json`, …). Preserved as secondary evidence, not as the primary authority label.
- **sandbox source** (`lv.`): an in-sandbox datum document. Includes anchors and non-anchor sources.
- **binary payload** (`stl.`): the compiled hyphae form of a single filament datum. No sandbox segment in the canonical id.
- **cached source** (`cptr.`): the decompiled JSON form of a binary payload. No sandbox segment in the canonical id.
