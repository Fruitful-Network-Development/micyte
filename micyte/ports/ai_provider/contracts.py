"""Asking a hosted AI provider for a completion — the contract, and only the contract.

The ``channel.py`` discipline the commerce port restates: the platform declares the shape
of the thing and refuses without it; whoever runs the deployment supplies the parts that
are not the platform's to choose. Here that split is sharper than usual, because the part
MiCyte may not hold is the whole network half: **no HTTP client, no provider SDK and no
credential ever enters micyte/**. A provider adapter lives host-side
(``fnd_app/packages/peripherals/ai/``), takes its ``authorize`` gate at construction, and
implements :class:`AiProviderPort`; this module owns the question and the shape of the
answer.

One operation, at the withholdable grain
----------------------------------------
The external-call vocabulary (``micyte.ports.external_call_policy``) judges
``(service, operation)`` pairs, and the grain of an operation is *what an operator would
withhold separately*. For a chat provider today that is exactly one thing:
:data:`OPERATION_MESSAGES_CREATE` — the call that sends the operator's text to someone
else's computer and pays for the reply. ``models.list`` and ``embeddings.create`` are
named in the program plan as later grains; they are added when a feature calls them, not
before, because a declared operation nothing calls is decoration (the Quiar rule).

The service token is the PROVIDER (``"anthropic"``, ``"openai"``), so a grant can name one
provider without naming them all — the reason there is no umbrella ``"ai"`` service.

No degraded answer
------------------
A reply is text a person will read as the provider's words. There is no empty fallback and
no partial mode: an adapter that cannot answer raises :class:`AiCallFailed` with the
reason, because a blank reply rendered into a note reads as "the model said nothing",
which is a claim about the provider that nobody verified.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

#: The one operation this contract names today, spelled the way a grant withholds it.
OPERATION_MESSAGES_CREATE = "messages.create"

#: The roles a conversation turn may carry — the intersection every current provider
#: speaks, refused here rather than passed through to become one vendor's 400.
MESSAGE_ROLES = ("system", "user", "assistant")


class AiProviderError(ValueError):
    """A request to a provider is malformed before any network is involved."""


class AiCallFailed(RuntimeError):
    """The provider could not answer, and the reason is the message.

    Raised, never returned as empty text — the external-call README's rule: a failure
    flattened into a plausible value is invisible exactly when it matters.
    """


def _required(value: object, *, field_name: str) -> str:
    token = "" if value is None else str(value).strip()
    if not token:
        raise AiProviderError(f"{field_name} is required")
    return token


@dataclass(frozen=True)
class AiMessage:
    """One turn of the conversation being sent.

    ``text`` is required: an empty turn is not a smaller request, it is a request whose
    meaning the provider gets to invent.
    """

    role: str
    text: str

    def __post_init__(self) -> None:
        role = _required(self.role, field_name="ai_message.role")
        if role not in MESSAGE_ROLES:
            raise AiProviderError(
                f"ai_message.role must be one of {MESSAGE_ROLES}, not {role!r}")
        object.__setattr__(self, "role", role)
        object.__setattr__(
            self, "text", _required(self.text, field_name="ai_message.text"))

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "text": self.text}


@dataclass(frozen=True)
class AiReply:
    """What came back, attributed.

    ``provider`` and ``model`` are required so a reply is never anonymous — with two
    providers configured, the first question about a bad answer is which one gave it,
    the same attribution rule ``AvailabilityQuote.reservation_source`` carries.
    """

    provider: str
    model: str
    text: str

    def __post_init__(self) -> None:
        for field_name in ("provider", "model", "text"):
            object.__setattr__(
                self, field_name,
                _required(getattr(self, field_name), field_name=f"ai_reply.{field_name}"))

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.model, "text": self.text}


def require_api_key(key: object, *, provider: str) -> str:
    """The ``require_cipher`` discipline for the credential.

    An adapter constructed without a key would fail at the provider with a vendor 401
    three layers from the cause; this names the actual state — the operator has not
    configured the credential — at the door.
    """
    token = "" if key is None else str(key).strip()
    if not token:
        raise AiCallFailed(
            f"no api key is configured for {provider!r} — the credential lives in the "
            "instance's private files (never MOS), and until the operator supplies it "
            "there is nothing to call with")
    return token


@runtime_checkable
class AiProviderPort(Protocol):
    """The outbound seam: one provider, asked for one completion.

    Implementations take ``*, authorize`` at construction and judge
    :data:`OPERATION_MESSAGES_CREATE` inside the same function body that opens the
    network — the shape the AST egress sweep verifies.
    """

    @property
    def provider_id(self) -> str:
        """Which provider this is — the external-call SERVICE token, for attribution."""

    def create_message(
        self, *, model: str, messages: tuple[AiMessage, ...], max_tokens: int,
    ) -> AiReply:
        """Send the turns, return the attributed reply. Raises :class:`AiCallFailed`."""


__all__ = [
    "MESSAGE_ROLES",
    "OPERATION_MESSAGES_CREATE",
    "AiCallFailed",
    "AiMessage",
    "AiProviderError",
    "AiProviderPort",
    "AiReply",
    "require_api_key",
]
