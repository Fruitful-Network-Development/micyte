# SAMRAS Engine UI Boundary

## Status

Canonical

## Current Contract

The engine owns SAMRAS semantics. UI surfaces consume structure-aware results and mutation outcomes.

Engine ownership includes:

- decode and encode
- structural validation
- authority selection
- legacy compatibility decode
- row-based structure reconstruction
- address mutation and rebuild

UI ownership includes:

- tree inspection
- dropdown or directory presentation
- node addition/removal intents
- display of diagnostics and warnings

The UI should not normally author raw SAMRAS magnitudes directly. Canonical writes persist the structural bitstream only.

## CTS-GIS Implication

CTS-GIS consumes SAMRAS tree shape from the shared package. Administrative node rows are secondary overlays:

- structure rows decide the namespace
- title rows can decorate nodes
- duplicate or out-of-range title rows are diagnostics
- those overlay defects do not block bare node-id navigation when a valid structure is available

CTS-GIS first tries decodable structure authorities, then falls back to row-based reconstruction only when needed for legacy compatibility.

## Authoritative Paths

- `MyCiteV2/packages/core/structures/samras/`
- `MyCiteV2/instances/_shared/runtime/portal_cts_gis_runtime.py`
