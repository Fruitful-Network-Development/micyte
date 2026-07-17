# MiCyte Portal — Overview & Glossary

> Status: as-built

This is the front door of the MiCyte development wiki. It states the portal's
mission, maps the as-built layered architecture onto real package paths, indexes
every other wiki page, defines the shared vocabulary, and records the
page-template conventions the rest of the wiki follows. Every code reference here
was read before it was cited; code paths are given as `path:line` and resolve on
disk. Sibling wiki pages are linked even where they are not yet merged — those
are intentional forward references.

---

## 1. Mission

MiCyte Portal (`MyCiteV2/`) is a hexagonal Python stack that turns a
single ontological datum-database — the **MOS** (Mycelial Ontological Schema) —
into a document-processor-style workspace. Datums are addressed
`<layer>-<value_group>-<iteration>`; primitive "rudi" datums (`0-0-*`) are the
alphabet, and complex datums abstract them, so the full transitive dependency set
of any datum (its **hyphae value**) is itself a citable identity. The portal is
organized into clean layers: a lean datum-database core (L1), a surface that
persists datum documents into MOS in canonical single-sequence form (L2), and a
UI that loads those documents as runtime workbooks and lets modular tools and
lenses operate on them (L3). The near-term goal is to make tools and lenses bind
to recognized datum families and hyphae flags; the longer-term goal is a
networked, contract-driven federation of portals coordinated by a published
registry, eventually packaged as a desktop app with a local database.

---

## 2. Layered model map

The four conceptual layers, the two cross-cutting concerns (tools/lenses), and
the stubbed future-network tier, each annotated with the real package paths that
implement (or scaffold) them. All paths below exist on disk.

```
                         MyCiteV2/  (hexagonal Python stack)
 ┌───────────────────────────────────────────────────────────────────────────┐
 │ L3 UI — runtime shell, workbook materialization, panels                     │
 │   packages/state_machine/portal_shell/   (shell composition, tool eligibility)
 │   packages/tools/workbench_ui/           (READ path: SQL → JSON projection)  │
 │   instances/_shared/portal_host/         (app.py, templates, static JS)      │
 │   instances/_shared/runtime/             (WRITE path: workbook → MOS-save)    │
 ├───────────────────────────────────────────────────────────────────────────┤
 │ L2 SURFACE — datum-document persistence, MSS form, canonical naming         │
 │   packages/adapters/sql/datum_semantics.py  (the real address/hyphae/MSS engine)
 │   packages/adapters/sql/                  (SQLite-backed MOS adapter)         │
 │   packages/core/document_naming/          (canonical lv./stl./cptr. doc IDs) │
 ├───────────────────────────────────────────────────────────────────────────┤
 │ L1 CORE — lean MOS datum library: addresses, rudis, hyphae, structures      │
 │   packages/core/mss/                      (datum_identity: hyphae chain)      │
 │   packages/core/datum_ops/                (ops/node_ops, workbook codec)      │
 │   packages/core/datum_io/                 (WORKBOOK-YAML codec, transport)    │
 │   packages/core/structures/samras/        (SAMRAS structural model)          │
 │   packages/core/structures/hops/          (HOPS coordinate decode)           │
 │   packages/ports/datum_store/             (authoritative datum-doc port)      │
 ├───────────────────────────────────────────────────────────────────────────┤
 │ ⟂ CROSS-CUT: TOOLS & LENSES                                                  │
 │   packages/state_machine/portal_shell/tool_eligibility.py (tool ↔ hyphae)    │
 │   packages/state_machine/lens/registry.py (lens ↔ family / value_kind)       │
 │   instances/_shared/portal_host/static/v2_portal_tool_palette.js (menu-bar)  │
 ├───────────────────────────────────────────────────────────────────────────┤
 │ ⌛ FUTURE NETWORK (stubbed — 1-LOC inert scaffolds today)                     │
 │   packages/core/crypto/                   (asymmetric/symmetric key material)│
 │   packages/modules/domains/contracts/     (Manager/Subordinate contracts)    │
 │   packages/modules/domains/reference_exchange/ (resource sharing)            │
 │   packages/sandboxes/orchestration/, packages/sandboxes/system/              │
 │   packages/state_machine/mediation_surface/                                  │
 │   packages/tools/_shared/                                                    │
 │   packages/core/network_root_surface_query.py (network read-model query norm)│
 └───────────────────────────────────────────────────────────────────────────┘
```

Two as-built facts to keep in mind while reading the rest of the wiki (both are
covered in depth in the delta map):

- **core→adapter inversion.** The real address/hyphae/MSS engine lives in the
  *adapter* layer (`MyCiteV2/packages/adapters/sql/datum_semantics.py`, 663 LOC,
  importing only `ports/datum_store`), and `core/datum_ops` imports *up* into it
  (`MyCiteV2/packages/core/datum_ops/ops.py:24`,
  `MyCiteV2/packages/core/datum_ops/node_ops.py:17`). A near-duplicate identity
  helper in `MyCiteV2/packages/core/mss/datum_identity.py` is used only by
  `tool_eligibility.py` and tests.
- **materialization split.** The WORKBOOK-YAML codec
  (`MyCiteV2/packages/core/datum_io/codec.py`,
  `MyCiteV2/packages/core/datum_ops/workbook.py`, both explicitly "transport
  only") drives the **write** path
  (`MyCiteV2/instances/_shared/runtime/portal_datum_workbench_mutation_runtime.py`),
  while the **read** path projects SQL straight to JSON
  (`MyCiteV2/packages/tools/workbench_ui/service.py`).

---

## 3. Reading order / Table of contents

Read top to bottom for a first pass; jump by area afterward. Every link below is
a sibling wiki page produced by this batch — some may not be merged yet (forward
references are expected).

**Standards**
- [`05-engineering-standards.md`](05-engineering-standards.md) — coding/doc standards for this codebase.

**As-built architecture (what exists today)**
- [`10-l1-core-engine.md`](10-l1-core-engine.md) — L1 CORE: the MOS datum-database library.
- [`20-l2-surface-persistence.md`](20-l2-surface-persistence.md) — L2 SURFACE: datum-document persistence in MSS form.
- [`30-l3-shell-runtime-ui.md`](30-l3-shell-runtime-ui.md) — L3 UI: shell, runtime, workbook materialization.
- [`40-tools-and-lenses-asbuilt.md`](40-tools-and-lenses-asbuilt.md) — tools & lenses as they bind today.
- [`50-delta-map.md`](50-delta-map.md) — gap map: target architecture vs. as-built (inversion, split, stubs).

**Design specs (the model the code is converging on)**
- [`60-canonical-datum-and-hyphae-flags.md`](60-canonical-datum-and-hyphae-flags.md) — canonical datums and the hyphae-flag mechanism.
- [`61-mss-and-hyphae-form-spec.md`](61-mss-and-hyphae-form-spec.md) — MSS form and hyphae-form encoding spec.
- [`70-yaml-materialization-pipeline.md`](70-yaml-materialization-pipeline.md) — the WORKBOOK-YAML materialization pipeline.

**How-to guides**
- [`80-tool-authoring-guide.md`](80-tool-authoring-guide.md) — authoring a tool.
- [`81-lens-authoring-guide.md`](81-lens-authoring-guide.md) — authoring a lens.
- [`82-demo-sandbox-cookbook.md`](82-demo-sandbox-cookbook.md) — building a demo sandbox end-to-end.

**Future / roadmap**
- [`90-network-contract-architecture.md`](90-network-contract-architecture.md) — network, keys, Manager/Subordinate contracts, registry.
- [`95-desktop-app-local-db.md`](95-desktop-app-local-db.md) — desktop app with a local DB.
- [`99-roadmap.md`](99-roadmap.md) — sequencing and milestones.

**Pre-existing orientation (already in the repo)**
- [`README.md`](README.md) — what the wiki family is for.
- [`separation_and_responsibility.md`](separation_and_responsibility.md) — cross-repo ownership boundaries.
- [`../README.md`](../README.md) — the docs root and documentation families.

---

## 4. Glossary

Terms are grounded in the codebase or in the canonical contracts; citations point
to where the concept is implemented or specified. Where this wiki and
[`../contracts/portal_vocabulary_glossary.md`](../contracts/portal_vocabulary_glossary.md)
overlap, the contract is canonical — this glossary is orientation.

- **datum** — the atomic unit of meaning in MOS. A datum is one row in a datum
  document, carrying a `datum_address`, a `raw` payload, and references to other
  datums. Rows are modeled by `AuthoritativeDatumDocumentRow` in
  `MyCiteV2/packages/ports/datum_store/` and processed throughout
  `MyCiteV2/packages/adapters/sql/datum_semantics.py`.

- **datum address** — the `<layer>-<value_group>-<iteration>` triple identifying a
  datum (e.g. `0-0-1`, `3-1-4`). Parsing/formatting/sort-key helpers live in
  `MyCiteV2/packages/core/mss/datum_identity.py:34` (`_parse_datum_address`) and
  the adapter engine `MyCiteV2/packages/adapters/sql/datum_semantics.py:18`
  (`_DATUM_ADDRESS_RE`).

- **rudi datum** — a primitive base datum at `layer=0, value_group=0`
  (`0-0-*`). Rudis are the alphabet that complex datums abstract; the hyphae chain
  is expressed entirely in rudi addresses. See the `(0, 0)` test in
  `MyCiteV2/packages/core/mss/datum_identity.py:163` (`rudi_in_doc`).

- **hyphae value** — the full transitive dependency closure of a datum, expressed
  as its rudi chain. `derive_hyphae_chain` returns `[0-0-1, ..., 0-0-K]`, where K
  is the highest rudi iteration reachable in the closure, including every position
  in between — `MyCiteV2/packages/core/mss/datum_identity.py:126`. This is the
  identity a tool can bind against.

- **MSS form** (Mycelial Single-Sequence) — the canonical single-sequence encoding
  of one or more top-level datums (address size, bitmap, start/stop slices). MSS
  hashing and the `mos.mss_sha256_v1` version policy are in
  `MyCiteV2/packages/adapters/sql/datum_semantics.py:14` and
  `compute_mss_hash` at `MyCiteV2/packages/core/mss/datum_identity.py:101`. See
  [`61-mss-and-hyphae-form-spec.md`](61-mss-and-hyphae-form-spec.md).

- **hyphae form** — the same MSS machinery plus a preprocessing step that excludes
  datums outside the current focus, so the sequence carries only the focused
  datum and its dependencies. Spec'd in
  [`61-mss-and-hyphae-form-spec.md`](61-mss-and-hyphae-form-spec.md); the hyphae
  chain it relies on is `derive_hyphae_chain`
  (`MyCiteV2/packages/core/mss/datum_identity.py:126`).

- **SAMRAS** — the pure structural model for breadth-first child-count magnitude
  trees: canonical encode/decode, address derivation, round-trip validation, and
  mutation helpers, with no presentation logic. Owned by
  `MyCiteV2/packages/core/structures/samras/` (see its
  [`README.md`](../../MyCiteV2/packages/core/structures/samras/README.md) and
  `structure.py`). Canonical contracts:
  [`../contracts/samras_structural_model.md`](../contracts/samras_structural_model.md).

- **HOPS** — bounded mixed-radix coordinate decoding promoted for the read-only
  CTS-GIS slice; it deliberately does not revive the broader legacy HOPS stack.
  Owned by `MyCiteV2/packages/core/structures/hops/` (see its
  [`README.md`](../../MyCiteV2/packages/core/structures/hops/README.md),
  `time_address.py`, `chronology.py`).

- **sandbox** — a named workspace grouping a set of datum documents. The sandbox
  segment is part of a `lv.` document ID and is required for `lv.` docs and
  forbidden for `stl.`/`cptr.` docs —
  `MyCiteV2/packages/core/document_naming/__init__.py:95`. The tool palette also
  exposes per-sandbox tool discovery (`fetchForSandbox` in
  `MyCiteV2/instances/_shared/portal_host/static/v2_portal_tool_palette.js:79`).

- **datum document** — a persisted collection of datum rows in MSS form, one
  document per logical doc, modeled by `AuthoritativeDatumDocument` in
  `MyCiteV2/packages/ports/datum_store/`. Canonical document IDs follow
  `<prefix>.<msn_id>[.<sandbox>].<name>.<hash>` —
  `MyCiteV2/packages/core/document_naming/__init__.py:65`
  (`format_canonical_document_id`). The MOS database is the canonical store;
  on-disk YAML is transport only. Taxonomy:
  [`../contracts/datum_document_naming_taxonomy.md`](../contracts/datum_document_naming_taxonomy.md).

- **WORKBOOK-YAML / workbook** — the human-readable, multi-sheet YAML rendering of
  a sandbox's datum documents that L3 tools, lenses, and the UI consume at
  runtime. It is explicitly a TRANSPORT format only — never a persistence store —
  per the module docstrings at
  `MyCiteV2/packages/core/datum_io/codec.py:1` and
  `MyCiteV2/packages/core/datum_ops/workbook.py:5`. The write path compiles an
  edited workbook back into a MOS migration
  (`MyCiteV2/instances/_shared/runtime/portal_datum_workbench_mutation_runtime.py:488`).
  See [`70-yaml-materialization-pipeline.md`](70-yaml-materialization-pipeline.md).

- **lens** — a bounded presentation transform that changes how a recognized datum
  value is displayed (e.g. nominal ASCII text instead of raw binary magnitude),
  without changing stored data. Lenses resolve by family / value_kind / overlay in
  `MyCiteV2/packages/state_machine/lens/registry.py:25` (`DatumLensRegistry`).
  See [`81-lens-authoring-guide.md`](81-lens-authoring-guide.md).

- **tool** — a modular function bound to a datum's archetype / source_kind, surfaced
  from the menu-bar search and added to the interface panel. Eligibility is
  computed by `recognize_applicable_tools`
  (`MyCiteV2/packages/state_machine/portal_shell/tool_eligibility.py:64`), with the
  archetype set widened via the hyphae chain. The palette UI calls
  `GET /portal/api/tools/eligible`
  (`MyCiteV2/instances/_shared/portal_host/static/v2_portal_tool_palette.js:40`).
  Canonical contract:
  [`../contracts/tool_operating_contract.md`](../contracts/tool_operating_contract.md).
  See [`80-tool-authoring-guide.md`](80-tool-authoring-guide.md).

- **archetype** — a token classifying a datum document or row, used as the binding
  surface for tools. Derived from `document_metadata.archetype` and from per-row
  `archetype` tokens reached through the hyphae chain —
  `MyCiteV2/packages/state_machine/portal_shell/tool_eligibility.py:36`
  (`_row_archetype`) and `:44` (`_document_archetype_set`).

- **msn_id** — the MOS sequence-name identifier embedded in a canonical document
  ID. It must be non-empty and contain no `.` —
  `MyCiteV2/packages/core/document_naming/__init__.py:82`. It is the stable handle
  in the `<prefix>.<msn_id>.…` naming scheme.

- **contact card** — (future) the public card a portal advertises, declaring what
  is requestable plus the portal's public key. The supporting network read-model
  query normalizer exists at
  `MyCiteV2/packages/core/network_root_surface_query.py`; the contract surface is
  the stubbed `MyCiteV2/packages/modules/domains/contracts/` package
  (currently a 1-LOC inert scaffold). See
  [`90-network-contract-architecture.md`](90-network-contract-architecture.md).

- **contract (Manager / Subordinate)** — (future) an asymmetric-key agreement with
  a time-bounded symmetric key. The **Manager** defines the YAML template files and
  the base MSS document; the **Subordinate** fills the empty datum fields and
  recompiles the MSS. Contracts enable resource sharing, and every portal defaults
  to a Subordinate contract with the FND portal. Scaffolded at
  `MyCiteV2/packages/modules/domains/contracts/`,
  `MyCiteV2/packages/modules/domains/reference_exchange/`, and
  `MyCiteV2/packages/core/crypto/` (all inert today). See
  [`90-network-contract-architecture.md`](90-network-contract-architecture.md).

- **msn_registry** — (future) the DNS-like MSS file the FND portal publishes so
  portals can discover one another's contact cards. Not yet implemented; specified
  in [`90-network-contract-architecture.md`](90-network-contract-architecture.md).

- **flag** — the mechanism by which a compiled-hyphae match against a registered
  value "raises a flag" that binds a lens or tool. Today binding is approximated by
  archetype/source_kind widening in
  `MyCiteV2/packages/state_machine/portal_shell/tool_eligibility.py` and by
  family/value_kind matching in
  `MyCiteV2/packages/state_machine/lens/registry.py`; there is no first-class
  hyphae-flag primitive yet. The target design is specified in
  [`60-canonical-datum-and-hyphae-flags.md`](60-canonical-datum-and-hyphae-flags.md).

---

## 5. Page-template conventions

The wiki uses three page archetypes. Future contributors should match whichever
fits the page's intent so the corpus stays consistent. All three open with a
`> Status:` line and (except this hub) a back-link to this overview.

### As-built pages
Describe what exists in the code *today*.
- First line: `> Status: as-built`.
- Second line: a back-link, e.g. `[← Overview](00-overview-and-glossary.md)`.
- Every claim about behavior cites real code as `path:line`, read before citing.
- Call out divergences from the target model rather than smoothing them over;
  cross-link [`50-delta-map.md`](50-delta-map.md) for the full gap list.

### Design-spec pages
Describe the model the code is converging on (not necessarily built yet).
- First line: `> Status: design-spec`.
- Back-link to this overview.
- Clearly separate "target" from "as-built today", and link the relevant as-built
  page so readers can see the gap.
- Normative `must`/`required` claims belong in `docs/contracts/`; spec pages link
  to the contract rather than restating it (per
  [`../standards/documentation_style_guide.md`](../standards/documentation_style_guide.md)).

### How-to pages
Step-by-step guides for a concrete task (authoring a tool/lens, building a demo).
- First line: `> Status: how-to`.
- Back-link to this overview.
- Ordered steps, each runnable or copy-pasteable; reference real files/endpoints.
- Point readers at the matching as-built and spec pages for background.

Shared rules for all pages: prefer the canonical terms from
[`../contracts/portal_vocabulary_glossary.md`](../contracts/portal_vocabulary_glossary.md);
keep normative content in contracts (this wiki is orientation, per
[`README.md`](README.md)); links to code files must resolve on disk, while links
to sibling wiki pages may be forward references.
