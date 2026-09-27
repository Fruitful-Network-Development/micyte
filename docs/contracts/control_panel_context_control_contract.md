# Control Panel Context Control Contract

## Status

**RETIRED 2026-08-16.** The `control_panel` region was removed by operator directive;
`shell_composition.regions` is now exactly `{activity_bar, workbench}`. Nothing builds
`nimm_aitas_control.context_controls` and nothing renders it. The builders behind the
`spatial` and `attention` controls (`_nimm_navigation_shell_requests`, `_verb_tab_entries`,
`_system_context_items`) were deleted on 2026-08-17.

Kept as the record of a shape that shipped, not as something to implement against. What
the panel carried that was worth keeping moved rather than died — see
`surface_catalog.md` for where each capacity landed (Sources onto the Compendium's level 1,
Utilities sections onto `section_nav`, Network selection onto `selection_strip`, the app
install target onto `install_target`, and the sandbox `<select>` onto the level-0 shelf).

The five canonical controls below were never all backed: `archetype` shipped as a disabled
shell, and the Directive Terminal reported `directive_terminal_not_enabled` on every
instance for the whole life of the region.

## Original specification (historical)

Draft, additive.

## Purpose

Define the modular NIMM-AITAS context controls projected by the unified control panel.
The shape is additive to `nimm_aitas_control.facets` so existing directive-panel payloads
and renderers can continue to function while migrated panels use the five canonical controls.

## Schema

`nimm_aitas_control.context_controls[]` is an ordered list:

```json
{
  "context_id": "<attention | intention | time | archetype | spatial>",
  "label": "<display label>",
  "current_value": "<context value>",
  "control_type": "<select | stepper | directional | disabled>",
  "options": [
    { "label": "<string>", "value": "<string>", "active": false, "action": {}, "shell_request": {} }
  ],
  "controls": [
    { "label": "<string>", "control_id": "<string>", "action": {}, "shell_request": {}, "disabled": false }
  ],
  "empty_message": "<string, optional>"
}
```

## Canonical Controls

- `attention`: select control backed by available attention node requests.
- `intention`: stepper control backed by previous/next intention requests.
- `time`: directional control backed by current/timeframe requests.
- `archetype`: select control; may be a disabled shell until archetype switching is implemented.
- `spatial`: directional control backed by NIMM navigation shell requests.

## Renderer Rules

- Render terminal input before the stacked context controls.
- Render all five controls even when a backing source is absent; missing backing becomes a
  disabled control shell with `empty_message`.
- Do not infer transitions in the browser. Buttons and selects dispatch only the supplied
  `action` or `shell_request`.
- Existing `facets` remain a fallback/diagnostic projection during migration.
