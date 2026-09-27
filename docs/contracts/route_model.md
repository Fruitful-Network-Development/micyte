# Route Model

> **MOS-authority rule:** All routes that read datum documents do so via
> the MOS authority database, never the filesystem. See
> [`mos_authority_enforcement.md`](mos_authority_enforcement.md).

Canonical visible routes:

- `/portal`
- `/portal/system`
- `/portal/system/tools/<tool_slug>`
- `/portal/system/tools/workbench-ui`
- `/portal/network`
- `/portal/network/browser`
- `/portal/network/p2p`
- `/portal/utilities`
- `/portal/utilities/tools`
- `/portal/utilities/apps`
- `/portal/utilities/ports`
- `/portal/utilities/peripherals`
- `/portal/utilities/contracts`
- `/portal/utilities/published`

The three `/portal/network*` routes are gated on `host_config.network_enabled`. With the
module off they return **404**, not a disabled page. The Utilities holdings are platform
surfaces and are NOT gated (see `test_network_enabled_flag`).

Removed in TASK-2026-08-14-002 Phase 1: the legacy `tool-exposure` / `extensions` /
`grantee-profile` / `integrations` 302 redirects ("for one cycle", June), and the
`libraries` / `view-packages` / `datum-packages` stub shelves, replaced by `apps`.
An unknown `/portal/utilities/*` path now 404s.

`/portal` is the canonical public entry and redirects to `/portal/system`.

`/portal/system` opens the SYSTEM datum-file workbench. Its fresh reducer-owned entry projects the system sandbox anchor file, `anthology.json`.

For migrated portals, the authoritative `SYSTEM` datum/workbench/profile/grant posture is resolved from the MOS authority database. Missing or uninitialized SQL authority is a readiness failure rather than a filesystem fallback for those migrated surfaces.

`/portal/network` opens the read-only NETWORK system-log workbench. Its canonical operational document is `data/system/system_log.json`. Contract correspondence is selected as a filter over the same document rather than through peer tabs or child routes.

Former dedicated activity and profile-basics leaf pages are gone. Those views now project through `/portal/system` workspace state with `file=activity` and `file=profile_basics`.

Canonical shell API:

- `POST /portal/api/v2/shell`

Direct APIs:

- `POST /portal/api/v2/system/workspace/profile-basics`
- `POST /portal/api/v2/system/tools/workbench-ui`
- `POST /portal/api/utilities/publish`

The `aws-csm`, `cts-gis`, `fnd-dcm` and `fnd-ebi` tool endpoints listed here previously do not
exist. Those surfaces were retired — see `surface_catalog.md`, "Retired surfaces".

Canonical shared mutation lifecycle APIs:

- `POST /portal/api/v2/mutations/stage`
- `POST /portal/api/v2/mutations/validate`
- `POST /portal/api/v2/mutations/preview`
- `POST /portal/api/v2/mutations/apply`
- `POST /portal/api/v2/mutations/discard`

Reducer-owned query projection keys:

- `file`
- `datum`
- `object`
- `verb`

Reducer-owned canonical query rules:

- fresh `SYSTEM` entry projects `file=anthology&verb=navigate`
- sandbox-management view projects `file=sandbox&verb=navigate`
- reducer-owned tool pages reuse the same query keys, but runtime remains the source of truth

Within `file=anthology`, the workbench may render layered datum-table groupings and a selected-datum detail lens, but those are projections of the same reducer-owned SYSTEM state.

Runtime returns the canonical route and canonical query projection in every reducer-owned envelope. The browser updates history only from that runtime-returned canonical URL.

`Workbench UI` is one `SYSTEM` child SQL authority-inspection surface. The canonical public route is `/portal/system/tools/workbench-ui`.

It does not replace `/portal/system`, and it does not imply coverage of retained host-bound/private assets or `NETWORK` derived materializations.

Workbench UI query projection keys:

- `document`
- `document_filter`
- `document_sort`
- `document_dir`
- `filter`
- `sort`
- `dir`
- `group`
- `workbench_lens`
- `source`
- `overlay`
- `row`

Workbench UI canonical query rules:

- fresh `Workbench UI` entry takes the first available authoritative document in the current document-table ordering (it used to prefer a `sandbox:cts_gis:*` document; that sandbox no longer exists); the default fresh query projects `document_sort=version_hash&document_dir=asc&sort=datum_address&dir=asc&group=flat&workbench_lens=interpreted&source=show&overlay=show`, plus the first selected row from that resolved document
- `document=<document_id>` selects one SQL-backed authoritative document
- `document_filter=<text>` narrows the read-only document table by `document_id`, `document_name`, `source_kind`, or `version_hash`
- `document_sort=<document_id|document_name|source_kind|row_count|version_hash>` changes document-table ordering
- `document_dir=<asc|desc>` changes document-table order direction
- `filter=<text>` narrows the selected-document row grid, including `hyphae_hash`
- `sort=<datum_address|layer|value_group|iteration|labels|relation|object_ref|hyphae_hash>` changes flat row-grid ordering
- `dir=<asc|desc>` changes row-grid order direction
- `group=<flat|layer|layer_value_group|layer_value_group_iteration>` switches the datum grid between flat, grouped, and layer/value-group/iteration matrix modes while preserving canonical structural order
- `workbench_lens=<interpreted|raw>` switches the workbench between the interpreted row summary and the raw canonical payload lens
- `source=<show|hide>` toggles source metadata columns and sections without changing authoritative rows
- `row=<datum_address>` focuses one selected row in the read-only Interface Panel detail view
- `overlay=hide` suppresses additive directive summaries without changing authoritative row content
- keyboard navigation and next/previous selection actions stay query-driven by resolving to canonical `document` and `row` selections rather than adding new navigation keys

NETWORK root query projection keys:

- `view`
- `contract`
- `type`
- `record`

NETWORK root canonical query rules:

- fresh `NETWORK` entry projects `view=system_logs`
- `contract=<contract_id>` narrows the same workbench to contract correspondence
- `type=<event_type_id>` narrows the same workbench to one event type
- `record=<datum_address>` focuses one log row in the read-only Interface Panel detail view

`network.root` is not a tool and not a sandbox.

The NETWORK page's two other tabs are separate routes, not query state on the root:

- `/portal/network/browser` — the `msn_id` browser. Query keys: `mode` (`cached`|`linked`),
  `region` (a gazetteer node), `node` (an `msn_id`). `mode` is a REQUEST, not a setting: it can
  always fall back to cached, and it can never grant linked — an ungated request returns the
  reason it was refused rather than being silently downgraded.
- `/portal/network/p2p` — channel state. No transport is wired.

There is still no Messages/Hosted/Profile/Contracts child-tab model on the root: held contracts
live under `/portal/utilities/contracts`, and publication under `/portal/utilities/published`.
