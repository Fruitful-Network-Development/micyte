# MSS engine invariants

## Status

Canonical, and pinned: `fnd_app/tests/architecture/test_contract_pages_are_pinned.py` asserts that
every test this page names exists. Written 2026-09-17 (TASK-2026-09-16-002 P0/P1) from a measured
reading of the live store and the code, not from the earlier specs alone.

## Purpose

Name every property the engine relies on a document having, say WHERE it is enforced (the codec
on the wire, or the store's write door on the rows), give the sentence a refusal carries, and pin
each to the test that proves the engine — not a caller — refuses a violation. A rule enforced in
one caller is a rule the next caller skips: before this page, archetype coverage was checked in
five `fnd_app` write runtimes and in no engine.

Implementation: `micyte/core/mss/invariants.py` — `check_datums` (wire level, over `MssDatum`s)
and `check_rows` / `check_new_rows` (document level, over stored rows). The codec's
`_validate_canonical` and the store's `create_document_rows` / `append_document_rows` call them
and raise `MssFormatError` / `InvariantRefused` carrying EVERY refusal, not the first.

## The two levels

**Wire level** — properties of a canonical datum set the binary codec
(`micyte/core/mss/document_codec.py`, policy `mos.mss_binary_v3`) can encode at all. A set that
violates one cannot be given a hash. These five are the refusals the codec has always made;
this page names them and the checker becomes their one home.

Since 2026-09-23 there is a second wire, the document TRANSPORT (`mos.mss_binary_v4`,
`micyte/core/mss/transport.py`, `docs/contracts/mss_binary_sequence/transport_v4.md`): the
stored rows as one bitstream that decodes back to them exactly. It requires I1 only — a reference
the identity codec would refuse under I4 or I5 is carried as a string token, not dropped — so a
document that fails I2–I5 still has a transport and only lacks an identity.

**Document level** — properties of the rows a document stores, which the wire is deliberately
lossless about (the wire carries arity explicitly, so it can encode a row whose address lies
about its arity) and which the ENGINE must therefore refuse at the write door. Operator decision
D1 (2026-09-17): a value group on an instance row IS its arity.

## The invariants

| id | level | rule | enforced by | refusal sentence | pinned by |
|---|---|---|---|---|---|
| I1 | wire | every datum address is unique | codec `_validate_canonical` | `duplicate datum address` | `fnd_app/tests/unit/test_mss_invariants.py` |
| I2 | wire | layers are contiguous from 0 (reindex first) | codec | `layers must be contiguous from 0 (reindex first)` | `fnd_app/tests/unit/test_mss_document_codec.py` (`test_non_contiguous_layers_rejected_by_encode`) |
| I3 | wire | a datum is refs-only or tuple-bearing, never both | codec | `datum <a> cannot be both refs-only and tuple-bearing` | `fnd_app/tests/unit/test_mss_document_codec.py` (`test_refs_and_tuples_together_rejected`) |
| I4 | wire | every reference names a datum in the set | codec | `datum <a> references missing <ref>` | `fnd_app/tests/unit/test_mss_invariants.py` |
| I5 | wire | references point downward, to a strictly lower layer | codec | `datum <a> references <ref> which is not in a lower layer (refs must point downward)` | `fnd_app/tests/unit/test_mss_document_codec.py` (`test_upward_reference_rejected`) |
| I6 | document | a row's head names its own address (`raw[0][0] == datum_address`); `art.` rows keep the artifact grammar and are outside this rule | store door | `row <a> has a head that names <b>` | `fnd_app/tests/unit/test_mss_invariants.py` |
| I7 | document | an instance row (layer 4) carrying *n* ≥ 1 pairs lives in family `4-n`; a head with no pairs is the structural blank and lives in `4-1`; a `~` (refs-only) head is outside this rule | store door, for a document that keeps the convention (see below) | `row <a> carries <n> pairs, so its family is 4-<n>, not 4-<vg>` | `fnd_app/tests/unit/test_mss_invariants.py` |
| I8 | document | iterations are contiguous from 1 within a layer-4 family; an appended row lands one past the family's highest (the name layers below are sparse by design) | store door (new rows); audit (whole document) | `row <a> would leave a gap: family <f> reaches <k>, so the next row is <f>-<k+1>` | `fnd_app/tests/unit/test_mss_invariants.py` |
| I9 | document | a row a writer files under an archetype is covered by that archetype (`Archetype.covers`); structural rows (the blank, a `~` collection) say nothing about kind and are outside it | store door, when the writer names the archetype (`expects_archetype`); a two-archetype document — `job_document_runtime` — names them per row itself until the door takes a per-row map | `row <a> folds to a shape <archetype> does not cover` | `fnd_app/tests/unit/test_mss_invariants.py` |
| I10 | document | a title is at most 64 ASCII characters (`labels.TITLE_BITS` = 512) | store door | `row <a> has a title of <n> characters; the title babelette holds 64` | `fnd_app/tests/unit/test_mss_invariants.py` |

## What the live corpus said (2026-09-17, read-only, `scripts/audit_mss_invariants.py`)

1,356 documents, 140,782 rows; 196 documents carry a finding.

| sandbox | I6 | I7 | I8 | I10 |
|---|---:|---:|---:|---:|
| agnet | 0 | 7,917 | 3 | 1 |
| archetype | 0 | 234 | 1 | 0 |
| brevat / glyph / oveure / quiar | 0 | 8 | 5 | 0 |
| grantor | 0 | 174 | 1 | 0 |
| pim | 0 | 46 | 8 | 0 |
| registrar | 2,103 | 1,075 | 37 | 23 |
| system | 11 | 608 | 8 | 0 |
| taxonomy | 0 | 455 | 1 | 0 |
| **total** | **2,114** | **10,517** | **64** | **24** |

* **I6 is a real defect class, 2,114 rows.** `registrar/administrative` holds 2,103 rows at
  `4-2-N` whose heads still read `4-1-N`: a re-address rewrote the key and not the head.
  `system/quadrennium_cycle` stores `4-2-11` with a head of `4-2-10` and no `4-2-10`. The
  transform in `transform.py` rewrites `head[0]` with the key, as `_drop_and_renumber`
  already does; these rows are its first repair.
* **I7 is a convention 10% of layer-4 rows do not keep** — not the 31 exceptions the
  2026-06-01 cutover audit counted (that audit spanned every layer; this one is the row
  layer). Whole sandboxes use the value group POSITIONALLY: agnet's one-pair profile rows
  at `4-2`, `registrar/msn_registry` at `4-9`, taxonomy's four-pair txa rows at `4-2`,
  PIM analytics' five-pair rows at `4-1`, `system/farm_profile` with 23 pairs at `4-5`,
  and every archetype's own blank instance at `4-1-1`. Two live appenders mint that way
  (`site_analytics_source.py`, `micyte/domains/registry/minting.py`); ten mint by arity
  through `row_address.next_row_address`. **So the door holds a document to I7 when the
  document keeps it** (`arity_convention_holds`: every pair-bearing layer-4 row already in
  family `4-<arity>`), judges nothing on a document that has not said, and leaves a
  positional document to its convention. Converting a positional document is
  `transform_set` work, one document at a time, an operator's decision each — the audit is
  the map.
* **I8: 64 gaps at layer 4**, all real (a `pim/lcl_domain` family `4-3` holding
  `[1, 4, 5, …]`); the name layers below are excluded by rule.
* **I10: 24 titles over 64 characters**, all in registrar logs.
* The 24,249 findings the first run reported against `art.` documents were the checker
  misreading the artifact grammar (chain reference first) — that grammar is
  `datum_ops/artifact.py`'s and is excluded by rule, not by count.
* The door judges the rows being WRITTEN. Existing gaps and lying heads are findings for
  the audit and for `transform.py`'s compaction, not a reason to refuse the next append.

## Not invariants (deliberately)

* "VG0 rows are references only" (recovered spec rule 2) — the codec's v2 note records that the
  live corpus keeps refs-only and tuple-bearing datums under any value group at layers below 4,
  and the wire carries which is which. Measured, not enforced.
* Title vocabulary, field naming, and namespace claims — those are the field registry's and
  the archetype library's; this page holds only what the engine itself must refuse.

## Related

* `datum_editing_atomicity.md` — the insert / delete / shift algorithm (I8's repair side).
* `mss_binary_sequence/README.md` — the recovered wire spec; `cutover_design.md` — the audit.
* `docs/wiki/61-mss-and-hyphae-form-spec.md` — the wiki-level summary.
