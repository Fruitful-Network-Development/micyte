"""SMS provider port: one text message, sent on the instance's behalf — contract only."""

from .contracts import (
    OPERATION_MESSAGE_SEND,
    SERVICE_AWS_SNS,
    SmsMessage,
    SmsProviderError,
    SmsProviderPort,
)

__all__ = [
    "OPERATION_MESSAGE_SEND",
    "SERVICE_AWS_SNS",
    "SmsMessage",
    "SmsProviderError",
    "SmsProviderPort",
]
