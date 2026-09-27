# Automation routines

The second tool register. A `WorkbenchTool` renders a document for a person; an
`AutomationRoutine` writes one because a condition held.

## Why two registers

The workbench-tool contract presumes a person throughout: a selection to be eligible
against, a route to be reached by, a payload for a renderer. A condition-triggered
writer has none of those, and the previous attempt to cover both from one contract
produced `manipulates_datum_kinds` — a field on the shell tool registry that was
normalized, serialized, and read by nothing for a year. A contract whose second half is
optional grows declarations no code path reaches, because the path that would read them
only exists for the first half.

Here the two kinds cannot be mixed up:

- `micyte.automation.register` refuses anything with `build_panel_payload`, `route`, or
  `applies_to_archetype`.
- `micyte.tools.register` refuses anything with a `routine_id`.
- An architecture test asserts the two id spaces do not intersect.

## The declaration is the request

`AutomationRoutine.writes` is a tuple of `RoutineWrite(document_kind, action,
sandbox_id="")` — an alias for `DeclaredWrite`, which lives with the write policy
because a workbench tool and a port binding declare in the same vocabulary. The
runner builds its
[`DatumWriteRequest`](../ports/datum_write_policy/) objects **out of that tuple** — it
never asks the routine what it intends. So there is no second statement of the same
fact to drift from the first, which is the specific way the field this replaces failed.

`sandbox_id=""` means "the sandbox this run is bound to". It is never `*`: a wildcard is
a value a *grant* may hold. A request that could carry one would satisfy every narrowed
grant it met.

## Order of operations

1. **Authorize every declared write, before evaluating.** A routine may do its whole job
   or none of it. Per-effect authorization after the fact would let a routine that may
   write two documents write one and stop.
2. **Evaluate.** The routine returns a `RoutineDecision` — `fired`, a `reason` (required
   in both directions), and effects.
3. **Apply.** The runner calls the effects; the routine cannot. That is what makes
   `dry_run` truthful rather than a flag the routine is trusted to honour.

An effect whose write was not declared raises `RoutineContractError`. It was never
judged, so it does not run.

## Time

`RoutineContext.now` is supplied by the runner. A routine that reads the clock cannot
be replayed or tested against a boundary — the same reason the nightly refresh's period
selection became a pure function of `now` in Phase 0.

## Identity

A routine's actor id is its own (`automation:<routine_id>` on the FND host). It does not
borrow the operator's, and it is not absent. Its grants are configured like any other
actor's, in `private/config.json` under `datum_write_grants` — so a routine ships
**denied** and becomes able to write when someone says so, in writing.

## The register is empty

On purpose. The first production routine writes live farm data on a schedule; that is
the operator's call. The seam exists so the first one arrives authorized instead of as
another unattended script that identifies itself as nothing.
