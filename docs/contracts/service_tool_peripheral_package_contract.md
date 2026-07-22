# Service Tool Peripheral Package Contract

Version: 1.0
Date: 2026-05-11
Reference implementation: FND-CSM (`portal_fnd_csm_runtime.py`)

> **MOS-authority rule:** The "Data authority: MOS SQL authority
> (SAMRAS) vs Filesystem peripheral data" distinction is bound by the
> enforcement contract at
> [`mos_authority_enforcement.md`](mos_authority_enforcement.md). Only
> non-datum peripheral data (e.g. tool profiles, vault inventories) may
> live on the filesystem; datum documents always live in MOS.

---

## Overview

A **service tool** is a portal tool whose primary operation is external service management
(email, analytics, payments, subscriptions) rather than spatial datum mediation. Service tools
differ from general tools (CTS-GIS) in posture, workbench visibility, and data sources.

This contract specifies what every service tool's Python runtime and JS workspace must satisfy.

---

## 1. Service Tool vs General Tool

| Aspect | General Tool (CTS-GIS) | Service Tool (FND-CSM) |
|---|---|---|
| `tool_kind` | `TOOL_KIND_GENERAL` | `TOOL_KIND_SERVICE` |
| Primary surface | Reflective workspace (diktataograph) | Interface panel (tabbed component frames) |
| Workbench visibility | Visible (datum navigation) | Hidden by default (`visible=False`) |
| Data authority | MOS SQL authority (SAMRAS) | Filesystem peripheral data |
| Surface posture | `SURFACE_POSTURE_WORKSPACE_PRIMARY` | `SURFACE_POSTURE_INTERFACE_PANEL_PRIMARY` |

The `tool_kind` and `surface_posture` are set in `PortalToolRegistryEntry` in `shell_registry.py`.

---

## 2. Required Surface Payload Shape

The `surface_payload` emitted by the bundle builder must include:

```python
{
    "schema": "{tool_id}.surface.v1",          # e.g. "mycite.v2.portal.system.tools.fnd_csm.surface.v1"
    "kind": "tool_mediation_surface",
    "tool_id": str,                            # stable tool identifier, e.g. "fnd_csm"
    "surface_id": str,                         # e.g. "system.tools.fnd_csm"
    "entrypoint_id": str,                      # e.g. "portal.system.tools.fnd_csm"
    "title": str,
    "subtitle": str,
    "tool": {
        "tool_id": str,
        "label": str,
        "summary": str,
        "configured": bool,                    # True if tool is configured in tool_exposure_policy
        "enabled": bool,                       # True if tool is enabled in tool_exposure_policy
        "operational": bool,                   # True if configured + enabled + capabilities met
        "missing_capabilities": list[str],
    },
    "tool_state": dict,                        # Normalized tool state (see §4)
    "action_result": dict,                     # {} or { "action_kind", "status", "message" }
    "request_contract": {                      # Required (see §3)
        "schema": str,
        "action_schema": str,
        "route": str,
        "action_route": str,
        "surface_id": str,
    },
}
```

---

## 3. Request Contract

Every `surface_payload` must embed a `request_contract`:

```python
"request_contract": {
    "schema": FND_CSM_TOOL_REQUEST_SCHEMA,
    "action_schema": FND_CSM_TOOL_ACTION_REQUEST_SCHEMA,
    "route": FND_CSM_TOOL_ROUTE,              # e.g. "/portal/system/tools/fnd-csm"
    "action_route": FND_CSM_TOOL_ROUTE + "/actions",
    "surface_id": FND_CSM_TOOL_SURFACE_ID,
}
```

**Rule**: The JS workspace reads `route`, `action_route`, `schema`, and `action_schema`
exclusively from this contract. No hardcoded URL strings or schema IDs in JS workspace files.

---

## 4. Tool State Schema

The normalized tool state dict must satisfy:

| Field | Type | Semantics |
|---|---|---|
| `active_tab` | `str` | Active tab ID; defaults to first tab if empty |
| `engaged_frame_id` | `str` | Transient; names frame to force re-render this cycle |

Service-tool-specific fields are added as needed (FND-CSM adds `selected_grantee_msn`,
`selected_domain`).

**Normalization function signature:**
```python
def _normalize_{tool_id}_tool_state(request_payload: dict[str, Any]) -> dict[str, Any]:
    tool_state = _as_dict(request_payload.get("tool_state"))
    return {
        "active_tab": _as_text(tool_state.get("active_tab")) or "email",
        "engaged_frame_id": _as_text(tool_state.get("engaged_frame_id")),
        # ...tool-specific fields...
    }
```

**`engaged_frame_id` lifecycle:**
1. Normalized from incoming `tool_state` at the start of the build cycle.
2. **Popped** from `tool_state` before frame building:
   `engaged_frame_id = _as_text(tool_state.pop("engaged_frame_id", ""))`
3. Passed to frame builders to produce an `::engaged` render_key suffix for the targeted frame.
4. Does **not** persist to `surface_payload.tool_state`.

All fields must use stable string keys. Do not derive field names from external data.

---

## 5. Interface Panel: Tab Host Contract

The interface panel region must declare:

```python
{
    "tab_host": "shared_interface_tabs",
    "default_tab_id": active_tab,
    "tabs": [
        {
            "id": "email",               # Stable tab identifier
            "label": "Email",            # Display string
            "initializer": {
                "verb": "mediate",
                "target_authority": "{tool_id}",   # e.g. "fnd_csm"
                "intent": "resolve_email_profile",  # Stable intent string
            },
        },
        ...
    ],
    "component_frames": [...],           # See §6
}
```

**Initializer semantics:**
- The `initializer` is **server-side metadata only**. It tells the server which mediation
  operation to perform when rebuilding a tab's frames during re-engagement.
- The client does **not** fire initializers independently.
- Tab switching dispatches `select_tab` (a tool action) to update `active_tab` in tool state.
- Frame re-engagement dispatches `engage_component_frame` (a tool action) to update
  `engaged_frame_id` in tool state, which causes the targeted frame to receive a fresh
  render_key on the next build cycle.

---

## 6. Interface Panel: Component Frame Layout

The `component_frames` list must conform to `interface_panel_component_frame_contract.md`.

For service tools, the standard layout is:
- **One `component_group` frame per tab** (frame_id convention: `{tool_id}.tab.{tab_id}`)
- Each group contains **child frames** appropriate to that tab's content:
  - `characteristic_set` — labeled key-value pairs (entity summary, config values)
  - `listing` — tabular data (events, orders, contacts)
  - `profile` — full entity profile (if applicable)

**Frame builders** from `micyte/state_machine/nimm/mediate_handlers.py`:

| Builder | Use case |
|---|---|
| `build_component_group_frame()` | Tab container |
| `build_characteristic_set_component_frame()` | Labeled key-value display |
| `build_listing_component_frame()` | Tabular rows with columns |
| `build_profile_component_frame()` | Entity profile with field groups |

All builders accept `target_authority: str = "cts_gis"` — service tools must pass
`target_authority="{tool_id}"` to ensure the initializer spec is accurate.

**Render key format:**
```
"{stable_scope}::{frame_id}::{version_token}"
```

For FND-CSM, the stable scope is `"{grantee_msn}::{domain}"`. The version token is
`""` for normal renders and `"::engaged"` when `engaged_frame_id` matches the frame.

When the grantee or domain changes, the render_key changes for all frames, causing full
re-render. When `engage_component_frame` is dispatched for one frame, only that frame's
render_key changes; sibling frames are cache-hits.

---

## 7. Action Dispatch Model

Service tools use the **tool action pattern** (not NIMM directive envelopes):

```
POST {action_route}
Body: {
    schema: action_schema,
    action_kind: str,
    action_payload: dict,
    tool_state: dict,
}
```

**Standard action kinds** every service tool must handle:

| Action kind | Effect |
|---|---|
| `select_tab` | Set `active_tab` in tool state |
| `engage_component_frame` | Set `engaged_frame_id`; force re-render of named frame |

Service-tool-specific action kinds are documented per tool.

**Action result** is always returned in the next surface_payload:
```python
"action_result": {
    "action_kind": str,
    "status": "accepted" | "rejected" | "error",
    "message": str,
}
```

**Dispatch boundary rule:** Use tool actions for all operations that stay within the current
surface and tool context. Use NIMM directive envelopes only for operations that change the
active surface, AITAS context, or trigger authority mutations.

See `interface_panel_component_frame_contract.md §Component Dispatch Patterns` for the full
boundary specification.

---

## 8. Workbench Region

Service tools hide the workbench by default:

```python
workbench = build_datum_file_workbench(
    portal_scope=portal_scope,
    shell_state=shell_state,
    surface_id=TOOL_SURFACE_ID,
    sandbox_id="tool-slug",
    sandbox_label="Tool Label",
    anchor_document=None,
    sandbox_documents=[],
    title="...",
    subtitle="...",
    visible=False,           # Required: service tools are interface-panel-primary
)
```

The `workbench.family_contract` must be present (produced by `attach_region_family_contract`
inside `build_datum_file_workbench`). The JS workspace renderer for the reflective workspace
region still receives a valid region dict; it renders a grantee/domain selector or equivalent
control area.

---

## 9. Peripheral Data Source Pattern

Service tools operate against filesystem data outside the MOS SQL authority.

**Standard tool data path:**
```
{private_dir}/utilities/tools/{tool-slug}/
```

**Grantee profile format** (for FND-managed service tools):
```json
{
    "schema": "mycite.v2.grantee.profile.v1",
    "msn_id": "<grantee_samras_msn_id>",
    "label": "Display Name",
    "short_name": "ABBR",
    "domains": ["example.com"],
    "users": ["info@example.com"]
}
```

File naming convention:
```
grantee.{fnd_msn}.{grantee_msn}.json
```

`domains` drives analytics and contact log path resolution.
`users` provides the candidate list for service assignments (e.g., newsletter sender).

Each tool documents its own additional data source files in its tool-specific contract.

**FND-CSM data sources:**
- Grantee profiles: `{private_dir}/utilities/tools/fnd-csm/grantee.*.json`
- AWS-CSM tool profiles (email): resolved by `FilesystemAwsCsmToolProfileStore`
- Newsletter contact logs: `{private_dir}/utilities/tools/aws-csm/newsletter/newsletter.{domain}.contacts.json`
- PayPal orders: `{private_dir}/utilities/tools/paypal-csm/orders.ndjson`
- Webhook config: `{private_dir}/utilities/tools/fnd-csm/paypal-webhook.{msn_id}.json`
- Analytics events: `{webapps_root}/clients/{domain}/analytics/events/*.ndjson`

---

## 10. Capability Requirements

Service tools that manage FND-managed services require the `fnd_peripheral_routing`
capability:

```python
PortalToolRegistryEntry(
    tool_id="fnd_csm",
    ...
    required_capabilities=("fnd_peripheral_routing",),
)
```

The bundle builder checks capabilities and sets `tool.operational = False` if any required
capability is missing from `portal_scope.capabilities`. The tool renders a non-operational
state to the user rather than silently failing.

---

## Reference Implementation

FND-CSM satisfies all sections of this contract:

| Component | File |
|---|---|
| Bundle builder | `fnd_app/instances/_shared/runtime/portal_fnd_csm_runtime.py` |
| JS workspace | `fnd_app/instances/_shared/portal_host/static/v2_portal_fnd_csm_workspace.js` |
| Frame builders | `micyte/state_machine/nimm/mediate_handlers.py` |
| Shell constants | `micyte/state_machine/portal_shell/shell_schemas.py` |
| Shell registry | `micyte/state_machine/portal_shell/shell_registry.py` |
| Tests | `fnd_app/tests/unit/test_portal_fnd_csm_runtime.py` |
