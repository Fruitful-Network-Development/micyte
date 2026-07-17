> Status: as-built

[← Overview](00-overview-and-glossary.md)

# L1 Core Engine — the MOS datum-database library

## Purpose

`MyCiteV2/packages/core/` is the **L1 CORE** layer: a lean, store-agnostic
library that defines what a *datum* is, how datum addresses compose into SAMRAS
trees, how a document's content reduces to a single canonical MSS version hash,
how a sandbox is loaded as a `Workbook` and edited by pure composable
operations, and how those edits are compiled into a re-minted, rule-checked
migration plan. It is *pure*: nothing here opens a database, reads a file, or
writes datum state. Persistence is the job of an L2 store executor
(`adapters/sql/datum_workbook_apply.py`); the MOS database is canonical and the
WORKBOOK-YAML codec here is transport-only.

This page is the as-built map of that library and how its pieces fit into the
load → edit → compile → plan → apply round-trip.

## File map

### YAML transport codec (`core/datum_io/`)

| path:line | role | approx LOC |
|---|---|---|
| `MyCiteV2/packages/core/datum_io/codec.py:55` | `to_yaml` / `from_yaml` — one datum document ⇄ conventionalized YAML | 121 |
| `MyCiteV2/packages/core/datum_io/codec.py:97` | `workbook_to_yaml` / `workbook_from_yaml` — a whole sandbox as a multi-sheet WORKBOOK envelope | — |
| `MyCiteV2/packages/core/datum_io/__init__.py:3` | re-exports the codec surface + the two schema constants | 19 |

### Datum-ops manipulation library (`core/datum_ops/`)

| path:line | role | approx LOC |
|---|---|---|
| `MyCiteV2/packages/core/datum_ops/ops.py:43` | `Workbook` (sandbox = named sheets) + `WorkbookDelta` + `apply_sequence` | 172 |
| `MyCiteV2/packages/core/datum_ops/ops.py:105` | row-level ops `InsertRow` / `DeleteRow` / `MoveRow` / `ReorderRow` (delegate to the SQL reorder engine) | — |
| `MyCiteV2/packages/core/datum_ops/node_ops.py:128` | node-address ops `MintNode` / `RelocateNode` / `RepointNode` / `RenameNode` / `DropNode` | 331 |
| `MyCiteV2/packages/core/datum_ops/node_ops.py:262` | cross-sheet primitives `RewriteRefs` / `RecompileMagnitude` / `RebuildCollection` | — |
| `MyCiteV2/packages/core/datum_ops/node_addrs.py:37` | variable-depth SAMRAS node-address algebra (parent/child, contiguous alloc, subtree remap) | 149 |
| `MyCiteV2/packages/core/datum_ops/refs.py:152` | `build_reference_index` — sandbox-wide cross-document node-reference edges + definitions | 176 |
| `MyCiteV2/packages/core/datum_ops/compiler.py:50` | `compile_workbook` — diff baseline vs edited workbook → infer the op sequence | 112 |
| `MyCiteV2/packages/core/datum_ops/migrate.py:82` | `plan_migration` — apply ops, rule-check, re-mint canonical ids, SAMRAS consistency | 148 |
| `MyCiteV2/packages/core/datum_ops/migrate.py:39` | `mint_canonical_id` — re-mint a document id from its fresh MSS hash (idempotent) | — |
| `MyCiteV2/packages/core/datum_ops/rules_loop.py:51` | `check_step` — row-shape + SAMRAS-decode + reference-existence checks (HARD vs advisory) | 84 |
| `MyCiteV2/packages/core/datum_ops/samras_deps.py:43` | `build_magnitude_bitstream` + anchor→source map; SAMRAS-magnitude recompile helpers | 75 |
| `MyCiteV2/packages/core/datum_ops/labels.py:20` | 512-bit ASCII title-label codec (`rf.3-1-2` babelette) | 33 |
| `MyCiteV2/packages/core/datum_ops/workbook.py:16` | `Workbook` ⇄ WORKBOOK-YAML bridge (sheets keyed by canonical name) | 31 |
| `MyCiteV2/packages/core/datum_ops/__init__.py:1` | public API surface for the manipulation library | 85 |

### MSS identity (`core/mss/`)

| path:line | role | approx LOC |
|---|---|---|
| `MyCiteV2/packages/core/mss/datum_identity.py:101` | `compute_mss_hash` — deterministic SHA-256 over sorted rows (the version identity) | 177 |
| `MyCiteV2/packages/core/mss/datum_identity.py:126` | `derive_hyphae_chain` — the `0-0-*` rudi closure for a datum address | — |
| `MyCiteV2/packages/core/mss/canonicalization.py:50` | `canonicalize_iteration_addresses` / `canonicalize_value_group_ordering` — pre-hash row-order invariants | 122 |
| `MyCiteV2/packages/core/mss/__init__.py:1` | re-exports `compute_mss_hash`, `derive_hyphae_chain`, the canonicalizers | 12 |

### Canonical document naming (`core/document_naming/`)

| path:line | role | approx LOC |
|---|---|---|
| `MyCiteV2/packages/core/document_naming/__init__.py:65` | `format_canonical_document_id` — compose `lv.`/`stl.`/`cptr.` ids | 338 |
| `MyCiteV2/packages/core/document_naming/__init__.py:109` | `parse_canonical_document_id` (+ `is_canonical_document_id`) — single validation point | — |
| `MyCiteV2/packages/core/document_naming/__init__.py:238` | `derive_canonical_id_from_legacy` — migrate `system:`/`sandbox:`/`payload:`/`cache:` ids | — |

### SAMRAS structure codec (`core/structures/samras/`)

| path:line | role | approx LOC |
|---|---|---|
| `MyCiteV2/packages/core/structures/samras/structure.py:11` | address-segment algebra (`parse_address_segments`, `parent_address`) + `SamrasStructure` dataclass | 106 |
| `MyCiteV2/packages/core/structures/samras/codec.py:122` | `encode_canonical_structure_from_addresses` / `decode_canonical_bitstream` (unary-width header, stop slices, value stream) | 262 |
| `MyCiteV2/packages/core/structures/samras/codec.py:184` | legacy decoders (fixed-header binary, hyphen payload) for migration | — |
| `MyCiteV2/packages/core/structures/samras/validation.py:33` | `derive_addresses_from_child_counts` / `child_counts_from_addresses` + structure validation | 181 |
| `MyCiteV2/packages/core/structures/samras/mutation.py:1` | tree mutations (`add_child`/`move_branch`/`remove_branch`/`rebuild_structure_from_addresses`) | 259 |
| `MyCiteV2/packages/core/structures/samras/workspace_adapter.py:1` | reconstruct a structure from datum rows; pick a preferred authority row | 377 |

### HOPS coordinate / chronology codec (`core/hops/`, `core/structures/hops/`)

| path:line | role | approx LOC |
|---|---|---|
| `MyCiteV2/packages/core/structures/hops/__init__.py:74` | `classify_hops_coordinate_token` / `decode_hops_coordinate_token` (mixed-radix lon/lat) | 170 |
| `MyCiteV2/packages/core/hops/__init__.py:14` | canonical public HOPS API — re-exports the structures/hops decoders + `assemble_polygon_groups` | 63 |
| `MyCiteV2/packages/core/hops/polygon_groups.py:1` | `assemble_polygon_groups` — spatial chain `4 → 5 → 6 → 7` row-group assembly | 105 |
| `MyCiteV2/packages/core/structures/hops/time_address.py:1` | time-address parse/compare/normalize + projection helpers | 231 |
| `MyCiteV2/packages/core/structures/hops/time_address_schema.py:1` | `decode_mixed_radix_magnitude`, anchor-payload-driven schema | 173 |
| `MyCiteV2/packages/core/structures/hops/chronology.py:1` | `ChronologyAuthority`, `encode_unix_ms_as_hops` / `encode_utc_datetime_as_hops` | 102 |

### Supporting authorities (skim)

| path:line | role | approx LOC |
|---|---|---|
| `MyCiteV2/packages/core/datum_rules/rules.py:92` | `classify_row` / `validate_row` — MOS shape/arity authority (rudi/scalar/pairs/record) | 239 |
| `MyCiteV2/packages/core/datum_refs/refs.py:45` | `parse_datum_ref` / `normalize_datum_ref` — `<msn_id>.<datum_address>` ref grammar | 96 |
| `MyCiteV2/packages/core/datum_templates/__init__.py:1` | archetype templates: scaffold / recognize / column-map for CSV intake | 417 |

## How it works

### Datum address algebra (two distinct address kinds)

The engine carefully distinguishes two hyphen-tuple address spaces that look
alike but mean different things:

* A **datum address** is the 3-segment `layer-value_group-iteration` *row key*
  (e.g. `4-2-17`). It is parsed by `parse_datum_address` — which the core ops
  layer imports *from the SQL adapter* (see Vision-fit). `(layer, value_group)`
  is a row *family*; `ReorderRow` (`ops.py:153`) asserts a move stays inside one
  family.
* A **node address** is a variable-depth position in a SAMRAS tree (e.g. `4`,
  `4-9`, `1-3-2-5-1`), stored as a *magnitude value* inside a row head.
  `core/datum_ops/node_addrs.py` is the parallel algebra for these: every
  segment is a positive integer (`structure.py:11`), so the SAMRAS
  contiguity/root constraints hold by construction. `remove_subtree_remap`
  (`node_addrs.py:94`) and `relocate_subtree_remap` (`node_addrs.py:125`) compute
  the sibling-renumber + re-parent remaps that ride descendants along.

### Rudi datums and the hyphae chain

"Rudi" base datums live at `layer=0, value_group=0` (`0-0-*`); complex datums
abstract them. The full transitive dependency set of a datum is its **hyphae
value**. `derive_hyphae_chain` (`mss/datum_identity.py:126`) walks a datum's
local reference closure and returns the contiguous rudi chain `[0-0-1 .. 0-0-K]`
where `K` is the highest rudi iteration reachable — every position `1..K` is
included even if not directly referenced (mirroring the focus-exclusion idea
that a hyphae is the same machinery as an MSS plus a preprocessing step).

### MSS hash (the version identity)

`compute_mss_hash` (`mss/datum_identity.py:101`) reduces a whole document to a
single deterministic SHA-256: it sorts rows by `(layer, value_group, iteration)`,
serializes `source_kind` + `document_metadata` + each row's `{datum_address, raw}`
with canonical JSON (`sort_keys`, no whitespace), and hashes under the policy
tag `mos.mss_sha256_v1`. By construction it reproduces
`build_document_version_identity` in the SQL adapter
(`adapters/sql/datum_semantics.py:136`). Before hashing, `canonicalization.py`
can repair iteration-skip gaps and order a family by SAMRAS magnitude so the
row order is itself canonical.

### SAMRAS / HOPS codecs

A **SAMRAS magnitude** encodes the *prefix-closure* of a node set as a canonical
bitstream rooted at `0-0-5`. `encode_canonical_structure_from_addresses`
(`samras/codec.py:122`) lays out a unary-coded address-width field, a unary-coded
stop-count-width field, the stop-count, the stop-address array, then the
concatenated minimal-binary value tokens; `decode_canonical_bitstream`
(`codec.py:141`) reverses it and *re-encodes* to assert the input was already
canonical (not merely structurally valid). `samras_deps.build_magnitude_bitstream`
(`samras_deps.py:43`) wraps this with a round-trip address-set assertion so a
sheet's anchor magnitude always matches its defined node set.

**HOPS** is the geospatial/temporal analogue: `decode_hops_coordinate_token`
(`structures/hops/__init__.py:100`) interprets a numeric-hyphen token as a
mixed-radix lon/lat partition (default radices `(8, 81, 100, 100, 100, 100)`),
and the `structures/hops/` time-address helpers do the chronological side. The
`core/hops/` package (`hops/__init__.py:14`) is the thin canonical public
re-export of all of it.

### Document naming

A canonical id is `<prefix>.<msn_id>.[<sandbox>.]<name>.<hash>` where the hash is
the 64-char MSS SHA-256. `lv.` (live datum) ids carry a sandbox segment; `stl.`
(payload) and `cptr.` (cache pointer) ids do not
(`document_naming/__init__.py:65`). `parse_canonical_document_id`
(`__init__.py:109`) is the single validation point the SQL adapters call before
persisting. Note the *id is not part of the hashed content*, so re-minting an
unchanged document yields the same id (idempotent).

### The datum_ops round-trip (load → edit → compile → plan → apply)

1. **Load** — the L2 executor's `load_workbook`
   (`adapters/sql/datum_workbook_apply.py:36`) hydrates a sandbox into a pure
   `Workbook` (or `datum_ops/workbook.py:28` reconstructs one from WORKBOOK YAML).
2. **Edit** — UI/tools hand back edited YAML; no op grammar required.
3. **Compile** — `compile_workbook` (`compiler.py:50`) diffs baseline vs edited,
   tracks node identity by *title*, and infers `RelocateNode` / `RenameNode` /
   `MintNode` / `DropNode`, then appends the housekeeping cascade
   (`RecompileMagnitude` + `RebuildCollection`) in exactly the order
   `plan_migration` expects.
4. **Apply ops (pure)** — `apply_sequence` (`ops.py:85`) threads each op's
   `WorkbookDelta` forward so the next op sees prior edits. Ops are frozen
   dataclasses returning deltas; node-address ops cascade across *every* sheet
   that references a moved node via `build_reference_index` (`refs.py:152`).
5. **Plan** — `plan_migration` (`migrate.py:82`) runs the op sequence over the
   baseline, runs `check_step` (HARD issues abort), asserts each anchor SAMRAS
   magnitude exactly matches its source sheet's node set, re-mints each *touched*
   sheet's canonical id from its fresh MSS hash, and returns a `MigrationPlan`
   (touched sheets, write order, verify expectations, advisories). "Touched"
   means the content hash changed — not merely a stale stored id.
6. **Apply (store)** — the executor (`adapters/sql/datum_workbook_apply.py:103`
   `execute_migration`) backs up, writes in `write_order`, and verifies against
   the plan's row-count/SAMRAS expectations.

### The YAML transport codec

`datum_io/codec.py` is transport-only: `to_yaml`/`from_yaml` round-trip one
document carrying `source_kind`, `document_metadata`, and every row's
`{address, raw}` verbatim — so the MSS version identity is preserved across a
round-trip. `workbook_to_yaml`/`workbook_from_yaml` do the same for a whole
sandbox (multi-sheet envelope). Nothing here writes to disk; the MOS DB is
canonical (the MOS-only datum storage rule).

## Vision-fit

| Aspect | Status | Notes |
|---|---|---|
| Datum address `<layer>-<vg>-<iteration>` + node-address algebra | Implemented | `node_addrs.py`, `parse_datum_address` |
| Rudi (`0-0-*`) + hyphae transitive closure | Implemented | `derive_hyphae_chain` (`datum_identity.py:126`) |
| MSS canonical single-sequence hash | Implemented | `compute_mss_hash` (`datum_identity.py:101`) |
| SAMRAS canonical bitstream (address-width / bitmap / stop slices / value stream) | Implemented | `samras/codec.py` |
| HOPS coordinate + chronology codec | Implemented | `core/hops/`, `core/structures/hops/` |
| Document title `<type>.<msn>.<sandbox>.<name>.<hash>` | Implemented | `document_naming/__init__.py` |
| Pure load→edit→compile→plan→apply round-trip | Implemented | `datum_ops/` + L2 executor |
| WORKBOOK-YAML transport codec | Implemented | `datum_io/` (transport only, MOS canonical) |
| MSS *form* carrying >1 top-level datum / explicit focus-exclusion hyphae preprocessing | Partial | a document carries many rows; `compute_mss_hash` hashes the whole document. `derive_hyphae_chain` returns the rudi chain but there is no standalone "focus-exclusion preprocessing" entry point in `core/` — it is folded into the closure walk. |
| Canonical datum compiling its MSS along the *minimum-but-complete abstraction path* | Partial | the abstraction path is implied by the reference closure; there is no single `core/` function named for the minimum-but-complete path (the hyphae walk is the closest realization). |
| `core/` as the authoritative address/MSS engine | Absent / inverted | the *real* engine lives in the L2 adapter — see Open questions. |

## Open questions

* **Core → adapter inversion.** The supposed L1 address/hyphae/MSS engine is
  actually `MyCiteV2/packages/adapters/sql/datum_semantics.py` (663 LOC). Core
  modules import the primitive parsers *from the adapter*:
  `core/datum_ops/ops.py:24` and `core/datum_ops/node_ops.py:17` both import
  `parse_datum_address` (and `ops.py` also imports `preview_document_insert` /
  `preview_document_delete` / `preview_document_move`) from
  `adapters.sql.datum_semantics`. That is a layering inversion — L1 depends on
  L2. This is flagged for resolution in
  [`05-engineering-standards.md`](05-engineering-standards.md) and
  [`60-canonical-datum-and-hyphae-flags.md`](60-canonical-datum-and-hyphae-flags.md).
* **Duplicated MSS implementation.** `core/mss/datum_identity.py:compute_mss_hash`
  is a near-duplicate of the adapter's `build_document_version_identity`
  (`datum_semantics.py:136`); both are documented as intentionally producing the
  same hash. The core copy *is* used on the live path (`migrate.py:20`,
  `datum_io/codec.py`, two SQL adapters), but its sibling `derive_hyphae_chain`
  is consumed only by `state_machine/portal_shell/tool_eligibility.py:21` and the
  unit tests (`tests/unit/test_datum_identity_core.py`). Which copy is canonical,
  and whether the adapter should delegate to core (the correct direction), is the
  open design question.
* **Hardcoded agro_erp contract in `samras_deps.py`.** The anchor→source map
  (`ANCHOR_SAMRAS_SOURCE` = `{1-1-1: txa, 1-1-5: lcl}`), the `5-0-1` id-collection
  address, and the `NODE_REF_MARKERS` (`refs.py:44`, `rf.3-1-1`/`rf.3-1-5`) are
  the agro_erp reference design hardwired into the library. Both modules note
  this is "deferred: derive per sandbox" — generalizing it is unresolved.
* **`compiler.py` does not infer pure re-points.** A reference re-point with no
  node move is only expressible via the explicit `RepointNode` / `RewriteRefs`
  primitives — the inference scope is definition-structure edits only.
