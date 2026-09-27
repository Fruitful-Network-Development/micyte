"""Who may write which datum documents — the contract, and the one place it is enforced.

Modelled on ``micyte/core/crypto/channel.py``: the platform declares the shape and
refuses without it; the host supplies the facts. There is no permissive mode and no
default grant, because the failure this exists to prevent is a write that *looks*
authorized.

Deliberately NOT here: where grants are stored, how an actor is authenticated, or
what a "document kind" means to any particular domain. Those are host concerns. This
module owns only the question and the answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A grant field holding this matches anything. It is spelled out rather than
# implied by an empty set, because an empty set is what a MISCONFIGURED grant
# looks like and those two must not be the same value.
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
        raise ValueError(
            f"{field_name} must name at least one value (use ANY to mean 'any')"
        )
    return tokens


class DatumWriteDenied(PermissionError):
    """Raised by :func:`require_datum_write` when no grant covers the request."""


@dataclass(frozen=True)
class DeclaredWrite:
    """One kind of write some caller may perform, stated in advance.

    The vocabulary every register declares in — a workbench tool that edits, an
    automation routine that fires, a port binding that an adapter fills. It lives
    here rather than in any one of them because **the declaration is the request**:
    the runner and the write routes build their :class:`DatumWriteRequest` objects
    out of these, and never ask the caller what it intends. One shape means there is
    no second statement of the same fact for the first to drift from, which is the
    specific way ``manipulates_datum_kinds`` failed — normalized, serialized, and
    read by nothing for a year.

    ``sandbox_id`` may be left empty to mean "the sandbox this run is bound to",
    which is how a declaration is written once and granted per farm. It is never a
    wildcard: the caller substitutes the concrete sandbox before authorizing, so the
    request still names exactly one. :data:`ANY` is a value a GRANT may hold, and a
    request able to supply it would satisfy every narrowed grant it met.
    """

    document_kind: str
    action: str
    sandbox_id: str = ""

    def __post_init__(self) -> None:
        for name in ("document_kind", "action"):
            token = _as_text(getattr(self, name))
            if not token:
                raise ValueError(f"declared_write.{name} is required")
            object.__setattr__(self, name, token)
        object.__setattr__(self, "sandbox_id", _as_text(self.sandbox_id))
        if self.sandbox_id == ANY:
            raise ValueError(
                "declared_write.sandbox_id must name one sandbox or be empty "
                "(empty means 'the sandbox this run is bound to'); "
                f"{ANY!r} is a grant value, not a request value"
            )

    def bound_to(self, sandbox_id: str) -> DeclaredWrite:
        """This write with its sandbox resolved against the run's sandbox."""
        if self.sandbox_id:
            return self
        resolved = _as_text(sandbox_id)
        if not resolved:
            raise ValueError("declared_write.sandbox_id is unset and the run names no sandbox")
        return DeclaredWrite(
            document_kind=self.document_kind, action=self.action, sandbox_id=resolved
        )


@dataclass(frozen=True)
class DatumWriteRequest:
    """One attempted write, described completely enough to be judged.

    ``actor_id`` is who is asking — an operator msn, a grantee msn, or the id of an
    unattended writer. It is never blank: "no identity" is not an actor, it is a
    missing one, and treating it as an actor is the specific mistake this port was
    added to make impossible.

    ``tool_id`` is what is asking on the actor's behalf. Two different tools acting
    for the same person are two different requests, which is what lets a port or a
    background writer be granted less than its operator has.
    """

    actor_id: str
    tool_id: str
    sandbox_id: str
    document_kind: str
    action: str

    def __post_init__(self) -> None:
        for name in ("actor_id", "tool_id", "sandbox_id", "document_kind", "action"):
            token = _as_text(getattr(self, name))
            if not token:
                raise ValueError(f"datum_write_request.{name} is required")
            object.__setattr__(self, name, token)


@dataclass(frozen=True)
class DatumWriteGrant:
    """Permission for one actor to write some documents through some tools.

    Every dimension must be stated. A grant that omits one would be read as "any",
    and a permission system whose omissions widen it is one nobody can audit.
    """

    actor_id: str
    tool_ids: frozenset[str] = field(default_factory=lambda: frozenset({ANY}))
    sandbox_ids: frozenset[str] = field(default_factory=lambda: frozenset({ANY}))
    document_kinds: frozenset[str] = field(default_factory=lambda: frozenset({ANY}))
    actions: frozenset[str] = field(default_factory=lambda: frozenset({ANY}))

    def __post_init__(self) -> None:
        actor = _as_text(self.actor_id)
        if not actor:
            raise ValueError("datum_write_grant.actor_id is required")
        object.__setattr__(self, "actor_id", actor)
        for name in ("tool_ids", "sandbox_ids", "document_kinds", "actions"):
            object.__setattr__(
                self,
                name,
                _as_token_set(getattr(self, name), field_name=f"datum_write_grant.{name}"),
            )

    def covers(self, request: DatumWriteRequest) -> bool:
        return (
            self.actor_id == request.actor_id
            and _matches(self.tool_ids, request.tool_id)
            and _matches(self.sandbox_ids, request.sandbox_id)
            and _matches(self.document_kinds, request.document_kind)
            and _matches(self.actions, request.action)
        )


def _matches(allowed: frozenset[str], value: str) -> bool:
    return ANY in allowed or value in allowed


def require_datum_write(
    request: DatumWriteRequest, *, grants: tuple[DatumWriteGrant, ...] | list[DatumWriteGrant]
) -> None:
    """Return silently when a grant covers ``request``; raise otherwise.

    The single place the "a datum write must be granted" rule is enforced, so a call
    site cannot implement its own more lenient version of it — the same reason
    ``require_cipher`` exists rather than a per-caller ``if cipher is None`` check.

    There is no ``grants=None`` meaning "unrestricted". An empty grant set denies
    everything, which is the correct reading of "nobody has said this actor may
    write": a permission system that opens when its configuration is missing has the
    posture of one that is off.
    """
    for grant in grants or ():
        if grant.covers(request):
            return
    raise DatumWriteDenied(
        f"{request.actor_id!r} may not {request.action!r} "
        f"{request.document_kind!r} in {request.sandbox_id!r} via {request.tool_id!r}"
    )
