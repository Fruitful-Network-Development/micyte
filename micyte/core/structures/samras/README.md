# SAMRAS

This package owns the pure structural SAMRAS contract in V2:

- canonical encode/decode for breadth-first child-count magnitudes
- legacy fixed-header and numeric-hyphen migration decode paths
- address derivation and round-trip validation
- structure-aware authority selection across compact payload rows
- workspace reconstruction from staged address rows when legacy structure rows are unusable
- canonical mutation helpers for address-tree editing
- structure-only semantics without CTS-GIS-specific presentation logic

CTS-GIS consumes this package as the authority for tree shape. Row overlays remain secondary label evidence.
