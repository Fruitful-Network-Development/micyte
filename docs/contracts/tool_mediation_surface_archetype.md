# Tool Mediation Surface Archetype

## Status

Canonical

## Purpose

This note captures the mediation-tool pattern that has become clearer through CTS-GIS.

It is not a CTS-GIS-only behavior description. It is the preferred model for complex reducer-owned mediation tools that need tool-local navigation plus correlated evidence projection inside the shared portal shell.

## Shared Shell Boundary

The shared shell contract stays unchanged:

- reducer-owned shell focus remains `sandbox -> file -> datum -> object`
- a tool does not add new shell depth below `object`
- tool-specific navigation is body-carried through tool-local runtime state

For tools in this class, the public posture is:

- `tool_mediation_surface`
- `interface-panel-led`
- `workbench.visible=false` by default
- supporting-evidence workbench content only when the runtime explicitly projects it

## Tool-Local State

Complex mediation tools should keep richer navigation and correlation state in a tool-local payload rather than widening shared shell query or shell depth.

The stable pattern is:

- shared shell state owns the current reducer-backed mediation subject
- tool-local state owns internal navigation, selection, intention, and evidence focus
- runtime returns canonical next tool-local state in the response body

## Interface Body

A mediation tool should project one tool-local interface body inside the dominant `presentation_surface` region.

Recommended structure:

- one dominant structural or directive tab
- one or more correlated evidence tabs or panels driven by the current tool-local selection
- narrow posture may stack the same tab-local panels vertically without changing their semantic contract

CTS-GIS is the reference example:

- `Diktataograph` is one shared-host Interface Panel tab that drives tool-local structural navigation
- `Garland` is one shared-host Interface Panel tab that projects correlated profile and geospatial evidence for the current node
- these are two projections of one mediation posture, not separate mediations

## Decoder Placement

Decoding or lens logic belongs in the service layer, not in the renderer.

The stable rule is:

- renderers consume already-decoded projection payloads
- services own ASCII, HOPS, or other lens/overlay decoding
- runtime composes decoded service surfaces into tool-local interface-body contracts

## Blank State Rule

A mediation tool should prefer explicit blank-but-stateful projection over misleading fallback content.

That means:

- if tool-local navigation resolves structurally but correlated evidence is missing, keep the current selected subject visible
- do not silently borrow another node, document, or feature just to avoid an empty panel
- reserve real projection state for evidence that actually matches the current tool-local selection

CTS-GIS now follows this rule by keeping Garland aligned to the selected SAMRAS node even when no matching profile source or HOPS projection exists yet.

## Evidence Posture

Supporting evidence should be explicit and precedence-ordered.

The stable pattern is:

- governance and anchor files first
- structural authority second
- label/profile/spatial evidence after that
- workbench content remains secondary evidence, not a duplicate primary experience

## Adoption Guidance

Other tools should reuse this archetype when they need:

- reducer-owned shell posture
- tool-local navigation inside one mediation subject
- multiple interface sections that are synchronized projections of one current selection
- service-owned decoding or lens logic

Tools that are query-driven service surfaces may still use a lighter model, but they should preserve the same shell posture vocabulary and workbench/interface separation.
