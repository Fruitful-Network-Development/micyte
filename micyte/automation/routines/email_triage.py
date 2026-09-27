"""``email_triage`` — read the mail, judge it against the tree, answer or hand it over.

The register's first routine, and it runs NOTHING on a schedule. The 2026-07-31 decision
("no scheduler") stands; this exists so that:

* the Functions surface can answer the operator's question — *which applications or
  routines have permission to use this function* — with a real row rather than an empty
  column. A permission dimension nothing fills is the ``tool_ids`` defect, and that one
  sat enforced-and-unreachable for a year;
* the first unattended caller arrives already declared and already refusable, instead of
  as a script that identifies itself as nothing;
* turning it on later is one grant, reviewed on its own, rather than new code.

**Named for the job, not the client.** ``email_triage``, never ``bpw_email_triage``. The
``handyman_erp`` lesson: a register entry named for one client is a vertical wearing a
platform's clothes, and the second client makes a copy. Which mailbox it acts on comes
from the port binding, which is a per-client fact and belongs in per-client configuration.

**It declares CALLS and no writes.** A triage run reads mail, asks a model, and sends —
none of which is a datum row. The register used to require a write, which would have
forced this to declare a decorative one to get past the door; it now takes either.
"""

from __future__ import annotations

from typing import Any

from micyte.ports.external_call_policy import DeclaredCall

from .._contract import RoutineContext, RoutineDecision

#: The service token the FND Service extension is granted under. Imported would be
#: better; it lives host-side (``fnd_app``), and ``micyte`` may not reach there — the
#: boundary that lets MiCyte ship standalone. Pinned by a test that compares the two.
_FND_SERVICE = "fnd_service"

#: The AI providers a triage run may ask. The same tuple Oveure's relay offers, read from
#: the notes module rather than restated, so the dropdown and the grant cannot drift.
def _providers() -> tuple[str, ...]:
    from micyte.tools.note_books import OVEURE_PROVIDERS

    return OVEURE_PROVIDERS


class EmailTriageRoutine:
    """Declared, refusable, and driven by hand.

    ``evaluate`` deliberately does not read mail. A routine's ``evaluate`` returns
    EFFECTS the runner may apply, and every effect this job has is an outbound call
    rather than a datum write — so there is nothing for the runner's effect machinery to
    hold. Running it is the host's job (it owns the adapters and the credentials); what
    this class contributes is the DECLARATION the runner authorizes and the surface reads.

    Stated as a decline with a reason rather than as a stub that raises, because
    ``RoutineDecision`` requires a reason in both directions and "nobody has turned this
    on" is a true and useful one to find in a log.
    """

    routine_id = "email_triage"
    label = "Email triage"
    summary = (
        "Read what arrived, judge it against this instance's own domain tree, and "
        "either answer it or hand it to a person. Runs when somebody presses Run."
    )
    #: No datum writes. A triage run leaves no row: the draft is returned unsaved, the
    #: same posture the ask relay takes, because an answer that wrote itself into the
    #: books would be an automation nobody granted.
    writes: tuple = ()

    def __init__(self) -> None:
        self.calls: tuple[DeclaredCall, ...] = (
            *(DeclaredCall(service=service, operation=operation)
              for service, operation in (
                  (_FND_SERVICE, "mailbox.list"),
                  (_FND_SERVICE, "message.fetch"),
                  (_FND_SERVICE, "message.send"),
                  (_FND_SERVICE, "message.forward"),
              )),
            *(DeclaredCall(service=provider, operation="messages.create")
              for provider in _providers()),
        )

    def evaluate(self, context: RoutineContext) -> RoutineDecision:
        return RoutineDecision(
            fired=False,
            reason=(
                "email_triage is declared but not scheduled. It is driven from Oveure's "
                "Inbox tab; the 2026-07-31 no-scheduler decision has not been reopened."
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "routine_id": self.routine_id,
            "label": self.label,
            "calls": [{"service": c.service, "operation": c.operation} for c in self.calls],
        }


__all__ = ["EmailTriageRoutine"]
