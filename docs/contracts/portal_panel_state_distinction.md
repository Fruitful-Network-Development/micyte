# Portal Panel State Distinction

## Status

Canonical

## Purpose

Define the functional distinction between the three portal panels — workbench, interface,
and control — with respect to AITAS state and the spatial value. This contract prevents
conflation of navigation (which changes spatial state) and mediation (which reads context
without changing spatial state).

This contract is upstream of:

- `docs/contracts/interface_panel_component_frame_contract.md`
- `docs/contracts/cts_gis_garland_projection_lens.md`

---

## The Three Panels

### Workbench Panel

The workbench panel **materializes the datum at the current AITAS spatial position**.

- It shows the raw MOS-backed datum document (or file, or sandbox) that the focus_path points to.
- Navigation directives (NAV buttons, terminal `nav` commands) change the focus_path → spatial
  value changes → workbench re-renders the newly focused datum.
- Example spatial values and what the workbench shows:
  - `cts-gis` → tool sandbox contents (list of documents)
  - `tool.1-2-3-4-5-6-7-8-9-0.cts-gis` → the tool anchor document's datum table
  - `tool.1-2-3-4-5-6-7-8-9-0.cts-gis / 1-1-2` → the `1-1-2` datum row's content

The workbench does not interpret the data — it materializes it.

#### The workbench is the only foreground region (2026-08-16)

There is no overlay layer. Tools, app hubs, the AGNET channel and the datum cell editor all
render INSIDE the workbench, and the two overlay hosts (`#portalToolOverlay`,
`#portalDatumOverlay`) are retired.

This is a statement about state, not about layout. An overlay's open-ness lived only in the
client: it had no query key, so it could not be bookmarked, shared, reloaded onto, or
returned to with the back button — the one part of the shell whose position was not a
value. Folding those surfaces into the workbench puts them back under the same rule as
every other spatial value: **the address names what is on screen**.

The Compendium is the same rule applied to the datum corpus itself. Its three levels —
sandbox shelf, document gallery, document face — are the spatial value at three depths, and
each is a query the operator can hold onto (`sandbox_filter`, `document`, `doc_view`).

### Interface Panel

> **Retired as a REGION.** `shell_composition` emits `activity_bar` and `workbench` only.
> The mediation role below is still real and still performed — it now renders as workbench
> content (a tool host, or a document's scope face) rather than in a third column. Read
> this section for the distinction it draws, not for the layout it assumes.

The interface panel **returns mediation output with respect to the current AITAS state**.

- It queries profiles, geometry, projections, and structural correlations using the attention
  node as context.
- It does **NOT** change the AITAS spatial value. Mediation reads context; it does not navigate.
- The garland tab on the CTS-GIS interface panel mediates on anchor datum `1-1-2` to resolve
  the profile correlated to the current attention node. This is reference resolution — not
  navigation to `1-1-2`.
- Multiple component frames on the interface panel may each mediate with respect to different
  facets of the current state without any of them changing the spatial value.

### Control Panel

> **Retired as a REGION (2026-08-16).** `shell_composition.regions` is exactly
> `{activity_bar, workbench}`. The measurement that ended it: under 960px the CSS made
> `#portalControlPanel` a fixed drawer pinned over the workbench, and the menubar clipped
> the one toggle that could close it — so the portal could not be used from a phone at
> all. What the panel carried that was a real fact about a surface now travels WITH that
> surface: Sources with the sandbox (`compendium.sources`), section nav with the page
> (`surface_payload.section_nav`), the log filters with the log table
> (`surface_payload.selection_strip`), the install target with the marketplace
> (`surface_payload.install_target`). What it carried that was NOT — a Directive Terminal
> disabled on every instance, a lens readout with no toggle, a state reflection of what
> the canonical query already says, an identity row the menubar repeats — is gone.
> The distinction the section draws is still true; the column it assumes is not.

The control panel **exposes state machine controls**: verb tabs, operation selectors, navigation
arrows, the directive terminal, and context condition rows.

- It reflects the current AITAS state (attention, intention, time, archetype) and provides
  affordances to change it via shell requests.
- Verb changes (NAV/INV/MED/MAN) update intention but not the spatial focus_path.
- Navigation arrows fire NAV directives that update focus_path (spatial value changes).

---

## AITAS Structure

```
AITAS = {
  attention:  <msn_id focus, e.g. "3-2-3-17">,
  intention:  <navigate | investigate | mediate | manipulate>,
  time:       <current | time_context_token>,
  archetype:  <tool mode, e.g. "system_workspace">
}
```

The **spatial value** (focus_path) is separate from AITAS attention. AITAS attention identifies
_what_ the state machine is attending to (a node in the SAMRAS tree). The spatial value
identifies _where_ in the datum file system the shell is focused.

---

## The Mediation Distinction

When the garland tab initializes with directive `med; target=cts_gis; datum=1-1-2`:

- This is **not** a navigation to `1-1-2`.
- The spatial value remains: `tool.1-2-3-4-5-6-7-8-9-0.cts-gis` (or wherever the shell is focused).
- The mediation directive reads `1-1-2` as a **reference authority** — the msn-SAMRAS magnitude
  bitstream — to determine the structural context of the current attention node.
- The output is a profile payload for the attention node. The spatial value is unchanged.

In plain terms: **mediate uses a datum as a lens; navigate moves to a datum**.

---

## Panel Isolation During Panel Switching

When the user toggles from the interface panel to the workbench panel:

1. The AITAS spatial value is unchanged.
2. The workbench re-renders to show the datum at the current spatial position.
3. The interface panel's component frames are frozen in client-side state (see
   `interface_panel_component_frame_contract.md`).

When the user toggles back to the interface panel:

1. Frozen frames are re-displayed from the client-side registry — no server re-fetch.
2. The spatial value is still unchanged.
3. If the attention node changed while on the workbench panel (via navigation), frames
   whose `render_key` includes the attention node will have a mismatched key on the next
   surface render, and will re-render with the new attention context.

---

## Why the Spatial Value Does Not Change on the Interface Panel

The interface panel's mediation directives operate **laterally** — they evaluate relationships
and projections from the current state without descending into the datum tree. This is
architecturally required because:

1. The workbench panel must remain coherent as a "view of the current datum". If interface
   panel actions changed the spatial value, the workbench would lose its current position.
2. The garland tab may reference multiple source datums (e.g., `1-1-2` for SAMRAS structure,
   profile source files for geometry) without "navigating to" any of them.
3. Component frames are independent — multiple frames may each reference different datums as
   authorities without creating navigation conflicts.

---

## Concrete Example: CTS-GIS Garland Tab

State at the moment the garland tab is activated:

```
spatial:   tool.1-2-3-4-5-6-7-8-9-0.cts-gis
attention: 3-2-3-17
intention: mediate
time:      current
```

Garland tab initialization (runs server-side, does not change spatial):

1. Mediate on `1-1-2` (msn-SAMRAS magnitude) → decode tree → find node `3-2-3-17`.
2. Resolve correlated profile source document for node `3-2-3-17`.
3. Extract: label ("Ohio"), msn_id ("3-2-3-17"), feature_count, child_count.
4. Resolve geospatial projection from profile's HOPS geometry rows.
5. Return: `profile` component frame (with `geospatial_projection` subject_slot).

After initialization:

```
spatial:   tool.1-2-3-4-5-6-7-8-9-0.cts-gis   ← unchanged
attention: 3-2-3-17                                 ← unchanged
```

User toggles to workbench panel:

```
workbench shows: datum table for tool.1-2-3-4-5-6-7-8-9-0.cts-gis
```

User navigates out (back_out):

```
spatial:   cts-gis                                  ← changed by NAV
workbench shows: sandbox contents of cts-gis
```

User toggles back to interface panel:

```
garland profile frame: still frozen at Ohio (3-2-3-17) → cached HTML reused
```

If user re-engages the profile frame:

```
Mediation re-runs for new attention (if attention changed) or same Ohio profile.
```

---

## Non-Goals

- This contract does not define NIMM verb semantics in full. See `nimm/directives.py` and
  the NIMM grammar for complete definitions.
- This contract does not govern workbench mutation (YAML staging, apply). See
  `portal_datum_workbench_mutation_runtime.py` and the datum edit task.
