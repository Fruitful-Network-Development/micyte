# Portal Shell Refactor Guardrails

## Status

Active

## Purpose

Provide a blocking checklist for one-shell stabilization work so new drift does not enter during refactor.

## Blocking Rules

A refactor PR is blocked if any rule fails:

- introduces a new shell region
- introduces a new shell-level renderer kind for one tool
- adds a first-load posture authority path outside `build_shell_composition_payload()`
- widens shared shell query for CTS-GIS tool-local navigation
- bypasses canonical request/query normalization for a surface

## Required Evidence Per PR

Each shell/tool refactor PR must include:

- explicit link to `docs/contracts/tool_operating_contract.md`
- explicit link to `docs/plans/one_shell_portal_refactor.md`
- contract delta note (or explicit "no contract delta")
- compatibility window and retirement gate when aliases/adapters are introduced

## Required Verification Per PR

At minimum, run:

- `python -m unittest MyCiteV2.tests.unit.test_portal_shell_contract`
- `python -m unittest MyCiteV2.tests.contracts.test_contract_docs_alignment`
- `python -m unittest MyCiteV2.tests.architecture.test_portal_one_shell_boundaries`
- `python -m unittest MyCiteV2.tests.architecture.test_portal_shell_stabilization_matrix`

## Route Matrix Scope

The shell-boundary route matrix must stay covered for:

- `/portal/system`
- `/portal/system/tools/aws-csm`
- `/portal/system/tools/cts-gis`
- `/portal/system/tools/fnd-dcm`
- `/portal/system/tools/workbench-ui`
- `/portal/network`
- `/portal/utilities`

## Merge Gate

Do not merge stabilization-impacting shell/tool changes without:

- guardrail checklist satisfied
- matrix tests green
- contract and plan references updated in the same PR
