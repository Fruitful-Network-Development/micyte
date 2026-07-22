# MSS binary-sequence spec (canonical wire form) — recovered

These are the **authoritative** original writings for the **MSS (Mycelium Schema
Standardisation) binary sequence** — the canonical single-sequence binary
encoding of a datum document. They were removed from the tree in commit
`b9fd2897 "Rough refactor"` and survived only in git history; restored here so
the spec-of-record lives in-tree.

## Files

| File | What it is |
|---|---|
| `MSS_convention.py` | The original document codec sketch (`MSS` class): `boot` parses the bitstream → `index_a` (address-size header), `index_c` (section boundaries), `index_d` (the **uniform** stack of equal-width stop addresses), `index_g` (the **non-uniform** value stream, sliced by the stops). `boot_load` decodes `index_g` into `[sentinel, L=layers, group-counts…, iteration-counts…, (a=reference, b=magnitude) pairs…]` → `DnmcDtm(layer, group, iteration, reference, magnitude)`. |
| `anthology-notes.txt` | **The gold oracle.** A real anthology bitstream decoded step-by-step, plus the canonical **anthology base** (rudis `0-0-1..0-0-11`: top/tiu/sop/siu/nop/niu/mop/miu/gold/photon/json) and the layer-1+ datums in `<addr>: [[addr, ref, mag, …], [title]]` form. Use this to validate any codec. |
| `mss_compact_array_reference.py` | A 1044-line reference implementation of the canonical compact-array rules. **Caveat (its own docstring):** "a sound reference model with explicit assumptions, not a promise that every bit matches" — and its built-in round-trip self-test does **not** pass under Python 3.13. So it documents the *rules*, not a finished codec. |
| `main.py`, `example.msn-contract.json` | Driver + an example msn/contract payload. |

## The canonical rules (firm)

1. The MSS of a document = the **transitive downward reference closure** of its
   datum(s), **reindexed into an isolated anthology**. (Hyphae = the same codec
   over a single datum's focus closure.) The closure walks down to the rudis, so
   the **rudi ordinal scaffold is always carried** — *"include all preceding rudi
   datums even if not used directly; if the abstraction uses `0-0-5`, include
   `0-0-1` through `0-0-5`"* (`MOS/mycelial_ontological_schema.md`). This is what
   makes a datum **canonical** — the ordinal/incremental/nominal frames are
   anchored to the universal rudi starting position.
2. Wire layout: address-size header → section boundaries → **uniform stop-address
   array** → **value stream** sliced by the stops. The value stream carries
   metadata (`layer_count`, `value_group_count_per_layer`,
   `iteration_count_per_VG`, `value_group_value_per_VG`), a **COBM** between
   populated layers (defines the active carry-over set so reference width is fixed
   per layer), then the objects: **VG0 rows = references only; VG>0 rows = exactly
   `value_group` (reference, magnitude) tuples**.
3. **Document hash = a hash of this MSS sequence.** A document's identity is its
   MSS — never a hyphae value. Hyphae is the same codec with focus-preprocessing.

## What is NOT yet fixed law

The exact low-level bit micro-grammar (self-delimiting integer format, COBM bit
layout, VG0 row grammar) is, per the author, "still a design choice." A correct
codec must (a) honor the firm rules above and round-trip, and (b) be validated
against the `anthology-notes.txt` worked example.

> Status: spec-of-record (recovered). The shipping codec under
> `micyte/core/mss/` is being built against these rules; today's
> `mos.mss_sha256_v1` (JSON-of-rows + SHA-256) is a canonical-ish **stand-in**,
> not the binary MSS sequence.
