# Changelog

MiCyte's releases, newest first. One version, read from `micyte/__init__.py`; the public
repository is tagged `v<version>` and the wheel on its release page is the artifact.
`docs/standards/release_and_versioning.md` is the process; `scripts/publish_micyte.py` is
the cut. A section is added when the version is bumped, not after.

## 0.4.1 — 2026-09-30

- The public suite passes in the public repository. 0.4.0's cut shipped five tests that
  load a script (`scripts/mint_archetype_sandbox.py`, which carries a live address) or an
  asset (the portal's built sprite) the cut does not carry, and the public repository's
  first CI run failed on collection. Those tests are FND's (the ratchet now says so: a
  test that reaches a script or a path the cut does not ship is not public), and
  `scripts/publish_micyte.py` runs `micyte/tests` inside the export before it builds the
  wheel, so the release gate refuses a cut whose suite would not pass where it is
  published.
- The class library and the viewscopes keep their families. 0.4.0's readdress moved 63
  `kind_*` and `viewscope_*` documents with the archetypes, and their readers — which
  select rows BY FAMILY (header 4-1, members 4-2, slots 4-3; container 4-1, slots 4-2),
  as their modules say — went blind: every viewscope pane drew zero groups and the
  calendar found zero logs, while the archetype registry parsed identically. The library
  was restored from the pre-window backup and readdressed again under one rule,
  `datum_ops.positional_grammars`: a document a positional reader owns is not held to I7.
  The readdress refuses such a document whatever its flags say, the audit reports it
  apart instead of as a finding, and the lock is re-cut — the 57 archetypes keep 0.4.0's
  hashes (the packages' pins are unchanged), the 63 owned documents return to theirs.
  No engine change.

## 0.4.0 — 2026-09-30

- The archetype library keeps the arity convention: its 100 documents' 234 positional
  rows moved to the families their pair counts name, with every citation carried
  (47 rewritten, cascade depth 3). An archetype's id is its content hash, so every one of
  the 101 that moved is a new hash — the lock is re-cut and the four packages that pin
  them bump with it: quiar 2.4.0, brevat 1.3.0, grantor 0.3.0, oveure 1.3.0. The live
  audit reads I6 0 · I7 0 · I8 0 for the first time; the 24 I10 titles are the operator's.

### Engine
- The store's REPLACE door judges what changed (`check_replaced_rows`): I6, I9, I10 on
  every row that is new or whose bytes changed; I7 on those when the prior keeps the
  convention; I8 as "a family may not gain a hole where no row was" — a compaction and a
  readdress pass, a delete's hole is admitted, a skip is refused at the first new hole.
  It judged nothing before (`docs/contracts/mss_engine_invariants.md`).
- A raw row `[[address, …], [title]]` is read as a row, not as an `(address, raw)` pair;
  `arity_convention_holds` answers over raw rows.
- A local-domain definition row's family is its arity — every pair, extras included —
  and its references come before its extras, where `trailing_refs` reads; readers find a
  definition row by shape (`local_domain.is_definition_row`), on any marker, in any family.
- `row_address.next_row_address` is how a writer mints an address; a row whose edit
  changes its shape moves to the family its new arity names and the writer says where.

### Gadgets
- `/healthz` reports `packages`: the install ledger against this build's catalogue.
- The four packages above bump for the re-pinned archetypes; every other package's
  declaration is unchanged.

### The repository
- The public suite: `micyte/tests` — 64 tests that exercise `micyte.*` alone — ships with
  the cut, and the cut writes the public repository's own CI workflow.
- `docs/standards/development_process.md`: how a change lands (worktree, focus-named
  branch, the gate, PR, the tests workflow, merge, the gated deploy) and the focus registry.

## 0.3.0 — 2026-09-27

- The FND store's document ids carry the hash of each document's stored MSS bitstream
  (`mos.mss_binary_v4`); the engine mints under the policy token and the doors refuse any
  other. The archetype lock is re-cut against the flipped library, and the packages that
  pin archetypes bump with it: quiar 2.3.0, brevat 1.2.0, grantor 0.2.0, oveure 1.2.0.

### Engine
- `micyte/core/mss/invariants.py`: ten named invariants (`docs/contracts/mss_engine_invariants.md`);
  the codec's five wire-level refusals have one home, and the store's two write doors refuse
  the five document-level ones — head names its address, arity names the family (for a
  document that keeps the convention), one past the family's highest, archetype coverage
  when the writer names one, a 64-character title — every refusal reported at once.
- `micyte/core/mss/transform.py`: the manipulation primitives as set operations — sibling
  detection by material binary difference, set transform by range copy / delete / create
  with address shift, re-denotation to another value group, and the repairs (`reindex_heads`,
  `compact`, `readdress`) — refused whole when a result would introduce a violation.
- Archetype runs may bind a PARENT radix (`Run.parent`); the row shape carries each field's
  backing radix when the anchor is supplied.
- The binary MSS identity (`mos.mss_binary_v3`) is dual-written beside the JSON one on every
  write (`datum_document_binary`), with the references the closure could not carry counted.
- `micyte/domains/registry/minting.py` mints a row one past its FAMILY's highest, not the
  document's.

### Gadgets
- A document requirement pins the archetype hash it was built against
  (`micyte/tools/_archetypes.lock.json`); `unmet_requirements` reports a mismatch with both
  hashes and `compatibility` names it; installing an incompatible package is refused before
  anything is written; `check_updates` and `update_package` are new.
- `micyte/tools/_packages.lock.json`: a package whose declarations change bumps its version.

### Datum
- Four canonical id prefixes: `lv.`, `stl.`, `cptr.`, `art.` — the naming contract is pinned
  to the code by a test.
- `payment_instrument`: a processor-agnostic outbound port (vault / describe / charge /
  detach); no operation takes a card number.

### Readers and the ground (2026-09-25)
- Twenty-five whole-catalog readers take the index, one document, or one sandbox;
  `read_documents_by_sandbox` is remembered per store version under the catalog's rule and
  forgotten by every door; the palette names each instance that holds a shared sandbox name.
- The network map's boundary polygons are a versioned asset (`GET /portal/api/network/ground?v=<hash>`,
  immutable for the version asked for, gzipped once at publish): the network POST fell from
  3.08 MB to 50 KB and the browser draws the ground from its cache on every later visit.
- The worker's warm renders each PIM-paired client's landing after the operator's; the typed
  leaflet index's fingerprint counts directory entries, so a same-tick write is seen.

### Gadgets over the network (2026-09-25)
- `micyte/tools/_packages_manifest.py`: a publisher's catalogue as a hashed manifest — every
  package's whole declaration beside the digest the lock pins (one definition; the lock
  script imports it); the reader rebuilds the port's dataclasses, refuses an entry that does
  not hash to its digest, and marks what it returns official. `GET /__mss/public/packages`
  serves the running build's catalogue; an instance pulls it under its instance-network grant
  (`POST /portal/api/v2/packages/pull`), and `install_status`/`check_updates` judge the ledger
  against the official source when one was pulled (`offered_by`, `in_this_build`).
- A base account's grantee and instance are minted as occupants of the client's house through
  the registry's own minter (`mint_base_account_addresses`; `onboard_base_account.py --mint-under`).

### The I7 conversion (2026-09-26)
- `fnd_app/scripts/readdress_documents.py`: the repair's readdress transforms handed to the
  flip's cascade, so every citing magnet follows the new hash AND the moved row address; the
  flip's `compute` takes `transforms=`, its `verify` counts magnets by hash and by row. `readdress`
  places a second mover into a non-empty family one past the greater of the family's highest
  and the highest placed (it added them).
- The event vocabulary is found in the tree by label (`micyte/core/datum_ops/event_vocabulary.py`),
  with the legacy ordinals as the fallback.

### Store
- The catalog is READ FROM THE PER-DOCUMENT TABLES (`documents` ⋈ `datum_document_semantics`
  ⋈ the new `datum_document_provenance`), never from the 138 MB snapshot blob: measured on
  the live store, the tables hold every row the blob holds, the same metadata, the documents
  the blob never did, and the append the blob path was silently dropping. The blob is kept,
  unread, as the rollback copy; the index is projected from the tables and keyed for
  freshness on their newest write. `store_authoritative_catalog` now indexes what it
  stores; a re-keyed document keeps its place in the catalog; every door records a
  document's provenance (naming and the anchor context it was written with) beside its
  index row, healed once from the blob for an older store. `fnd_app/scripts/verify_catalog_parity.py`
  compares the two readers on any store, read-only.

### Portal host
- The gunicorn master no longer preloads the app or warms the datum-workbench projection
  (`_warm_system_workbench_projection` removed): on a 3.87 GB host the preloaded master held
  736 MB, swapped, for a surface nobody renders. `gunicorn_hooks.post_worker_init` warms the
  landing surface in the worker instead (`PORTAL_WARM_ON_BOOT=0` disables). The unit drops
  `--preload` and `--max-requests`.
- Leaflet adapters read YAML through `CSafeLoader` when libyaml is present
  (`fnd_app/packages/adapters/filesystem/_yaml.py`): a 900 KB analytics month parses in
  0.45 s instead of 3.3 s. `AnalyticsLeafletStore.load_month` remembers a parsed month by
  the file's `(path, mtime, size)` and hands back a copy; the writer reads the file.
- `instance_account.storage_facts` is remembered per store identity for five minutes.
- Read-only analytics readers (the rollup, the visitor log) borrow the cached month
  (`load_month(copy=False)`) instead of copying it; the writer still reads the file.
- `resource_types.build_type_leaflet_index` is remembered per pool state (the scanned
  directories' mtimes, sixty seconds at most): `resource_facts` asked for it once per type
  per render.
- The worker's warm logs through `gunicorn.error`, so `portal_warm_done` reaches the journal.
- The operator's hot tabs stop parsing the whole-tenant catalog blob: `read_sandbox_catalog`
  gains a `sandbox=` door that reads ONE sandbox through `read_documents_by_sandbox` and
  remembers it per store version; the network map and the profile's registrar face read
  `registrar` through it. The network base is remembered per (store, sandbox, day);
  `directory._gazetteer` labels are remembered by document id; `read_instance_catalog` is
  remembered per store version; the Peripherals tab remembers each domain's AWS status for
  sixty seconds and says when it read it; `for-sandbox` refuses a blank `sandbox_id`.
- `_node_names.build_name_index` folds the shared sandboxes (`registrar`, `taxonomy`) once per
  store version and merges them from memory for every later asker: a cold profile render
  folded the registrar twice, two thirds of its 11.6 s.
- Analytics events are JOURNALED, not buffered: `AnalyticsLeafletStore.append_event` writes
  one JSON line under the month's lock the moment an event arrives (durable before the
  response), and the month leaflet is folded from the journal once a minute
  (`AnalyticsIngestBuffer.rollup`, the same merge `ingest_batch` uses; a worker folds any
  leftover journal as it boots). Leaflets are dumped through `CSafeDumper`, byte-identical
  to `safe_dump` and four times faster. Before: events sat in memory up to 25 or 8 s, every
  flush parsed and re-dumped the whole month (2.8 s at 956 KB), and a killed worker lost
  its buffer.

## 0.2.0 — 2026-08-24

- First public cut with the `micyte/` package extracted from FND's tree (2026-07-16) and
  renamed throughout; AGPL-3.0; Python 3.13; wheel on the release page, not on PyPI.

## 0.1.0 — 2026-07-16

- The extraction: `micyte/` becomes an installable package; FND grantee services are its
  first consumer.
