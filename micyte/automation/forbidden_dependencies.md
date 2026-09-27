# Forbidden Dependencies

- `micyte/adapters/` — a routine receives its store through `RoutineContext.resources`;
  the runner never constructs one.
- `micyte/tools/` — the two registers are siblings, not layers.
- `micyte/state_machine/` — routes, surfaces and shell state are the UI half of the
  taxonomy and have no meaning here.
- `packages/sandboxes/`, `instances/` — host concerns.
