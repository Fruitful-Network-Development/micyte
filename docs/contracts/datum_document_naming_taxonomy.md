# Datum Document Naming Taxonomy

## Overview

Datum documents are the atomic storage units of the MOS (Mycelial Ontological Schema).
Every datum document has a canonical identifier following a strict naming convention
keyed on file *type* (the prefix), portal owner (`msn_id`), the optional sandbox
the document lives in, the document name, and a content version hash.

This taxonomy applies to **datum content only**. Tool-specific profiles, configuration
files, vault inventories, and other non-datum operational metadata are tracked
separately and are referenced from datum documents through their JSON-unit rudi
datum (`0-0-11`); they do not receive a canonical datum-document name.

## File Type Prefixes

Three prefixes define the datum-document type:

| Prefix | Long form | Type | Content |
|---|---|---|---|
| `lv` | live | Sandbox sources | The system anchor file (`anthology.json`), every tool sandbox anchor (`anchor`), and every other in-sandbox source document. All datum files in a sandbox depend on the sandbox anchor and may reference new datum addresses for abstraction by treating the anchor's datums as branches. |
| `stl` | stale | Binary payloads | The compiled hyphae form of a filament datum, produced by either the local portal or a foreign portal. A binary payload encodes only the minimal abstraction identity (hyphae value) of a single filament datum. |
| `cptr` | capture | Cached sources | The decompiled JSON form of a binary payload. A capture contains every datum abstraction needed to materialize the corresponding filament datum's hyphae value, but it is not itself a sandbox source — it is a cache of the payload's decompiled form. |

## Canonical Name Format

```
lv.<msn_id>.<sandbox>.<name>.<version_hash>
stl.<msn_id>.<name>.<version_hash>
cptr.<msn_id>.<name>.<version_hash>
```

Fields:

- `msn_id` — Portal/owning instance identifier. Example: `1-2-3-4-5-6-7-8-9-0` for the FND portal.
- `sandbox` — Canonical sandbox token. Required for `lv.` documents only. **Uses underscores** (programmatic form). Examples: `system`, `cts_gis`, `fnd_ebi`, `agro_erp`. URL route slugs (`/tools/cts-gis`) are a separate display concern and must not appear in canonical document IDs.
- `name` — Document name. For `lv.` documents the name is `anchor` for every sandbox anchor *except* the system sandbox, where the anchor is named `anthology`. Non-anchor `lv.` documents and all `stl.`/`cptr.` documents use the document's own name (e.g. `247_17_77_1`, `registrar`, `txa`, `natural_entity`).
- `version_hash` — 64-character lowercase hex SHA-256 over the MSS form of the document (policy `mos.mss_sha256_v1`).

`stl.` and `cptr.` documents do not carry a sandbox segment. A binary payload or its
capture is owned by a portal (`msn_id`) but is not constrained to one of that
portal's sandboxes — payloads circulate across sandboxes and across portals through
contracts.

## URL Slug vs Sandbox Token

The sandbox **token** (used in canonical document IDs and programmatic APIs) uses underscores.
The URL **slug** (used in portal routes and filesystem directory names) uses hyphens.
These are two distinct representations of the same sandbox identity.

| URL slug (route / filesystem) | Canonical sandbox token (document ID) |
|-------------------------------|----------------------------------------|
| `/tools/cts-gis`              | `cts_gis`                             |
| `data/sandbox/fnd-ebi/`       | `fnd_ebi`                             |
| `/tools/aws-csm`              | `aws_csm`                             |
| `system` (no slug difference) | `system`                              |

`sandbox_id_for_surface()` in `portal_shell/shell.py` is the authoritative conversion point.
It always returns the underscore token form. Callers must not use the URL slug as a
document filter or document ID component.

## Source Filename to Canonical Name Parsing

Legacy `sc.` source files follow the pattern `sc.<msn_id>.<namespace><semantic>.json`.
The canonical document name is extracted by:

1. Stripping `sc.` and the MSN ID segment.
2. Stripping a recognized namespace marker from the remainder:
   `msn-`, `msn_`, `fnd.`, `cts.`, `registrar.`
3. The remaining `<semantic>` becomes the canonical name (underscores preserved, dots stripped).
4. If the semantic is empty after stripping, the source file is **malformed** — it is
   quarantined and not materialized as a canonical document.

Examples:
- `sc.<msn>.msn-natural_entity.json` → `natural_entity`
- `sc.<msn>.msn_address_nodes.json` → `address_nodes`
- `sc.<msn>.fnd.1-2-3-4-5-6.json` → `1-2-3-4-5-6`
- `sc.<msn>.cts.247_17_77_1.json` → `247_17_77_1`
- `sc.<msn>.sos_voterid.json` → `sos_voterid`
- `sc.<msn>.msn-.json` → **MALFORMED** — quarantined

The parser is `extract_semantic_name_from_sc_stem()` in
`MyCiteV2/packages/core/document_naming/__init__.py`. It is the canonical,
single-function implementation used by the migration script and any future
materialization paths.

## Anchor Naming Rules

- System sandbox anchor: `lv.<msn_id>.system.anthology.<hash>`
- Every other sandbox anchor: `lv.<msn_id>.<sandbox>.anchor.<hash>`
- The names `anchor` and `anthology` are reserved for sandbox anchors. Non-anchor
  documents must not use them.
- Any sandbox anchor file that exists on disk is an authoritative datum document in
  MOS. Tool anchors are not a separate file-authority class.
- Tool sandboxes are not required to mirror the system sandbox starter set. A tool
  sandbox may legitimately contain only its anchor plus the source documents that
  actually exist for that tool.

## Concrete Examples (FND, msn_id `1-2-3-4-5-6-7-8-9-0`)

| Legacy / staging form | Canonical form |
|---|---|
| `anthology.json` | `lv.1-2-3-4-5-6-7-8-9-0.system.anthology.<hash>` |
| `tool.1-2-3-4-5-6-7-8-9-0.cts-gis.json` (CTS-GIS sandbox anchor) | `lv.1-2-3-4-5-6-7-8-9-0.cts_gis.anchor.<hash>` |
| `tool.1-2-3-4-5-6-7-8-9-0.fnd-ebi.json` (FND-EBI sandbox anchor) | `lv.1-2-3-4-5-6-7-8-9-0.fnd_ebi.anchor.<hash>` |
| `sc.1-2-3-4-5-6-7-8-9-0.cts.247_17_77_1.json` (CTS-GIS sandbox source) | `lv.1-2-3-4-5-6-7-8-9-0.cts_gis.247_17_77_1.<hash>` |
| `sc.1-2-3-4-5-6-7-8-9-0.fnd.3-2-3-17.json` (CTS-GIS sandbox source) | `lv.1-2-3-4-5-6-7-8-9-0.cts_gis.3-2-3-17.<hash>` |
| `sc.1-2-3-4-5-6-7-8-9-0.msn-natural_entity.json` | `lv.1-2-3-4-5-6-7-8-9-0.cts_gis.natural_entity.<hash>` |
| `rf.1-2-3-4-5-6-7-8-9-0.txa.json` (Agro-ERP sandbox source) | `lv.1-2-3-4-5-6-7-8-9-0.agro_erp.rf.<hash>` |
| `sc.1-2-3-4-5-6-7-8-9-0.registrar.bin` | `stl.1-2-3-4-5-6-7-8-9-0.registrar.<hash>` |
| `sc.1-2-3-4-5-6-7-8-9-0.registrar.json` | `cptr.1-2-3-4-5-6-7-8-9-0.registrar.<hash>` |

Note the historical `msn-` filename prefix (`msn-natural_entity`, `msn-administrative`) is
**not** carried into the canonical name. The `msn_id` segment of the canonical id already
records portal ownership; the legacy `msn-` filename prefix represented a separate
"convention file" idea that has been retired in favour of starter-portal schema versions
plus an FND-portal contract that delivers the necessary built-in payloads (e.g.
`bin.registrar`).

## Version Hash

The `version_hash` is the SHA-256 of the MSS (Monotonic Structured Serialization) form
of the document under policy `mos.mss_sha256_v1`:

`mss.` is a design-time shorthand for the serialization/hash policy only; it is
not a fourth document prefix. Stored document IDs are limited to the three
canonical prefixes: `lv.`, `stl.`, and `cptr.`.

- The MSS form is the *indiscriminate* inclusion of the complete datum file: every
  row, ordered canonically by `(layer, value_group, iteration)`, with every reference
  datum address materialized in the document.
- Iteration values must be contiguous (no skips). A datum document with skipped
  iterations cannot be written to the database; it must be canonicalized first.
- The hash is computed by
  `MyCiteV2/packages/core/mss/datum_identity.py::compute_mss_hash`.

The MSS form of a single datum row's hyphae value (the minimal abstraction identity
of one filament datum) is what `stl.` payloads encode; the cached source `cptr.` is
the decompiled JSON of the same minimal abstraction set. These are distinct from the
document `version_hash` of an `lv.` sandbox source, which covers the full ordered
file.

## Validation Regex

Document IDs must match:

```
^lv\.[^.]+\.[^.]+\.[^.]+\.[a-f0-9]{64}$
|
^(stl|cptr)\.[^.]+\.[^.]+\.[a-f0-9]{64}$
```

Validation is enforced at the SQL adapter boundary
(`MyCiteV2/packages/adapters/sql/datum_store.py`) and through the
`MyCiteV2/packages/core/document_naming` library. Writes that do not match are
rejected.

## SQL Realization

A single relational table — `documents` — backs this taxonomy. The prefix is
discriminated by a `CHECK (prefix IN ('lv','stl','cptr'))` constraint; `sandbox` is
nullable so that `stl.` and `cptr.` rows can omit it. Refer to
`mos_database_schema_addendum.md` for the schema.

The taxonomy explicitly **does not** decompose into separate tables for SAMRAS
namespaces, HOPS geometry chains, hyphae chains, or staging-promotion maps. Those
concerns belong to the core libraries (`packages/core/samras`, `packages/core/hops`,
`packages/core/datum_editing`, `packages/core/mss`) and the per-row
`hyphae_chain_json` column on `datum_row_semantics`, not to additional relational
schemas.

## Origin (Local vs Foreign)

Every `documents` row carries an `origin` column with values `local` or `foreign`.
Local documents are owned by the operating portal (matching `msn_id`); foreign
documents arrived through a contract with another portal. Update rights for foreign
documents are mediated by the portal-to-portal contract that delivered them.
Contract enforcement is handled by the contracts pipeline; the taxonomy itself only
records the origin.

## MOS Database as Authority

The MOS authority database (`mos_authority.sqlite3`) is the single runtime source of
truth for datum document materialization and naming. The `documents` table is the
canonical index.

The full enforcement contract (allowed/forbidden filesystem usage, the
enforcement test chain, the legacy_alias retirement schedule, and the
sandbox-add procedure) is defined in
[`mos_authority_enforcement.md`](mos_authority_enforcement.md) — that
document is the single binding source for this rule. The taxonomy below
keeps only the naming-shape concerns.

the legacy `hippo` tree is **historical evidence only**. It is not imported by MyCiteV2 at
runtime, it is not a materialization authority for MOS, and it must not influence
document naming, sandbox token resolution, or workbench rendering decisions.

## Migration Status

The migration to canonical `lv./stl./cptr.` IDs is realized through the
`documents` table introduced in 2026-05-05; legacy compatibility keys
(`system:anthology`, `sandbox:<tool>:<filename>.json`) are retained as
`documents.legacy_alias` for one cycle. New writes must produce canonical IDs;
readers accept either form during the cycle.

Sandbox is the parent datum-document grouping below `msn_id`. Canonical local
datum documents therefore resolve as `lv.<msn_id>.<sandbox>.<name>.<hash>`, where
`system` owns the SYSTEM anthology/workbench documents and each tool owns its own
sandbox documents. Readers must reject or clamp attempts to focus a document whose
resolved sandbox does not match the active workbench sandbox.

The raw on-disk filename remains compatibility metadata only. In runtime catalog and
workbench summaries, `document_name` may still carry the source filename
(`tool.<msn>.cts-gis.json`, `sc.<msn>.msn-address_nodes.json`, …), while
`canonical_name` carries the authoritative datum-document name (`anchor`,
`address_nodes`, `administrative`, …).
