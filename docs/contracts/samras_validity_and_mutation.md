# SAMRAS Validity And Mutation

## Status

Canonical

## Current Contract

A SAMRAS structure is valid only when its encoded fields decode correctly and the derived address space is structurally consistent.

Important validity conditions include:

- width fields decode correctly
- stop-count and stop-address array decode correctly
- stop addresses are strictly increasing and remain within the value stream
- value slicing yields no empty tokens
- breadth-first child-count decode consumes all tokens exactly
- roots and children are contiguous
- references do not exceed the structure the magnitude permits

## Canonical Mutation Flow

Canonical mutation does not edit the raw magnitude directly. The engine flow is:

1. decode the current structure
2. derive the canonical address tree
3. apply address-level mutation
4. revalidate continuity and structure
5. regenerate breadth-first child counts
6. regenerate stop addresses
7. regenerate the final canonical bitstream

This keeps address rows derived, not independently authoritative.

## Historical Restoration In V2

The V1 mutation helpers are restored in the V2 SAMRAS package for structural editing:

- `add_root`
- `add_child`
- `remove_branch`
- `move_branch`
- `set_child_count`
- `rebuild_structure_from_addresses`

V2 also restores the historical workspace behavior where staged address rows can reconstruct a canonical SAMRAS tree when a legacy structure row is missing or unusable.

That reconstruction path is compatibility logic, not a replacement for keeping the governing magnitude correct.

## Authoritative Paths

- `MyCiteV2/packages/core/structures/samras/mutation.py`
- `MyCiteV2/packages/core/structures/samras/workspace_adapter.py`
- `MyCiteV2/packages/core/structures/samras/validation.py`
