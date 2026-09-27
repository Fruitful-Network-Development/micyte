"""Automation routines — the register for tools no person drives.

See :mod:`micyte.automation._contract` for why this is a second register rather than
optional fields on the workbench-tool contract.

The register holds routines that are DECLARED but not scheduled, and the distinction is
the whole posture. A routine acts on a condition nobody is watching, so the first one to
run unattended is the operator's call, not a demonstration. Being in the register means it
can be authorized, refused, and read off a surface — none of which requires anything to
run — and it is what lets "turn it on" later be one reviewed grant instead of new code.

``routines/`` holds them. Every one ships refused, and no scheduler exists: the
2026-07-31 decision has not been reopened.
"""

from ._contract import (
    AutomationRoutine,
    RoutineContext,
    RoutineContractError,
    RoutineDecision,
    RoutineEffect,
    RoutineWrite,
)
from ._registry import (
    ROUTINE_REGISTRY,
    all_routines,
    describe,
    get,
    register,
    routine_ids,
)
from .runner import (
    RoutineOutcome,
    authorize_routine,
    declared_call_requests,
    declared_write_requests,
    run_routine,
)

__all__ = [
    "ROUTINE_REGISTRY",
    "AutomationRoutine",
    "RoutineContext",
    "RoutineContractError",
    "RoutineDecision",
    "RoutineEffect",
    "RoutineOutcome",
    "RoutineWrite",
    "all_routines",
    "authorize_routine",
    "declared_call_requests",
    "declared_write_requests",
    "describe",
    "get",
    "register",
    "routine_ids",
    "run_routine",
]

# Imported last, and for its side effect: each routine self-registers, exactly as a
# workbench tool does. At the bottom because a routine may reach `micyte.tools` for a
# shared constant, and that must not run while this package is still initialising.
from . import routines as _routines  # noqa: F401
