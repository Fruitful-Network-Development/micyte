"""Automation-routine registry — a list, and the refusals that keep it one kind of thing.

Mirrors :mod:`micyte.tools._registry` in shape so the two registers read the same way.
It differs in one respect on purpose: registration REFUSES a renderer. The taxonomy is
only worth having if it is enforced somewhere, and the cheapest somewhere is the door.
"""

from __future__ import annotations

from micyte.ports.external_call_policy import DeclaredCall

from ._contract import AutomationRoutine, RoutineContractError, RoutineWrite

# routine_id -> AutomationRoutine instance.
ROUTINE_REGISTRY: dict[str, AutomationRoutine] = {}

# Attributes that mean "this is a UI tool". A routine carrying any of them was
# written against the wrong contract, and the useful moment to say so is now
# rather than when a scheduler calls a method that does not exist.
_RENDERER_ATTRIBUTES = ("build_panel_payload", "route", "applies_to_archetype")


def register(routine: AutomationRoutine) -> AutomationRoutine:
    """Add a routine to the registry, or raise. Returns the routine for fluent use."""
    # Checked before the shape gate: a channel does not satisfy the routine
    # protocol either, and the useful refusal names WHERE the thing belongs
    # rather than which members it lacks.
    if hasattr(routine, "channel_id"):
        raise RoutineContractError(
            f"{getattr(routine, 'channel_id', '?')!r} declares channel_id: an "
            "outward-facing session surface belongs in micyte.channels. A channel "
            "writes nothing, so there is nothing here to schedule or authorize."
        )
    if not isinstance(routine, AutomationRoutine):
        raise RoutineContractError(
            f"register() expected an AutomationRoutine, got {type(routine).__name__}"
        )
    for attribute in _RENDERER_ATTRIBUTES:
        if hasattr(routine, attribute):
            raise RoutineContractError(
                f"{routine.routine_id!r} declares {attribute!r}: a routine renders "
                "nothing and is offered to nobody. Register a WorkbenchTool in "
                "micyte.tools, or drop the UI attribute."
            )
    routine_id = str(getattr(routine, "routine_id", "")).strip()
    if not routine_id:
        raise RoutineContractError("register() requires a non-empty routine_id")
    writes = tuple(getattr(routine, "writes", ()) or ())
    calls = tuple(getattr(routine, "calls", ()) or ())
    # Writes OR calls. The original rule was writes-only, on the reasoning that a routine
    # writing nothing is a read; that held while every routine's whole effect was a datum
    # row. It stopped holding the moment a routine's job was to send mail: that writes no
    # document and is emphatically not a read, and refusing it here would have pushed the
    # first one to declare a decorative write to get past the door.
    if not writes and not calls:
        raise RoutineContractError(
            f"{routine_id!r} declares neither writes nor calls. A routine that does "
            "neither is a read, and a read does not need to be scheduled or authorized."
        )
    for write in writes:
        if not isinstance(write, RoutineWrite):
            raise RoutineContractError(
                f"{routine_id!r} declares a write that is not a RoutineWrite: {write!r}"
            )
    for call in calls:
        if not isinstance(call, DeclaredCall):
            raise RoutineContractError(
                f"{routine_id!r} declares a call that is not a DeclaredCall: {call!r}"
            )
    ROUTINE_REGISTRY[routine_id] = routine
    return routine


def get(routine_id: str) -> AutomationRoutine | None:
    """Look up a routine by id, or None when absent."""
    return ROUTINE_REGISTRY.get(str(routine_id).strip())


def all_routines() -> list[AutomationRoutine]:
    """Every registered routine, sorted by routine_id for stability."""
    return [ROUTINE_REGISTRY[k] for k in sorted(ROUTINE_REGISTRY)]


def routine_ids() -> tuple[str, ...]:
    """Every registered routine id, sorted."""
    return tuple(sorted(ROUTINE_REGISTRY))


def describe() -> list[dict[str, object]]:
    """Every routine as a plain dict — for an operator surface or a CLI listing.

    Includes the declared writes AND calls, because "what may this thing do" is the only
    question worth asking about an actor nobody is watching — and half of what an
    unattended actor can do now leaves the box entirely.
    """
    return [
        {
            "routine_id": routine.routine_id,
            "label": routine.label,
            "summary": routine.summary,
            "writes": [
                {
                    "document_kind": write.document_kind,
                    "action": write.action,
                    "sandbox_id": write.sandbox_id or "(run sandbox)",
                }
                for write in routine.writes
            ],
            "calls": [
                {"service": call.service, "operation": call.operation}
                for call in routine.calls
            ],
        }
        for routine in all_routines()
    ]
