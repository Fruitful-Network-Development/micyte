"""Automation-routine contract — the second tool register.

A :class:`~micyte.tools.WorkbenchTool` presumes a person: something is in focus, a
panel is rendered, and someone is looking at it. A routine is the other half of the
taxonomy — a condition is met and a datum is written, with nobody watching. It has no
route, no panel and no eligibility, because there is no selection to be eligible
against.

Two registers rather than one optional-field register, for the reason the review that
prompted this found: ``manipulates_datum_kinds`` sat on the shell registry for a year
as a field that was normalized, serialized and consumed by nothing. A tool contract
whose UI half is optional produces exactly that — declarations nobody reaches, because
the code path that would read them only exists for the other kind of tool. Here the
two kinds cannot be confused: :func:`micyte.automation.register` refuses anything that
can render, and :func:`micyte.tools.register` refuses anything that declares a
``routine_id``.

**The declaration is the request.** :attr:`AutomationRoutine.writes` is not a label
describing what the routine does; the runner builds its
:class:`~micyte.ports.datum_write_policy.DatumWriteRequest` objects *out of it*. There
is no second place stating the same fact, so the two cannot drift apart — which is the
whole failure mode ``manipulates_datum_kinds`` demonstrated.

``RoutineWrite`` is an alias for
:class:`~micyte.ports.datum_write_policy.DeclaredWrite`, which is where the shape
now lives. A workbench tool that edits and a port binding an adapter fills declare
in the SAME vocabulary, so one ``require_datum_write`` judges all three registers
and none of them has to import another to say what it writes.

**Time comes from the runner.** A routine that reads the clock itself cannot be
replayed, tested against a boundary, or explained after the fact. ``RoutineContext.now``
is supplied, and a routine reading ``datetime.now()`` is a bug the same way a datum
writer hardcoding a row address is.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from micyte.ports.datum_write_policy import DeclaredWrite
from micyte.ports.external_call_policy import DeclaredCall


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


# A routine's write is not a routine-shaped thing — it is the write policy's own
# vocabulary, which a workbench tool and a port binding declare in too. Keeping the
# name here (the runner, the register, the CLI and the operator surface all say
# "routine write") while the TYPE lives with the policy is what lets one
# ``require_datum_write`` judge all three registers without any of them importing
# each other. See micyte/ports/datum_write_policy/contracts.py.
RoutineWrite = DeclaredWrite


@dataclass(frozen=True)
class RoutineContext:
    """Everything a routine is allowed to know. Opaque to the runner.

    ``now`` is the runner's clock, not the routine's — see the module docstring.
    ``resources`` is whatever the host wired up (a datum store, an authority path);
    the runner never looks inside it, which is what keeps this module free of
    adapter dependencies.
    """

    now: datetime
    sandbox_id: str
    resources: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.now, datetime):
            raise ValueError("routine_context.now must be a datetime")
        sandbox = _as_text(self.sandbox_id)
        if not sandbox:
            raise ValueError("routine_context.sandbox_id is required")
        object.__setattr__(self, "sandbox_id", sandbox)


@dataclass(frozen=True)
class RoutineEffect:
    """One write the routine has decided to make, and the callable that makes it.

    ``write`` must be one the routine declared, or the runner refuses the effect. The
    callable is the routine's own business — the runner owns only *whether* it runs.
    """

    write: RoutineWrite
    description: str
    apply: Callable[[], None]

    def __post_init__(self) -> None:
        if not isinstance(self.write, RoutineWrite):
            raise ValueError("routine_effect.write must be a RoutineWrite")
        if not _as_text(self.description):
            raise ValueError("routine_effect.description is required")
        if not callable(self.apply):
            raise ValueError("routine_effect.apply must be callable")
        object.__setattr__(self, "description", _as_text(self.description))


@dataclass(frozen=True)
class RoutineDecision:
    """Whether the condition held, why, and what follows from it.

    ``reason`` is required in BOTH directions. A routine that declines silently is
    indistinguishable from one that is broken, and the failure mode of an unattended
    writer is being believed — the same lesson the nightly refresh taught when it
    printed ``ok`` over zero grantees.
    """

    fired: bool
    reason: str
    effects: tuple[RoutineEffect, ...] = ()

    def __post_init__(self) -> None:
        if not _as_text(self.reason):
            raise ValueError("routine_decision.reason is required in both directions")
        object.__setattr__(self, "reason", _as_text(self.reason))
        object.__setattr__(self, "effects", tuple(self.effects))
        if not self.fired and self.effects:
            raise ValueError("routine_decision declares effects but did not fire")


@runtime_checkable
class AutomationRoutine(Protocol):
    """A condition-triggered datum writer.

    Deliberately absent: ``route``, ``build_panel_payload``, ``applies_to_*``. A
    routine is not offered to anyone and renders nothing.
    """

    routine_id: str
    label: str
    summary: str
    # Every kind of write this routine may make. The runner authorizes all of them
    # before evaluating, so a routine either may do its whole job or does none of it.
    writes: tuple[RoutineWrite, ...]
    # Every outbound call it may make, in the same vocabulary a port binding uses.
    #
    # Added TASK-2026-08-18-003. Until then a routine could declare only writes, so a
    # routine whose whole job is a call — read a mailbox, ask a model, answer — had no
    # way to say so, and the Functions surface asking "which unattended caller may use
    # this operation" had nothing to read. The declaration is the request here exactly as
    # it is for `writes`: the runner builds the ExternalCallRequests out of this tuple and
    # never asks the routine what it intends.
    #
    # REQUIRED, like `writes`, and empty is a fine answer. It is not given a default
    # because `AutomationRoutine` is a runtime_checkable Protocol: a default here would
    # be a class attribute nothing structurally implementing the protocol inherits, so
    # `isinstance` would still pass for a routine that never considered the question and
    # `getattr(routine, "calls", ())` would silently answer "none" for it. A declaration
    # nobody was forced to write is the shape of a field that means nothing — which is
    # exactly what `manipulates_datum_kinds` was. Say `calls = ()` and mean it.
    calls: tuple[DeclaredCall, ...]

    def evaluate(self, context: RoutineContext) -> RoutineDecision:
        """Decide whether the condition holds, and what to do about it."""
        ...


class RoutineContractError(TypeError):
    """A routine broke the contract — raised at registration or by the runner."""
