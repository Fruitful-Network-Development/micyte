# SAMRAS Structural Model

> **Companion contract:** SAMRAS encoding/decoding only. SAMRAS data
> lives exclusively in MOS — see
> [`mos_authority_enforcement.md`](mos_authority_enforcement.md) for the
> binding storage-authority rule.

## Status

Canonical

## Current Contract

SAMRAS is a shape-addressed mixed-radix address space represented as a structural value.

The structure defines a forest of nodes. Nodes do not store full addresses directly. Instead:

1. the structure stores child counts
2. those counts are interpreted in breadth-first order
3. addresses are derived from ordinal child position

Boundary reminders:

- SAMRAS structural addresses are not anthology/resource datum addresses
- SAMRAS addresses are not MSS compact-array row indexes
- similar decode mechanics do not imply shared identity semantics

The governing structural datum is the layer-1 datum authored in reference to `0-0-5`.

## Encoding Layout

A canonical SAMRAS magnitude is encoded as:

1. `address_width_field`
2. `stop_count_width_field`
3. `stop_count_field`
4. `stop_address_array`
5. `value_stream`

The canonical width fields are unary:

- `00001` -> width `4`
- `00000000001` -> width `10`

Decoded values are interpreted as:

- first value = root count
- each later value = child count for the next node in breadth-first order

## Address Derivation

If the decoded values are `v0, v1, v2, ...`:

- `v0` yields root nodes `1..v0`
- every later value yields the child count for the next queued node
- child addresses are assigned contiguously as `parent-1`, `parent-2`, ..., `parent-n`

Example lineage:

- `3`
- `3-2`
- `3-2-3`
- `3-2-3-4`
- `3-2-3-4-5`

## Historical Compatibility

V2 keeps the historical V1 compatibility decode paths:

- canonical unary-header binary
- legacy fixed-width-header binary
- legacy numeric-hyphen payloads

When a legacy payload decodes, the engine treats it as provisional and expects a canonical rewrite on save.

The reconstructed SAMRAS note in `docs/personal_notes/SAMRAS/samras_msn_reconstructed.txt` is a valid canonical example:

- `8` roots
- `622` nodes
- canonical width pair `10 / 10`

## Authoritative Paths

- `micyte/core/structures/samras/codec.py`
- `micyte/core/structures/samras/structure.py`
- `micyte/core/structures/samras/validation.py`
- `docs/personal_notes/SAMRAS/shape_addressed_mixed-radix_address_space.md`
