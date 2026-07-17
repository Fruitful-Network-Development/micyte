# MiCyte Docs

## Start Here

This repository is MiCyte: a MOS-backed datum operating environment and the portal
shell over it. One portal shell, one application authority model.

- Canonical public entry: `/portal` -> `/portal/system`
- Canonical shell endpoint: `/portal/api/v2/shell`
- Canonical tool work pages: `/portal/system/tools/<tool_slug>`
- SQL-backed authority is the expected posture for `SYSTEM` surfaces
- `/portal/system/tools/workbench-ui` is the read-only two-pane SQL authority lens

If you are orienting to the repo for the first time, read:

1. [`docs/wiki/00-overview-and-glossary.md`](wiki/00-overview-and-glossary.md)
2. [`docs/wiki/separation_and_responsibility.md`](wiki/separation_and_responsibility.md)
3. [`docs/contracts/README.md`](contracts/README.md)

## Documentation Families

This repo uses a few documentation families on purpose:

- code-adjacent package docs:
  `MyCiteV2/**/README.md`, `module_contract.md`, `allowed_dependencies.md`,
  `forbidden_dependencies.md`, `testing_strategy.md`
- canonical cross-cutting contracts:
  [`docs/contracts/`](contracts/)
- explanatory orientation and responsibility maps:
  [`docs/wiki/`](wiki/)
- standards and authoring rules:
  [`docs/standards/`](standards/)

Code-adjacent docs own bounded package responsibility. Repo-wide docs own
cross-package, cross-tool, or cross-repo meaning.

## Responsibility Boundary

MiCyte owns:

- portal authority and capability semantics
- runtime contracts and tool mediation
- cross-domain semantic services
- SQL-backed authority posture
- narrow audited write seams where explicitly approved

MiCyte does not own:

- the host topology it runs on (web server, auth proxy, cache, containers)
- live per-instance state as an authoring surface
- hosted frontend assets as a source repo

A host that deploys MiCyte owns those. MiCyte is the software; a deployment is a
downstream consumer of it — the dependency runs one way.

## Canonical Current Truth

- universal shell/tool posture:
  [`docs/contracts/tool_operating_contract.md`](contracts/tool_operating_contract.md)
- shell composition and routes:
  [`docs/contracts/portal_shell_contract.md`](contracts/portal_shell_contract.md),
  [`docs/contracts/route_model.md`](contracts/route_model.md),
  [`docs/contracts/surface_catalog.md`](contracts/surface_catalog.md)
- addressing and naming:
  [`docs/contracts/datum_document_naming_taxonomy.md`](contracts/datum_document_naming_taxonomy.md)
- vocabulary:
  [`docs/contracts/portal_vocabulary_glossary.md`](contracts/portal_vocabulary_glossary.md)
- structural and mutation posture:
  [`docs/contracts/samras_structural_model.md`](contracts/samras_structural_model.md),
  [`docs/contracts/samras_validity_and_mutation.md`](contracts/samras_validity_and_mutation.md),
  [`docs/contracts/mutation_contract.md`](contracts/mutation_contract.md)
- mediation surface archetype:
  [`docs/contracts/tool_mediation_surface_archetype.md`](contracts/tool_mediation_surface_archetype.md)
