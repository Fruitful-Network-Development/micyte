# MSS cutover — conformance audit + migration design

> Status: design — **awaiting a model decision (see §3) before any migration code.**

Goal: make the binary-MSS-sequence hash (`MyCiteV2/packages/core/mss/document_codec.py`,
`mss_document_hash`) the **canonical** document `version_hash` + hyphae form, replacing
the `mos.mss_sha256_v1` JSON+SHA-256 stand-in. The maintainer asked to **verify
conformance + design first**; this is that deliverable.

## 1. Read-only corpus audit (live `fnd` MOS, 2026-06-01)

Source: `<authority-db>.sqlite3` (read-only).
**163 documents, 50,729 three-segment datums.**

| Class | Count | Notes |
|---|---:|---|
| VG0 (refs-only) | 1,706 | every one leads with the `~` marker — consistent |
| **VG>0 conforming** (`len(body) == 2·value_group`) | **48,854** | **99.94%** of VG>0 datums follow "value_group = #(ref,magnitude) tuples" |
| VG>0 **non-conforming** | 31 | in 4 docs — see §2 |
| Operational/scalar rows | 138 | `raw` is a bare `str` (118) or `int` (20), **not** the `[[head],[title]]` datum model — a different document class (§2.D) |

**Takeaway:** the canonical datum-document model overwhelmingly follows the MSS
convention. The cutover is *not* blocked by widespread non-conformance — but the 31
exceptions + the operational class force two scoping decisions before we change identity.

## 2. The exceptions (classified)

- **A. Filament / entity records** — `sc.*.msn-natural_entity.json` `4-1-*` (8-token
  bodies = **4 attribute tuples** under `value_group=1`), `sc.*.registrar.json` `4-1-*`
  (10-token bodies = **5 tuples** under VG1). These are entity rows carrying several
  `(attribute_ref, value)` tuples, where `value_group` is **not** the tuple count.
  *This is the important class:* "value_group = tuple count" does **not** hold for
  filament/entity records.
- **B. Anchor positional datums** — `agro_erp.anchor` `1-2-1`/`1-2-2`: `value_group=2`
  but **one** tuple (`0-0-1`/`0-0-3` + a big magnitude). Here `value_group` is used
  positionally, not as a tuple count.
- **C. Bare structural magnitude** — `registrar.json` `1-1-2`: a single bitstream
  value, **no ref** (a SAMRAS/HOPS magnitude stored alone).
- **D. Operational scalar docs** — newsletter contact logs, `aws_csm` profiles, etc.:
  rows whose `raw` is a scalar string/int (a schema tag, a domain, a timestamp).
  These are **operational records**, not canonical datum documents; the MSS datum
  codec does not model them.

## 3. The decision this forces (maintainer's call)

The recovered spec says *"VG>0 rows store exactly `value_group` tuples."* The live data
shows `value_group` is really the **address segment** (SAMRAS/HOPS ordinal position),
which *usually* coincides with the tuple count but not for filament/entity records (A).
So before the codec can encode the whole corpus, choose one:

1. **Store tuple-count explicitly in MSS-DOC** (recommended). Add a per-datum
   tuple-count to the grammar instead of deriving it from `value_group`. Handles A/B/C
   uniformly, decouples `value_group` (a pure address segment) from arity, and matches
   the data as-is. Small grammar change (MSS-DOC.v2); no data migration of the 31 rows.
2. **Re-model the 31 to conform.** Migrate filament/entity records so `value_group`
   equals their attribute count. Keeps the spec's exact rule but changes real
   addresses/save-titles of those records (a data migration on top of the hash cutover).
3. **Scope MSS to conforming docs only** for now; keep filament/entity + operational
   docs on the stand-in hash. Smallest blast radius; leaves the model split.

Class **D** (operational docs) should be **out of scope** for MSS regardless — they are
not datum documents; they keep `mos.mss_sha256_v1` (or move to a non-datum store).

## 4. Adapter sketch (`AuthoritativeDatumDocument` → `MssDatum`)

For canonical datum docs: parse `raw[0] = [address, t0, t1, …]`. Address → (layer,
value_group, iteration). VG0 (or leading `~`) → refs-only from the trailing tokens.
VG>0 → pair the trailing tokens as `(ref, magnitude)`; **arity from the explicit
tuple-count (option 1)** rather than from `value_group`. Reference tokens are datum
addresses or `rf.<addr>` markers; magnitudes are decimal/bitstring values. Cross-document
refs (e.g. `3-2-3-…` msn-qualified) need a documented resolution rule (the closure must
be reindexed across the doc set, or qualified refs treated as opaque leaves).

## 5. Migration plan (once §3 is decided — runs in a maintenance window, not by me)

1. Land the adapter + a config flag `MOS_CANONICAL_HASH=mss_binary_v1` (default `off`
   ⇒ `main` stays behavior-preserving).
2. `scripts/recompile_datum_semantics.py` (offline, on a DB copy first):
   - recompute every canonical doc's `version_hash` via `mss_document_hash`,
   - reissue save-titles (`lv.<msn>.<sandbox>.<name>.<NEW hash>`) + the documents index,
   - recompute `datum_row_semantics` hyphae values,
   - **remap `directive_context` subject keys** (old `subject_hyphae_hash`/version → new)
     so overlays don't orphan,
   - write an old→new hash map for rollback.
3. Verify on the copy (counts, overlay resolution, a portal smoke), then flip the flag
   on prod in a window. `version_hash` is content-derived, so re-running is idempotent.

## 6. Reversibility

The flag defaults off; the migration keeps an old→new hash map; `version_hash` is a pure
function of content, so the cutover is re-runnable and the stand-in remains computable for
rollback. No raw datum content changes (only identities/derived semantics) under option 1.
