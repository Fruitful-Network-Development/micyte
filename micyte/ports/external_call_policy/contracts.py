"""Which outbound calls a caller may make — the contract, and the one place it is enforced.

The sibling of :mod:`micyte.ports.datum_write_policy`, for the other direction. That one
governs what a caller may write into this instance's own documents; this governs what it
may say to somebody else's service. They are deliberately separate policies over the same
actor namespace: a grant to edit a farm's offering is not a grant to charge a card, and an
adapter that may read a provider's catalog is not thereby allowed to capture a payment.

Modelled on ``micyte/core/crypto/channel.py``: the platform declares the shape and refuses
without it; the host supplies the facts. There is no permissive mode and no default grant,
because the failure this exists to prevent is a call that *looks* authorized.

Why the permission lives here and the calling does not
------------------------------------------------------
``micyte/pyproject.toml`` is exactly ``pyyaml`` + ``shapely``. No HTTP client, no OAuth
library and no payment SDK may enter the platform for an opt-in feature, so the call itself
belongs to the host — in ``fnd_app/`` beside the credentials it needs. What belongs here is
the *question*, for the same reason ``require_cipher`` lives in the platform while the
cipher comes from the deployment: a rule enforced at each call site is a rule with as many
readings as there are call sites.

A denial is not an empty result
-------------------------------
:class:`ExternalCallDenied` is raised, never returned as a falsy value. Two of the first
call sites this governs (PayPal's webhook list and create) already swallow their errors
into ``[]`` and ``None``, and an empty webhook list reads as "none are configured" —
which is the answer that gets a second one created. A refusal has to be louder than a
missing thing, or it will be mistaken for one.

Deliberately NOT here: credentials, endpoints, transports, retry policy, or what any
particular service's operations mean. Those are host concerns. This module owns only the
question and the answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A grant field holding this matches anything. Spelled out rather than implied by an
# empty set, because an empty set is what a MISCONFIGURED grant looks like and those
# two must never be the same value.
ANY = "*"


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_token_set(values: object, *, field_name: str) -> frozenset[str]:
    if isinstance(values, str):
        raise ValueError(f"{field_name} must be a collection of strings, not a string")
    try:
        items = [_as_text(v) for v in values]  # type: ignore[union-attr]
    except TypeError:
        raise ValueError(f"{field_name} must be a collection of strings") from None
    tokens = frozenset(t for t in items if t)
    if not tokens:
        raise ValueError(f"{field_name} must name at least one value (use ANY to mean 'any')")
    return tokens


class ExternalCallDenied(PermissionError):
    """Raised by :func:`require_external_call` when no grant covers the request."""


@dataclass(frozen=True)
class DeclaredCall:
    """One kind of outbound call some caller may make, stated in advance.

    The egress counterpart of
    :class:`~micyte.ports.datum_write_policy.DeclaredWrite`, and it works the same way:
    a port binding declares these, and the host builds its :class:`ExternalCallRequest`
    objects *out of them* rather than asking the caller what it intends.

    ``operation`` is the verb, at the grain an operator would actually want to withhold
    — ``order.capture`` separately from ``order.create``, because the first moves money
    and the second does not. A service named without operations would be a grant to do
    anything that service offers, which is the grant nobody means to write.
    """

    service: str
    operation: str

    def __post_init__(self) -> None:
        for name in ("service", "operation"):
            token = _as_text(getattr(self, name))
            if not token:
                raise ValueError(f"declared_call.{name} is required")
            if token == ANY:
                raise ValueError(
                    f"declared_call.{name} must name one {name}; "
                    f"{ANY!r} is a grant value, not a declaration value"
                )
            object.__setattr__(self, name, token)


@dataclass(frozen=True)
class ExternalCallRequest:
    """One attempted outbound call, described completely enough to be judged.

    ``actor_id`` is who is asking, in the same namespace the datum-write policy uses —
    ``operator:<instance>``, ``grantee:<msn>``, ``automation:<routine>``,
    ``port:<binding>``. It is never blank: "no identity" is not an actor, it is a
    missing one, and treating it as an actor is the mistake the commerce seam's Phase 0
    was written to make impossible.

    ``binding_id`` is which configured seam is calling. Two bindings against the same
    provider — a farm's own PayPal account and the operator's — are two different
    requests, which is what lets one be granted less than the other.
    """

    actor_id: str
    binding_id: str
    service: str
    operation: str

    def __post_init__(self) -> None:
        for name in ("actor_id", "binding_id", "service", "operation"):
            token = _as_text(getattr(self, name))
            if not token:
                raise ValueError(f"external_call_request.{name} is required")
            if token == ANY:
                raise ValueError(
                    f"external_call_request.{name} must not be {ANY!r}: a wildcard is a "
                    "GRANT value, and a request carrying one would satisfy every "
                    "narrowed grant it met"
                )
            object.__setattr__(self, name, token)


@dataclass(frozen=True)
class ExternalCallGrant:
    """Permission for one actor to make some calls through some bindings.

    Every dimension must be stated. A grant that omits one would be read as "any", and
    a permission system whose omissions widen it is one nobody can audit.
    """

    actor_id: str
    binding_ids: frozenset[str] = field(default_factory=lambda: frozenset({ANY}))
    services: frozenset[str] = field(default_factory=lambda: frozenset({ANY}))
    operations: frozenset[str] = field(default_factory=lambda: frozenset({ANY}))

    def __post_init__(self) -> None:
        actor = _as_text(self.actor_id)
        if not actor:
            raise ValueError("external_call_grant.actor_id is required")
        object.__setattr__(self, "actor_id", actor)
        for name in ("binding_ids", "services", "operations"):
            object.__setattr__(
                self,
                name,
                _as_token_set(getattr(self, name), field_name=f"external_call_grant.{name}"),
            )

    def covers(self, request: ExternalCallRequest) -> bool:
        return (
            self.actor_id == request.actor_id
            and _matches(self.binding_ids, request.binding_id)
            and _matches(self.services, request.service)
            and _matches(self.operations, request.operation)
        )


def _matches(allowed: frozenset[str], value: str) -> bool:
    return ANY in allowed or value in allowed


def require_external_call(
    request: ExternalCallRequest,
    *,
    grants: tuple[ExternalCallGrant, ...] | list[ExternalCallGrant],
) -> None:
    """Return silently when a grant covers ``request``; raise otherwise.

    The single place the "an outbound call must be granted" rule is enforced, so a call
    site cannot implement its own more lenient version of it.

    There is no ``grants=None`` meaning "unrestricted". An empty grant set denies
    everything, which is the correct reading of "nobody has said this actor may call
    out": a permission system that opens when its configuration is missing has the
    posture of one that is off.
    """
    for grant in grants or ():
        if grant.covers(request):
            return
    raise ExternalCallDenied(
        f"{request.actor_id!r} may not {request.operation!r} on {request.service!r} "
        f"via {request.binding_id!r}"
    )


__all__ = [
    "ANY",
    "DeclaredCall",
    "ExternalCallDenied",
    "ExternalCallGrant",
    "ExternalCallRequest",
    "require_external_call",
]
