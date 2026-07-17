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

### Interface Panel

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
