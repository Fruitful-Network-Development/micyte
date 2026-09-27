# MiCyte

The `mycite-core` repository is the canonical source for **MiCyte** — the
MOS-centric portal shell and datum operating environment (Mycelial Ontological
Schema) — and its authoritative documentation tree. (The repository, the
`fnd_app/` package directory, the `/srv/webapps/mycite/` runtime paths and the
`mycite.v2.*` wire schemas still carry the pre-rebrand `mycite` spelling; those
are infrastructure/protocol identifiers whose rename is a separate migration, not
a brand fix.) FND Grantee Services (the `/__fnd` dashboards) is the downstream
application built on the same core; the dependency runs one way, FND → MiCyte.

## Runtime Boundaries

- V2 repo code lives under `/srv/repo/mycite-core/fnd_app`
- preserved deployment snapshots live under `/srv/repo/mycite-core/deployed`
- Live instance state (gitignored runtime bubbles) lives under `/srv/webapps/mycite/<instance_id>/`
- Migrated `SYSTEM` authority surfaces are SQL-backed through per-instance MOS authority databases such as `deployed/fnd/private/mos_authority.sqlite3`
- Host-bound private/public assets and `NETWORK` derived materializations remain explicit retained exceptions outside SQL datum authority

## Portal Architecture

- one portal shell
- canonical public entry: `/portal` -> `/portal/system`
- one runtime envelope family
- root surfaces: `SYSTEM`, `NETWORK`, `UTILITIES`
- `SYSTEM` owns the core datum-file workbench for the system sandbox
- fresh `SYSTEM` entry focuses the anchor file `anthology.json`
- `NETWORK` owns the read-only portal-instance system-log workbench backed by `data/system/system_log.json`
- `NETWORK` is not a tool and not a sandbox; contract correspondence is a filter over the same workbench
- canonical shell endpoint: `POST /portal/api/v2/shell`
- canonical tool work pages: `/portal/system/tools/<tool_slug>`
- canonical SQL datum-grid tool: `/portal/system/tools/workbench-ui`
- canonical AWS service tool: `/portal/system/tools/aws-csm`
- canonical FND-DCM service tool: `/portal/system/tools/fnd-dcm`
- migrated `SYSTEM` shell/runtime posture is SQL-authoritative and fail-closed when the authority DB is missing or uninitialized
- `AWS-CSM` is one `SYSTEM` child service tool with a unified domain gallery, user-email gallery, onboarding section, and newsletter section
- `FND-DCM` is one `SYSTEM` child service tool for hosted manifest inspection and normalization across profile-led webapps
- `workbench_ui` is one `SYSTEM` child read-only tool for the two-pane spreadsheet-like SQL authority lens, row-level `hyphae_hash` review, and additive directive overlay summaries
- `workbench_ui` does not replace `/portal/system`; it remains scoped to authoritative SQL-backed documents rather than all deployed files
- service-tool posture comes from required capabilities and peripheral employment, not from portal identity or portal types
- shell chrome is one `ide-shell` split into `ide-menubar` and `ide-body`, with `Activity Bar`, `Control Panel`, `Workbench`, and `Interface Panel` as peer regions
- utilities/configuration pages: `/portal/utilities/*`

## Key Entry Points

- V2 portal host: `fnd_app/instances/_shared/portal_host/app.py`
- V2 runtime catalog: `fnd_app/instances/_shared/runtime/runtime_platform.py`
- V2 shell runtime: `fnd_app/instances/_shared/runtime/portal_shell_runtime.py`
- V2 shell contract: `micyte/state_machine/portal_shell/shell.py`
- archived snapshot material: `deployed/README.md`

## Canonical Docs

- [`docs/README.md`](docs/README.md)
- [`docs/contracts/portal_shell_contract.md`](docs/contracts/portal_shell_contract.md)
- [`docs/contracts/route_model.md`](docs/contracts/route_model.md)
- [`docs/contracts/surface_catalog.md`](docs/contracts/surface_catalog.md)
- [`docs/contracts/fnd_dcm_tool_contract.md`](docs/contracts/fnd_dcm_tool_contract.md)
- [`docs/contracts/fnd_dcm_manifest_conventions.md`](docs/contracts/fnd_dcm_manifest_conventions.md)
- [`docs/contracts/portal_vocabulary_glossary.md`](docs/contracts/portal_vocabulary_glossary.md)
- [`docs/plans/one_shell_portal_refactor.md`](docs/plans/one_shell_portal_refactor.md)
- [`docs/plans/master_plan_mos.md`](docs/plans/master_plan_mos.md)
- [`docs/audits/reports/mos_program_closure_report_2026-04-21.md`](docs/audits/reports/mos_program_closure_report_2026-04-21.md)
