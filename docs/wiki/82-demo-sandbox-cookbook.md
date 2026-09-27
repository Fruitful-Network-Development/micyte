# Demo Datum-Document Sandbox Cookbook

> Status: how-to
>
> [← Overview](00-overview-and-glossary.md)
>
> Rewritten 2026-08-23. It was marked `stale` because every step walked
> `bootstrap_fnd_csm_anchor.py` — deleted 2026-07-12 (`e9942b86`) when FND-CSM was
> retired, so seven of this page's citations pointed into a file that had not existed for
> six weeks. The MOS teaching underneath was correct throughout; only the worked example
> had died. It now walks scripts that exist, and opens with where a sandbox is actually
> made today: `provision_instance.py`.
>
> (The dead script is named without its directory on purpose. It is prose about a file
> that used to be cited here, not a citation — `test_wiki_is_combed` checks that every
> cited PATH resolves, and a path that cannot is exactly what this rewrite removed.)

## Goal

Teach you how to stand up a **demo datum-document sandbox** end-to-end so you
have a stable corpus to develop tools and lenses against. By the end you will be
able to:

1. Pick an `msn_id` and a sandbox token.
2. Author an **anchor** datum document (the SAMRAS primitive units + the
   abstraction/babelette rows that source rows reference).
3. Author one or more **source** datum documents whose rows point back at the
   anchor's reference rows.
4. Compute canonical `document_id`s and MSS version hashes, then persist
   everything into the MOS authority database via a small bootstrap script.
5. Verify the sandbox shows up in the portal and is eligible for tools/lenses.

This page teaches the **pattern**. It does not create a real sandbox — follow
the recipe in your own bootstrap script.

## Prerequisites

You should understand three things before writing a bootstrap script.

### 1. The MOS authority database

Datum **documents** live in the MOS sqlite authority file
(`private/mos_authority.sqlite3`), reached through the
`SqliteSystemDatumStoreAdapter`. Bootstrap scripts open it directly:

```python
from micyte.adapters.sql import SqliteSystemDatumStoreAdapter

store = SqliteSystemDatumStoreAdapter(authority_db, allow_legacy_writes=False)
```

See the construction with `allow_legacy_writes=False` in
[`fnd_app/scripts/bootstrap_agro_erp_anchor.py`](../../fnd_app/scripts/bootstrap_agro_erp_anchor.py),
and the shared read/write accessor the portal's tool-discovery routes use,
[`fnd_app/instances/_shared/datum_store_accessor.py`](../../fnd_app/instances/_shared/datum_store_accessor.py).

### 2. The document model

A datum document is an `AuthoritativeDatumDocument`, a frozen dataclass defined
in `micyte/ports/datum_store/contracts.py:123`. The fields you set in
a bootstrap are:

- `document_id` — the canonical id (computed; see below).
- `source_kind` — must be `"sandbox_source"` for a sandbox document (validated
  at `micyte/ports/datum_store/contracts.py:151`; the only other
  legal value is `"system_anthology"`).
- `document_name`, `relative_path`, `canonical_name`, `tool_id` — descriptive
  metadata; `tool_id` conventionally carries the sandbox token.
- `is_anchor` — `True` for the anchor document, `False` for source documents.
- `document_metadata` — a JSON dict; this is where tool/lens eligibility hints
  live (see [Attaching tools/lenses](#attaching-toolslenses)).
- `rows` — a tuple of `AuthoritativeDatumDocumentRow`
  (`micyte/ports/datum_store/contracts.py:89`). Each row carries a
  `datum_address` (e.g. `0-0-1`, `1-1-1`, `4-2-7`) and a `raw` JSON value (the
  list-of-lists cell payload).

The `document_id` form is
`lv.<msn_id>.<sandbox>.<name>.<version_hash>` for sandbox (`lv.`) documents. The
regex and the formatter that enforce it live in
`micyte/core/document_naming/__init__.py:21` (`_LV_RE`) and
`micyte/core/document_naming/__init__.py:65`
(`format_canonical_document_id`). The `<version_hash>` is a 64-char lowercase
hex SHA-256 over the document's MSS form.

### 3. The MOS-only storage rule

Datum **documents** are canonical only in the MOS sqlite authority — never as
loose JSON files. (Extension state, like newsletter or PayPal state, is a
different concern and lives as JSON under `instances/`; do not confuse it with
datum documents.) The adapter actively refuses non-canonical document ids on
write: see `store_authoritative_catalog` raising `NonCanonicalDocumentIdError`
at `micyte/adapters/sql/datum_store.py:203`, and the same guard on
the single-document path at
`micyte/adapters/sql/datum_store.py:331`.

## Step-by-step

The whole pattern is: build rows → wrap them in a document with a *placeholder*
id → compute the real hash → rebuild the document with the *real* id → persist.

### 1. Pick an `msn_id` and a sandbox name

Choose the portal's MSN id for your tenant — your entity's own node in the
registrar (resolved there, never hand-picked) — and a sandbox token. Tokens are programmatic
underscore form — `agro_erp`, `fnd_csm` — not URL-slug form. See the
slug→token normalisation in
[`micyte/core/document_naming/__init__.py`](../../micyte/core/document_naming/__init__.py)
(`_sanitize_sandbox_token`, which maps `cts-gis` → `cts_gis`).

### 2. Define the anchor datum document and its rudi / abstraction rows

The anchor defines the abstraction base every source row depends on. Build it
in layers, by `datum_address`:

- **Rudi / primitive rows** (`0-0-K`) — the SAMRAS unit primitives. Every
  sandbox reuses the same primitive layer; copy it verbatim from `PRIMITIVE_ROWS` in
  [`fnd_app/scripts/bootstrap_agro_erp_anchor.py`](../../fnd_app/scripts/bootstrap_agro_erp_anchor.py)
  (line 68), applied at line 137. Each is `raw=[[address, "~", "0-0-0"], [label]]`.
  There are **twelve** as of 2026-08-23: `0-0-12 octet` joined for the `artifact`
  datum type, and it is in every one of the 14 live anchors because the rudi set is
  REPLICATED per anchor rather than referenced from one place. These rudi rows are what
  `derive_hyphae_chain` walks to build a datum's hyphae chain
  (`micyte/core/mss/datum_identity.py:55`) — the "hyphae values"
  your tools key off.
- **Magnitude rows** (`1-1-K`) — a named magnitude over a primitive (e.g.
  `["1-1-2", "0-0-6", "256"]`, labelled `nominal-bacillete-256`).
- **Abstraction rows** (`2-0-K` / `2-1-K`) — abstraction spaces built on a
  magnitude.
- **Babelette rows** (`3-1-K`) — the reference targets (`rf.3-1-1`, `rf.3-1-2`,
  …) that source rows point at.

The AGRO-ERP anchor builds all four layers in `_build_anchor_rows`,
[`fnd_app/scripts/bootstrap_agro_erp_anchor.py`](../../fnd_app/scripts/bootstrap_agro_erp_anchor.py)
(line 135).

A minimal anchor ships only the primitive layer and grows its reference rows later. The
one that used to illustrate that was FND-CSM's, deleted with the tool; the living example
is the channel reference anchor built by
[`fnd_app/scripts/bootstrap_channel_sandbox.py`](../../fnd_app/scripts/bootstrap_channel_sandbox.py),
which is deliberately BARE — and the reason is worth reading before you copy it. A channel
refuses to open a session without a price datum, and the obvious fix is to hand-add a
`3-1-21` row. That is wrong twice: the fiat datum is a THREE-row chain matched
structurally, not one row, and a guessed row makes the real provisioner REFUSE the address
as already meaning something else. Leave the anchor bare and let
`provision_fiat_datum.py` mint the chain.

### 3. Author the source datum documents

Source rows live in higher value-groups and reference the anchor's babelette
rows. For example, AGRO-ERP's taxonomy rows are 4-2-N four-tuples
`[key, "rf.3-1-1", node_addr, "rf.3-1-2", binary_title]` plus a `5-0-1`
collection naming the full id set — see `_build_txa_rows`,
[`fnd_app/scripts/bootstrap_agro_erp_anchor.py`](../../fnd_app/scripts/bootstrap_agro_erp_anchor.py)
(line 173). Keep your source document
`is_anchor=False`.

### 4. Compute canonical ids and MSS hashes (the two-pass pattern)

The id contains the hash, but the hash is computed over the document — so you
build twice:

1. Build a candidate `AuthoritativeDatumDocument` with a **placeholder** hash of
   64 zeros (`"0" * 64`) so the id passes validation.
2. Run `compute_mss_hash(candidate)`
   (`micyte/core/mss/datum_identity.py:101`); it returns
   `{"policy", "version_hash", "canonical_payload"}`. Strip the leading
   `sha256:` from `version_hash`.
3. Re-`format_canonical_document_id(...)` with the real hash and rebuild the
   document with that id.

This exact dance is the model — see the reusable `_build_document` helper in
[`fnd_app/scripts/bootstrap_agro_erp_anchor.py`](../../fnd_app/scripts/bootstrap_agro_erp_anchor.py)
(line 199), and `document()` in
[`fnd_app/tests/_store_fixtures.py`](../../fnd_app/tests/_store_fixtures.py), which does
the same two passes in eight lines and is the shortest version of it in the tree. Because the hash is
deterministic over sorted rows + metadata
(`micyte/core/mss/datum_identity.py:105`), the same inputs always
produce the same id — that is what makes re-running idempotent.

### 5. Persist via the store adapter

Two supported write paths:

- **Whole-catalog append** — read the existing catalog, append your new
  document, and call `store_authoritative_catalog`
  (`micyte/adapters/sql/datum_store.py:182`). Simple, and it rewrites every
  document's semantics — which is why nothing bulk uses it any more. **It also now
  REFUSES a non-`lv.` prefix**: the catalog is read whole on every authoritative read,
  so a binary payload there is paid for by every reader (`NonCatalogPrefixError`).
- **Single-document swap** — `replace_single_document_efficient`
  (`micyte/adapters/sql/datum_store.py:296`) swaps exactly one
  document (or appends if `prior_document_id` is `None`) and only re-encodes
  that document's rows. AGRO-ERP uses it at
  `fnd_app/scripts/bootstrap_agro_erp_anchor.py:347` to avoid a memory spike on
  large catalogs.

Both paths invalidate the in-memory catalog caches on write
(`micyte/adapters/sql/datum_store.py:293`).

### 6. Verify in the portal

After persisting, confirm the document is discoverable. The palette runtime
reads the catalog and lists eligible tools/visualizers per sandbox:
`build_sandbox_visualizers_response`
(`fnd_app/instances/_shared/runtime/portal_palette_runtime.py:169`) scans every
document in your sandbox and `_doc_sandbox` extracts the sandbox token from
`document_id` parts (`fnd_app/instances/_shared/runtime/portal_palette_runtime.py:144`).
If your document appears in `documents` for `sandbox_id=<your token>`, it
loaded correctly.

## The short way: `provision_instance.py`

Everything below this line is how a sandbox is built by hand, and it is worth reading
because it is what the provisioner does. But **you almost certainly should not do it by
hand**, and the reason is not convenience.

[`fnd_app/scripts/provision_instance.py`](../../fnd_app/scripts/provision_instance.py)
reads an `instance.yaml` and converges it: farm-shaped and channel-shaped sandboxes,
their anchors, their local domains, the registrar rows they declare as sources. Dry run by
default, `VACUUM INTO` backup before any write, and it fails loudly on a step that returns
a not-OK status.

That last property is there because of what happened without it. Three stacked defects sat
in both sandbox bootstraps for eight days — a default reference naming a sandbox with zero
documents, a name-keyed lookup for a name four instances share, and an anchor fetched by
the literal `"anchor"` while the lcl beside it asked the naming contract. Any one of them
alone broke onboarding. They survived because a clean `INVALID` return went unread.

A hand-built sandbox has none of the provisioner's checks and every one of those failure
modes available to it. Use it to UNDERSTAND the shape; use the provisioner to make one.

```console
$ python -m fnd_app.scripts.provision_instance --manifest instance.yaml       # dry run
$ python -m fnd_app.scripts.provision_instance --manifest instance.yaml --apply
```

`fnd_app/tests/fixtures/test_instance.yaml` is a complete worked manifest, and
`fnd_app/tests/_provisioned_instance.py` builds an entire synthetic instance from it —
sandboxes, registrar entities, a taxonomy, a channel with a catalogue, a signing key and a
fiat datum — which is the shortest end-to-end example of everything on this page.

## Worked example: walking `bootstrap_agro_erp_anchor.py`

This is the most complete bootstrap; read it top to bottom as the canonical
template.

1. **Inputs & constants** — `SANDBOX = "agro_erp"`, the tenant/msn defaults, and
   `PRIMITIVE_ROWS` (the 11 SAMRAS primitives) at
   `fnd_app/scripts/bootstrap_agro_erp_anchor.py:60-80`.
2. **Load source data** — `_load_taxonomy` reads the staged taxonomy entries
   (`fnd_app/scripts/bootstrap_agro_erp_anchor.py:105`).
3. **Build the magnitude** — `_build_magnitude_bitstream`
   (`fnd_app/scripts/bootstrap_agro_erp_anchor.py:120`) encodes the address set
   into a canonical SAMRAS bitstream and round-trips it to self-verify
   (raises if the decoded address set does not match).
4. **Build anchor rows** — `_build_anchor_rows`
   (`fnd_app/scripts/bootstrap_agro_erp_anchor.py:135`) emits the primitive
   rows, the `1-1-1` `txa-SAMRAS` magnitude carrying the bitstream, the
   abstraction rows (`2-0-1`, `2-1-2`), and the babelette rows (`3-1-1`,
   `3-1-2`).
5. **Build source rows** — `_build_txa_rows`
   (`fnd_app/scripts/bootstrap_agro_erp_anchor.py:173`) emits one `4-2-N` row
   per taxon plus the `5-0-1` collection.
6. **Two-pass id computation** — `_build_document`
   (`fnd_app/scripts/bootstrap_agro_erp_anchor.py:199`) builds with the
   placeholder hash, computes the real hash via `_compute_hash` (which calls
   `compute_mss_hash`, `fnd_app/scripts/bootstrap_agro_erp_anchor.py:191`), and
   rebuilds with the real id.
7. **Idempotent persist** — `bootstrap`
   (`fnd_app/scripts/bootstrap_agro_erp_anchor.py:285`) reads the current
   catalog, finds any prior anchor/txa ids, and replaces them via
   `replace_single_document_efficient`. It also keeps the `documents` index
   table in sync (`_replace_documents_table_rows`,
   `fnd_app/scripts/bootstrap_agro_erp_anchor.py:242`).
8. **Dry-run** — `--dry-run` builds and self-verifies everything but writes
   nothing (`fnd_app/scripts/bootstrap_agro_erp_anchor.py:329`).

### Extending an existing anchor (the ingest pattern)

Once an anchor exists, an *ingest* script extends it rather than re-bootstrapping
from scratch: it adds new unit/magnitude rows to the anchor, adds source rows to
the source documents, recompiles affected magnitudes, and re-mints the affected
ids. The ingest script that documented this four-document extension was one of the 13
one-shot agro/cts_gis migrations deleted 2026-07-05 (`03853f40`), along with the
structural-move harness beside it.

The discipline they demonstrated is now the house style rather than one script's habit,
and the living examples state it better:
[`fnd_app/scripts/provision_instance.py`](../../fnd_app/scripts/provision_instance.py)
(idempotent converge, dry run by default, `VACUUM INTO` backup before any write, and a
loud failure on a step that returns a not-OK status) and
[`fnd_app/scripts/mint_octet_rudi.py`](../../fnd_app/scripts/mint_octet_rudi.py)
(refuses the whole run rather than half-writing, and takes no backup on a dry run —
a read-only run that littered the private dir would be a write by another name).

## Attaching tools/lenses

A demo sandbox's datums become eligible for a tool or lens through **document
metadata**, not through any per-sandbox registration. The palette matches a
tool's `applies_to_archetype` / `applies_to_source_kind`
(`micyte/tools/_contract.py:39`) against tokens it pulls off the
document:

- `document_metadata["datum_template_archetype"]` and
  `document_metadata["samras_family"]` feed the archetype set.
- `source_kind` feeds the source-kind set.

See the predicate `_viz_tool_matches`
(`fnd_app/instances/_shared/runtime/portal_palette_runtime.py:59`) and the
metadata extraction in `build_eligible_tools_response`
(`fnd_app/instances/_shared/runtime/portal_palette_runtime.py:106-115`). A tool
with empty `applies_to_*` tuples is treated as universal (matches every datum).

So to make your demo sandbox's documents light up a specific tool, set the
matching archetype/family in their `document_metadata` when you build them in
step 2/3. To author the tool or lens itself:

- Tools: [80-tool-authoring-guide.md](80-tool-authoring-guide.md)
- Lenses: [81-lens-authoring-guide.md](81-lens-authoring-guide.md)

Tools self-register on import and are returned by `all_tools()` (the registry
the palette iterates, `micyte/tools/__init__.py`). They must stay
orchestration-only — the architecture test
`fnd_app/tests/architecture/test_sandboxes_tool_boundaries.py:33` fails the
build if a tool sandbox imports `instances`, `packages.tools`, or `mycite_core`.

## Pitfalls

- **Make the bootstrap idempotent.** Read the current catalog, find any prior
  document with the same sandbox/anchor identity, and *replace* it rather than
  blindly appending. Re-running with the same inputs must yield byte-identical
  ids and zero row deltas (the determinism comes from
  `compute_mss_hash` over sorted rows,
  `micyte/core/mss/datum_identity.py:105`).
- **Canonical ids only.** Never hand-write a `document_id`; always compute it
  with the two-pass placeholder→real-hash dance. The adapter refuses
  non-canonical ids (`micyte/adapters/sql/datum_store.py:203`,
  `:331`), and you constructed the store with `allow_legacy_writes=False`.
- **Do not store datum documents as loose JSON.** The MOS sqlite authority is
  the only canonical home for datum documents. Staged JSON inputs are *sources*
  you read once at bootstrap time, not the store of record.
- **Always dry-run first, and back up the live DB.** The production-grade
  ingests dry-run against an isolated copy and snapshot the DB before any write
  (see `provision_instance.py`'s converge loop). Self-verify after
  writing (re-read the document and assert its id/row count).
- **Keep the `documents` index table in sync** when you write through the raw
  sqlite path, as AGRO-ERP does at
  `fnd_app/scripts/bootstrap_agro_erp_anchor.py:242`; otherwise discovery can
  drift from the catalog snapshot.

## See also

- [20-l2-surface-persistence.md](20-l2-surface-persistence.md) — how the L2
  surface persists and serves the catalog the portal reads.
- [10-l1-core-engine.md](10-l1-core-engine.md) — the L1 core engine that
  computes semantics, hyphae chains, and MSS identities for the rows you author.
- [80-tool-authoring-guide.md](80-tool-authoring-guide.md) /
  [81-lens-authoring-guide.md](81-lens-authoring-guide.md) — author the
  tools/lenses you point at your demo sandbox.
