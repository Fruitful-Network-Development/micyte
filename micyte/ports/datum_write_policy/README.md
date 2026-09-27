# Datum Write Policy Port

`micyte/ports/datum_write_policy/` owns the seam that answers one question:

> may **this actor**, acting through **this tool**, perform **this action** on
> **this kind of document** in **this sandbox**?

## Why it is a port and not a helper

Before this existed there was no single place that saw both *who is writing* and
*what is being written*. The tool registry already declared
`manipulates_datum_kinds` and `required_capabilities` per tool, and the instance
config already carried a `tool_exposure` policy — but all three were read only to
render a status row. A tool an operator had switched off still executed, and the
domain write routes took the target sandbox straight from the request body.

That is survivable while the only writer is a person clicking in a portal they
already had to authenticate into. It stops being survivable the moment a *port*
(a payment provider callback, a POS) or an unattended writer (a scheduled
inventory entry) writes on someone's behalf, because then "the caller" and "the
person the write is for" are different, and only one of them is present.

## Contract

- `DatumWriteRequest` — actor, tool, sandbox, document kind, action. Every field
  is required; a blank one raises rather than being treated as a wildcard.
- `DatumWriteGrant` — what one actor may do. Each dimension defaults to `ANY`
  explicitly, so a narrowed grant is visibly narrowed.
- `require_datum_write(request, grants=...)` — returns silently or raises
  `DatumWriteDenied`. No permissive mode; an empty grant set denies.

## What replaced what

`manipulates_datum_kinds` was removed from `PortalToolRegistryEntry` by the Phase 3
tool taxonomy rather than wired up to this port. It was a per-tool label saying which
document kinds a tool might write; a label beside the write path is a second statement
of the same fact, and the two drift — this one drifted all the way to being read by
nothing. The question now gets asked at the write, where it can be refused.

For an unattended writer the same fact is stated once and only once:
[`micyte/automation`](../../automation/) routines declare their writes, and the runner
builds the `DatumWriteRequest` objects out of that declaration. A routine cannot widen
its own scope because it is never consulted about it.

`required_capabilities` stays — it answers a different question (does this instance's
authority scope support the tool at all) and it is read, by the Utilities tool catalog.

## Not owned here

Grant storage, actor authentication, and the meaning of a document kind in any
domain. Those belong to the host. This module owns only the question and the
answer, the way `micyte/core/crypto/channel.py` owns the refusal and not the
cipher.
