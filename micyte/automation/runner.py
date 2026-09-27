"""Running a routine: authorize everything it declared, then let it decide.

The order matters and is the point of this module.

**Authorize before evaluating, and authorize all of it.** A routine is granted its
whole job or none of it. Authorizing per-effect after the decision would let a routine
that may write two documents write one and stop, and an unattended writer that half-ran
leaves a state nobody designed — the same failure the three-commit agro write path had
before Phase 1 collapsed it into one transaction.

**The runner never asks the routine what it may write.** It reads the declaration off
the register and builds the requests from it. A routine cannot widen its own scope
because it is never consulted about it.

**A routine cannot apply its own effects.** ``evaluate`` returns them; the runner
decides whether they run. That is what makes ``dry_run`` truthful rather than a flag
the routine is trusted to honour.
"""

from __future__ import annotations

from dataclasses import dataclass

from micyte.ports.datum_write_policy import (
    DatumWriteDenied,
    DatumWriteGrant,
    DatumWriteRequest,
    require_datum_write,
)
from micyte.ports.external_call_policy import (
    ExternalCallDenied,
    ExternalCallGrant,
    ExternalCallRequest,
    require_external_call,
)

from ._contract import (
    AutomationRoutine,
    RoutineContext,
    RoutineContractError,
    RoutineWrite,
)


@dataclass(frozen=True)
class RoutineOutcome:
    """What one run did, in enough detail to be believed or disbelieved.

    ``authorized`` is reported separately from ``fired`` because "not permitted" and
    "condition did not hold" are different answers, and an operator reading a log
    needs to tell them apart. ``denials`` carries the refusal text verbatim.
    """

    routine_id: str
    actor_id: str
    sandbox_id: str
    authorized: bool
    fired: bool
    reason: str
    applied: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    denials: tuple[str, ...] = ()
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return self.authorized and not self.denials

    def to_dict(self) -> dict[str, object]:
        return {
            "routine_id": self.routine_id,
            "actor_id": self.actor_id,
            "sandbox_id": self.sandbox_id,
            "authorized": self.authorized,
            "fired": self.fired,
            "reason": self.reason,
            "applied": list(self.applied),
            "skipped": list(self.skipped),
            "denials": list(self.denials),
            "dry_run": self.dry_run,
        }


def declared_write_requests(
    routine: AutomationRoutine, *, actor_id: str, sandbox_id: str
) -> tuple[DatumWriteRequest, ...]:
    """Every write the routine declared, as authorization requests.

    Public because an operator surface wants to show exactly this — "here is what
    this routine may do, and here is whether it is currently allowed to" — and it
    must be the same list the runner enforces, not a second rendering of it.
    """
    return tuple(
        DatumWriteRequest(
            actor_id=actor_id,
            tool_id=routine.routine_id,
            sandbox_id=write.bound_to(sandbox_id).sandbox_id,
            document_kind=write.document_kind,
            action=write.action,
        )
        for write in routine.writes
    )


def declared_call_requests(
    routine: AutomationRoutine, *, actor_id: str
) -> tuple[ExternalCallRequest, ...]:
    """Every outbound call the routine declared, as authorization requests.

    ``binding_id`` is the routine's own id. The egress policy's binding dimension asks
    "which configured seam is calling", and for an unattended caller the honest answer is
    the routine itself: it is what an operator would narrow a grant to, and borrowing the
    port binding's id here would make two different callers — the routine and the surface
    a person drives — indistinguishable in the grant that permits them.
    """
    return tuple(
        ExternalCallRequest(
            actor_id=actor_id,
            binding_id=routine.routine_id,
            service=call.service,
            operation=call.operation,
        )
        for call in routine.calls
    )


def authorize_routine(
    routine: AutomationRoutine,
    *,
    actor_id: str,
    sandbox_id: str,
    grants: tuple[DatumWriteGrant, ...] | list[DatumWriteGrant],
    call_grants: tuple[ExternalCallGrant, ...] | list[ExternalCallGrant] = (),
) -> tuple[str, ...]:
    """Return the denial messages for ``routine`` — empty when it may do its whole job.

    Both policies, one answer. Whole job or none holds across the pair: a routine allowed
    to read a mailbox but not to answer it would run half a conversation and stop
    somewhere nobody designed, which is the same failure authorizing writes together was
    written to prevent.
    """
    denials: list[str] = []
    for request in declared_write_requests(routine, actor_id=actor_id, sandbox_id=sandbox_id):
        try:
            require_datum_write(request, grants=grants)
        except DatumWriteDenied as denied:
            denials.append(str(denied))
    for call in declared_call_requests(routine, actor_id=actor_id):
        try:
            require_external_call(call, grants=call_grants)
        except ExternalCallDenied as denied:
            denials.append(str(denied))
    return tuple(denials)


def run_routine(
    routine: AutomationRoutine,
    *,
    context: RoutineContext,
    actor_id: str,
    grants: tuple[DatumWriteGrant, ...] | list[DatumWriteGrant],
    call_grants: tuple[ExternalCallGrant, ...] | list[ExternalCallGrant] = (),
    dry_run: bool = False,
) -> RoutineOutcome:
    """Authorize, evaluate, and (unless ``dry_run``) apply. Never raises for a denial.

    A denied routine returns an outcome saying so rather than raising, because the
    caller is a scheduler running several and one refusal is a fact to record, not an
    exception to unwind. A routine that breaks its own contract DOES raise
    :class:`RoutineContractError` — that is a programming error, not a policy answer.
    """
    declared = {(w.bound_to(context.sandbox_id)) for w in routine.writes}
    denials = authorize_routine(
        routine, actor_id=actor_id, sandbox_id=context.sandbox_id, grants=grants,
        call_grants=call_grants,
    )
    if denials:
        return RoutineOutcome(
            routine_id=routine.routine_id,
            actor_id=actor_id,
            sandbox_id=context.sandbox_id,
            authorized=False,
            fired=False,
            reason="not authorized for everything it declares",
            denials=denials,
            dry_run=dry_run,
        )

    decision = routine.evaluate(context)
    applied: list[str] = []
    skipped: list[str] = []
    for effect in decision.effects:
        bound = _bound(effect.write, context.sandbox_id)
        if bound not in declared:
            raise RoutineContractError(
                f"{routine.routine_id!r} returned an effect writing "
                f"{bound.action!r} on {bound.document_kind!r} in {bound.sandbox_id!r}, "
                "which it did not declare. The declaration is the authorization; an "
                "undeclared effect was never judged."
            )
        if dry_run:
            skipped.append(effect.description)
            continue
        effect.apply()
        applied.append(effect.description)

    return RoutineOutcome(
        routine_id=routine.routine_id,
        actor_id=actor_id,
        sandbox_id=context.sandbox_id,
        authorized=True,
        fired=bool(decision.fired),
        reason=decision.reason,
        applied=tuple(applied),
        skipped=tuple(skipped),
        dry_run=dry_run,
    )


def _bound(write: object, sandbox_id: str) -> RoutineWrite:
    if not isinstance(write, RoutineWrite):
        raise RoutineContractError(f"routine effect carries a non-RoutineWrite: {write!r}")
    return write.bound_to(sandbox_id)
