"""Which instance the current request is about.

A sandbox is addressed by ``(msn_id, sandbox)``. Every instance keeps its core sandbox under
the same name — ``system`` — so a read that names only the sandbox cannot say whose it is,
and ``read_documents_by_sandbox`` refuses rather than merging four tenants' documents.

Threading an ``msn_id`` parameter through every reader would mean touching 32 tool modules
and 36 ``build_panel_payload`` implementations, and — this is the part that matters — a
SINGLE missed one is a tool that raises in production. The msn is not really an argument to
those functions anyway: it is a property of the request they are all serving, the same way
the tenant is.

So it is scoped, once, where the request is resolved:

    with use_instance(active_msn):
        ...build the shell, render the tools...

Rules that keep this from being ambient magic:

* **An explicit ``msn_id`` always wins.** Callers that know better say so, and nothing here
  can override them.
* **It is a DEFAULT, never an override.** Absent scope plus an ambiguous name still raises.
  A script, a cron job or a test outside a request gets the loud failure, which is correct:
  nothing has said which instance it means.
* **Set by the HOST, never from a request body.** The value comes from the instance the
  shell resolved, so a caller cannot name the instance it would like to be read as — the
  same reason the write gate resolves a tool from the action rather than from the payload.
* **It does not cross a thread or a task boundary by accident.** ``ContextVar`` is per
  context; a worker that needs the scope must enter it itself.

The alternative was an ``msn_id`` parameter on 68 signatures, most of which would only pass
it straight down. That is not more explicit in any way a reader benefits from; it is the
same fact written 68 times, with 68 chances to omit it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

#: The msn of the instance the current request is about, or "" when nothing has said.
_ACTIVE_INSTANCE_MSN: ContextVar[str] = ContextVar("mycite_active_instance_msn", default="")


def active_instance_msn() -> str:
    """The scoped instance msn, or ``""`` when the caller is outside a request."""
    return _ACTIVE_INSTANCE_MSN.get()


def resolve_msn(msn_id: str = "") -> str:
    """``msn_id`` if given, else the scoped one. The one place that order is decided."""
    explicit = str(msn_id or "").strip()
    return explicit or active_instance_msn()


@contextmanager
def use_instance(msn_id: str) -> Iterator[str]:
    """Scope every sandbox read in this block to one instance.

    A blank ``msn_id`` clears the scope rather than inheriting an outer one, so a request
    that could not resolve an instance does not silently read as whichever one ran before
    it on this thread.
    """
    token = _ACTIVE_INSTANCE_MSN.set(str(msn_id or "").strip())
    try:
        yield active_instance_msn()
    finally:
        _ACTIVE_INSTANCE_MSN.reset(token)


__all__ = ["active_instance_msn", "resolve_msn", "use_instance"]
