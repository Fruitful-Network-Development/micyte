# Contract Docs

Canonical cross-cutting contracts for the one-shell V2 portal model.

## Shell and Surface Contracts

- [portal_shell_contract.md](portal_shell_contract.md)
- [route_model.md](route_model.md)
- [surface_catalog.md](surface_catalog.md)
- [tool_operating_contract.md](tool_operating_contract.md)
- [tool_mediation_surface_archetype.md](tool_mediation_surface_archetype.md)
- [service_tool_peripheral_package_contract.md](service_tool_peripheral_package_contract.md)
- [portal_vocabulary_glossary.md](portal_vocabulary_glossary.md)

## Panel and Interface Contracts

Both panel REGIONS are retired — `shell_composition.regions` is exactly
`{activity_bar, workbench}`. Their contracts are kept for the models that outlived them,
and each says so at the top; neither describes a region you can compose today.

- [control_panel_context_control_contract.md](control_panel_context_control_contract.md) — RETIRED 2026-08-16
- [interface_panel_component_frame_contract.md](interface_panel_component_frame_contract.md) — RETIRED; the component-frame lifecycle survives it
- [portal_panel_state_distinction.md](portal_panel_state_distinction.md) — the distinction holds; the column it assumed does not

## Network, Channels, and the Binding Store

- [contract_formation.md](contract_formation.md) — how two instances form a contract
- [hosted_alias_interface.md](hosted_alias_interface.md) — a channel's two halves and their postures
- [port_binding_store.md](port_binding_store.md) — the shape of `private/config.json`, validated

## Addressing, Naming, and Authority

- [datum_document_naming_taxonomy.md](datum_document_naming_taxonomy.md)
- [mos_authority_enforcement.md](mos_authority_enforcement.md)
- [mos_database_schema_addendum.md](mos_database_schema_addendum.md)

## Structural and Mutation Contracts

- [samras_structural_model.md](samras_structural_model.md)
- [samras_validity_and_mutation.md](samras_validity_and_mutation.md)
- [samras_engine_ui_boundary.md](samras_engine_ui_boundary.md)
- [mutation_contract.md](mutation_contract.md)
- [datum_editing_atomicity.md](datum_editing_atomicity.md)
- [mss_engine_invariants.md](mss_engine_invariants.md) — what the engine refuses, and the test that pins each refusal

## Binary Address Encoding

The MSS (mixed-radix, shape-addressed) binary sequence encoding for msn/SAMRAS
addresses:

- [mss_binary_sequence/README.md](mss_binary_sequence/README.md)
- [mss_binary_sequence/cutover_design.md](mss_binary_sequence/cutover_design.md)
