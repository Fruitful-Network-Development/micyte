"""What it means for a port to be FILLED on a particular instance.

A port is a contract and stays one. ``micyte/ports/module_contract.md`` says it owns
"inward-facing interface contracts only" — no adapter code, no host composition — and
``CommerceOfferingPort`` is the worked example: a Protocol, no implementation, no state,
no identity. Nothing about it can be configured, because there is nothing there to
configure.

So when an operator says "configure the port and give it permissions", the thing being
configured is not the port. It is the **binding**: a statement that on this instance,
this port is filled by that adapter, may write these documents, and may make those calls.
The port declares the shape; the binding says who is standing in it and what they are
allowed to do. That split is the same one ``require_cipher`` draws — micyte declares the
cipher's shape and refuses without one; the deployment supplies it — and it is what keeps
a seam from quietly becoming a service.

A binding is an ACTOR
---------------------
``port:<binding_id>``, in the same namespace as ``operator:``, ``grantee:`` and
``automation:``, so one grant list covers all of them and no adapter can be mistaken for
the person who installed it.

Like an automation routine, **a binding derives no grant and ships denied**. Nothing in
the catalog says which farm a payment adapter belongs to or whose money it may move, so
the only honest source is an operator writing it into ``private/config.json``. An
adapter that arrives able to act because it was merely installed is the shape of a
supply-chain problem.

The declaration is the request
------------------------------
:attr:`PortBinding.writes` and :attr:`PortBinding.calls` are not labels. The authorizing
code builds its requests *out of them* and never asks the adapter what it intends — the
same rule ``micyte.automation`` follows, for the same reason: a second statement of the
same fact is a thing that can drift from the first.

Deliberately NOT here: where bindings are stored, how an adapter is loaded, what
credentials it needs, or which ports exist. Those are host concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from micyte.ports.datum_write_policy import DatumWriteRequest, DeclaredWrite
from micyte.ports.external_call_policy import DeclaredCall, ExternalCallRequest
from micyte.ports.port_catalog import port_type

#: The actor-id prefix a binding runs under. Shares a namespace with the human and
#: automation actors so one grant list covers every writer on the instance, and stays
#: distinguishable so an adapter can never be read as the operator who installed it.
PORT_ACTOR_PREFIX = "port:"


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


class PortBindingError(ValueError):
    """A binding is malformed.

    ``binding_id`` names WHICH binding when the error is about one — empty when the
    fault is not attributable to a single row. A reader that has to report a refusal
    needs the id, and reading it back out of the message is how the two spellings
    start to disagree.
    """

    def __init__(self, message: str, *, binding_id: str = "") -> None:
        super().__init__(message)
        self.binding_id = _as_text(binding_id)


def port_actor_id(binding_id: str) -> str:
    """The actor id a binding acts as. Derived from the binding, never from a request."""
    token = _as_text(binding_id)
    if not token:
        raise PortBindingError("port_actor_id requires a binding_id")
    return f"{PORT_ACTOR_PREFIX}{token}"


@dataclass(frozen=True)
class PortBinding:
    """One port, filled by one adapter, on one instance — and what that is allowed to do.

    ``msn_id`` is WHOSE. It is required, and it is the half that was missing until
    2026-08-27.

    A binding is addressed by the PAIR — `(msn_id, sandbox)` — the same way every other
    sandbox in this stack is, and for the same reason. `port_bindings` lives in ONE
    config for every instance a portal serves, and `sandbox_ids` holds NAMES: every
    client's app sandbox is called `pim`, every instance's core is called `system`. So a
    binding that said only "sandbox `pim`" said *every instance at once*, and it was
    read that way — with one site binding configured, four other clients' Design tabs
    listed its owner's articles and offered a publish form pointed at his website.

    ONE instance per binding, not a pair per sandbox. A binding is one instance's choice
    of extension for one port, and its credential can only describe one login
    (`verify_service_identity` refuses a grantee/instance pair the corpus does not hold).
    A binding spanning two instances would be a credential that cannot exist.

    ``sandbox_ids`` is which of THAT instance's sandboxes it acts for. It is required and
    may not be empty: a payment adapter bound to "whichever sandbox the caller names" is
    how a sale lands on the wrong farm's books, and there is nobody watching an adapter
    to notice. It is also never the grant wildcard — that value belongs to grants, and a
    binding carrying one would produce requests that satisfied every narrowed grant they
    met.

    A binding with neither writes nor calls is refused. It would be a configured seam
    that cannot do anything, which is not a safe default but an unfinished sentence —
    and an operator reading the Ports surface would see a row that means nothing.
    """

    binding_id: str
    port_id: str
    adapter_id: str
    msn_id: str
    sandbox_ids: tuple[str, ...]
    writes: tuple[DeclaredWrite, ...] = ()
    calls: tuple[DeclaredCall, ...] = ()
    label: str = ""

    def __post_init__(self) -> None:
        for name in ("binding_id", "port_id", "adapter_id", "msn_id"):
            token = _as_text(getattr(self, name))
            if not token:
                raise PortBindingError(
                    f"port_binding.{name} is required for {self.binding_id!r}"
                    + (" — a binding that does not say WHOSE it is says everyone's, and "
                       "was read that way" if name == "msn_id" else ""))
            object.__setattr__(self, name, token)
        # The port must EXIST. Until `port_catalog` there was no list to check against,
        # so a typo produced a fully-formed binding for a seam nothing reads — visible on
        # the Ports surface, permanently inert, and indistinguishable from a feature that
        # simply does not work.
        try:
            port_type(self.port_id)
        except ValueError as exc:
            raise PortBindingError(f"{self.binding_id!r}: {exc}") from exc
        sandboxes = tuple(
            token for token in (_as_text(s) for s in (self.sandbox_ids or ())) if token
        )
        if not sandboxes:
            raise PortBindingError(
                f"port_binding.sandbox_ids is required for {self.binding_id!r}: a binding "
                "that acts for whichever sandbox it is handed is one that can act on the "
                "wrong farm with nobody watching"
            )
        if "*" in sandboxes:
            raise PortBindingError(
                "port_binding.sandbox_ids must name sandboxes; '*' is a grant value, "
                "not a binding value"
            )
        object.__setattr__(self, "sandbox_ids", sandboxes)
        object.__setattr__(self, "writes", tuple(self.writes or ()))
        object.__setattr__(self, "calls", tuple(self.calls or ()))
        for write in self.writes:
            if not isinstance(write, DeclaredWrite):
                raise PortBindingError("port_binding.writes must hold DeclaredWrite values")
        for call in self.calls:
            if not isinstance(call, DeclaredCall):
                raise PortBindingError("port_binding.calls must hold DeclaredCall values")
        if not self.writes and not self.calls:
            raise PortBindingError(
                f"{self.binding_id!r} declares neither a write nor a call, so filling the "
                "port would let it do nothing. Say what it is for, or do not bind it."
            )
        object.__setattr__(self, "label", _as_text(self.label) or self.binding_id)

    @property
    def actor_id(self) -> str:
        return port_actor_id(self.binding_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "port_id": self.port_id,
            "adapter_id": self.adapter_id,
            "msn_id": self.msn_id,
            "label": self.label,
            "actor_id": self.actor_id,
            "sandbox_ids": list(self.sandbox_ids),
            "writes": [
                {"document_kind": w.document_kind, "action": w.action} for w in self.writes
            ],
            "calls": [{"service": c.service, "operation": c.operation} for c in self.calls],
        }


def declared_write_requests(binding: PortBinding) -> tuple[DatumWriteRequest, ...]:
    """Every datum write this binding declared, as authorization requests.

    Public because the Ports surface wants exactly this — "here is what this binding may
    do, and here is whether it is currently allowed to" — and it must be **the same list
    the runtime enforces**, not a second rendering of it. A surface that computes
    permission its own way is a surface that will one day disagree with the gate and be
    believed.

    One request per (write x sandbox): a binding acting for two farms is asking two
    different questions, and an operator may well answer them differently.
    """
    return tuple(
        DatumWriteRequest(
            actor_id=binding.actor_id,
            tool_id=binding.binding_id,
            sandbox_id=write.bound_to(sandbox).sandbox_id,
            document_kind=write.document_kind,
            action=write.action,
        )
        for write in binding.writes
        for sandbox in binding.sandbox_ids
    )


def declared_call_requests(binding: PortBinding) -> tuple[ExternalCallRequest, ...]:
    """Every outbound call this binding declared, as authorization requests."""
    return tuple(
        ExternalCallRequest(
            actor_id=binding.actor_id,
            binding_id=binding.binding_id,
            service=call.service,
            operation=call.operation,
        )
        for call in binding.calls
    )


@dataclass(frozen=True)
class PortBindingSet:
    """Every binding an instance holds. One binding id, one binding.

    ``refused`` is what the config carried and could not be read — ``(binding_id, why)``
    per entry. It exists because the reader DROPS a malformed or unresolvable binding,
    which is the correct thing to do and a silent one: an operator sees "nothing
    connected", which is also the shipped state, and the two are indistinguishable.
    Carrying the reason lets a surface say which it is.

    Added when `msn_id` became required (2026-08-27) and every pre-migration binding
    therefore stopped reading. A migration that makes a seam vanish without saying so is
    a migration nobody notices until the feature is reported broken.
    """

    bindings: tuple[PortBinding, ...] = field(default_factory=tuple)
    refused: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for binding in self.bindings:
            if binding.binding_id in seen:
                raise PortBindingError(
                    f"{binding.binding_id!r} is bound twice — two rows disagreeing about "
                    "what one actor may do, with no rule saying which wins",
                    binding_id=binding.binding_id,
                )
            seen.add(binding.binding_id)

    def for_port(self, port_id: str) -> tuple[PortBinding, ...]:
        token = _as_text(port_id)
        return tuple(b for b in self.bindings if b.port_id == token)

    def for_instance(self, port_id: str, *, msn_id: str,
                     sandbox: str = "") -> tuple[PortBinding, ...]:
        """The bindings on ``port_id`` that are THIS instance's — the PAIR.

        The question every caller actually has, asked in one place so no caller answers
        it with `for_port(...)[0]` again. That was the shape of the cross-tenant read:
        "the first binding for this port" is the first one ANYBODY has.

        ``msn_id`` is not optional. A caller with no instance in hand is a caller that
        cannot be told which of these is theirs, and returning all of them would be the
        defect this method exists to remove.
        """
        msn = _as_text(msn_id)
        if not msn:
            raise PortBindingError(
                "for_instance requires an msn_id — a binding is addressed by the pair, "
                "and a lookup without one is the portal-wide read it replaces")
        name = _as_text(sandbox)
        return tuple(
            b for b in self.for_port(port_id)
            if b.msn_id == msn and (not name or name in b.sandbox_ids)
        )

    def get(self, binding_id: str) -> PortBinding | None:
        token = _as_text(binding_id)
        return next((b for b in self.bindings if b.binding_id == token), None)


__all__ = [
    "PORT_ACTOR_PREFIX",
    "PortBinding",
    "PortBindingError",
    "PortBindingSet",
    "declared_call_requests",
    "declared_write_requests",
    "port_actor_id",
]
