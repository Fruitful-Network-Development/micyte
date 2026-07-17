# Portal Shell

Authority: [../../../../docs/plans/v2-authority_stack.md](../../../../docs/plans/v2-authority_stack.md)

`packages/state_machine/portal_shell/` owns the shared shell contracts for the
single V2 portal shell:

- serialized shell action
- serialized shell state
- pure shell reducer
- normalized shell result
- one portal shell request and selection model
- one surface catalog rooted in `SYSTEM`, `NETWORK`, and `UTILITIES`
- one tool registry for `SYSTEM` child tool surfaces

This package does not own:

- port calls
- adapter behavior
- runtime composition side effects
- external integration state

Safe tool-surface extension rule:

- Keep tool registry posture metadata aligned to the shared default: `interface_panel_primary` with `default_workbench_visible=false`.
- Put primary tool experience in the `Interface Panel` contract; treat workbench content as secondary evidence that is hidden on first server composition.
- Do not use runtime `workbench.visible` or tool-registry posture fields to create a per-tool first-load exception. Change the shared shell contract, docs, and tests first if tool posture genuinely needs to change.
