# MSS-DOC.v4 — the document transport

## Status

Canonical, 2026-09-23 (TASK-2026-09-17-001 phase C). Implementation:
`micyte/core/mss/transport.py`. Pinned by `fnd_app/tests/unit/test_mss_transport.py` (every row
shape the corpus holds round-trips exactly) and `fnd_app/tests/adapters/test_bitstream_beside_the_rows.py`
(every door writes it; a reader can take it). Rehearsed over the whole live corpus on a disk copy by
`fnd_app/scripts/rehearse_bitstream_parity.py`: 1,356 of 1,356 documents (140,787 rows) decode
row-identical; 81.2 MB packed against 184.0 MB of canonical JSON.

## What it is, and what it is not

`mos.mss_binary_v3` (`micyte/core/mss/document_codec.py`) is a document's **identity**: the canonical
isolated anthology of its downward reference closure, addresses derived, foreign references
dropped and counted. `mos.mss_binary_v4` is the document's **transport**: its stored rows as one
bitstream that decodes back to those rows exactly — same values, same types, same slot shapes,
same addresses. The two share the micro-grammar (Elias-gamma integers, fixed-width fields, the
COBM active sets) and differ in what they carry. v3 is unchanged by this page; it stays the hash
the manifests and the dual-write carry until the id flip (phase D) decides otherwise.

## What the corpus forced (read-only survey, 2026-09-23)

* 805,991 of 808,821 tuple references point outside the document (the shared base, `rf.3-1-N`);
  a closure resolved from the document alone cannot carry them. The transport carries every
  string it cannot index as a **token-table entry**, verbatim, `rf.` prefix included.
* 324 layer-0 rows reference the root `0-0-0`, which no document carries; 27 references point to
  the same or a higher layer. Neither fits an active-set index; both are strings.
* 24 `~` collections hold tokens that are not addresses; 12 rows are a bare string where the
  grammar expects `[[address, …], [title]]`; 845 rows have no title slot; every `art.` row is
  headless (`[[token, magnitude], []]`) and carries integers. Each is a **shape** the grammar names.
* Every text magnitude is a string (808,825 of them, 307,617 distinct); the corpus writes display
  labels as 8-bit-aligned binary text, which the table stores at one bit per character.

## Grammar

See the module docstring in `micyte/core/mss/transport.py` for the field-by-field wire grammar.
In one paragraph: the metadata carries the ORIGINAL layer, value-group and iteration numbers
(delta coded), so the stream is self-describing and a gap survives; the COBM sections mark, per
layer, which earlier-layer datums this layer references locally; a per-document table holds every
distinct string once (UTF-8 bytes, or bits for binary text); the value stream carries one object
per datum — its shape, its typed tokens (local address by active-set index with its `rf.` bit,
string by table index, integer by zigzag gamma, boolean, null, nested value by canonical JSON),
and its title slot's shape.

## Refusals

Two, both from `encode_rows`: a row whose `datum_address` is not `<layer>-<value_group>-<iteration>`
(nothing to derive an address from) and two rows at one address (I1 in
`docs/contracts/mss_engine_invariants.md`). Nothing else is refused; the transport is total over
what the store holds, and the corpus rehearsal is what measures that claim.

## Where it lives

`datum_document_bitstream` (`micyte/adapters/sql/mos_schema.py`): one row per document, written
by every door in the door's own transaction (`_record_bitstream` in
`micyte/adapters/sql/datum_store.py`), purged with the id family by the delete. Three facts
besides a stream: a document over the full-semantics cap carries policy `deferred` and an empty
blob, as its binary identity does; a document the transport refuses carries `refused` with the
sentence in `note` — the door accepted it, so the write lands and the row says what the reader
would find; a document with no row was written before the table existed.
Reading: `MOS_READ_FROM_BITSTREAM=1` serves the decoded rows; `=verify` decodes, compares with the
payload's rows, logs a mismatch as an error and serves the payload; unset (the default) never
touches the table. The payload remains the store of record until phase D.

## The identity policy (phase D, 2026-09-25)

A store is keyed under ONE identity policy: `mos.mss_sha256_v1` (the JSON hash over the
canonical payload — every store until the flip) or `mos.mss_binary_v4` (the transport hash
over the document's rows — the FND store after the flip). The engine
(`micyte/core/datum_semantics/engine.py`, `identity_policy`) mints a new id under
`mos.mss_binary_v4` only while the environment carries the token
`MOS_CANONICAL_HASH=mss_binary_v4`, so re-writing a document's rows mints exactly the id the
flip gave it; `micyte/core/mss/datum_identity.py` delegates to the same function. The
store's write doors (`micyte/adapters/sql/datum_store.py`, `_refuse_identity_policy_mismatch`)
refuse a write keyed under a policy the store's `lv.` documents are not keyed under, with the
sentence naming the token — a forgotten token is a refused write, never a mixed store. Under
`mos.mss_binary_v4` the filing metadata (`source_kind`, `document_metadata`) is not part of
the identity; the sequence is. The flip itself is `fnd_app/scripts/flip_document_identity.py`
(`--apply` under the token; `--live` for the operator's window), and the map it writes is the
rollback. Pinned by `fnd_app/tests/unit/test_identity_policy_token.py`.
