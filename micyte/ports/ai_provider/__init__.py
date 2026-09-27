"""AI provider port: one hosted model, asked for one completion — contract only."""

from .contracts import (
    MESSAGE_ROLES,
    OPERATION_MESSAGES_CREATE,
    AiCallFailed,
    AiMessage,
    AiProviderError,
    AiProviderPort,
    AiReply,
    require_api_key,
)

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
