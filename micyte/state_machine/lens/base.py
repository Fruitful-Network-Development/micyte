from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


class Lens(ABC):
    """Stateless codec overlay for display/canonical transforms."""

    lens_id = "lens"

    @abstractmethod
    def decode(self, canonical_value: Any) -> Any:
        raise NotImplementedError

    @abstractmethod
    def encode(self, display_value: Any) -> Any:
        raise NotImplementedError

    def validate_display(self, display_value: Any) -> tuple[str, ...]:
        del display_value
        return ()


class IdentityLens(Lens):
    lens_id = "identity"

    def decode(self, canonical_value: Any) -> Any:
        return canonical_value

    def encode(self, display_value: Any) -> Any:
        return display_value


class TrimmedStringLens(Lens):
    lens_id = "trimmed_string"

    def decode(self, canonical_value: Any) -> str:
        return _as_text(canonical_value)

    def encode(self, display_value: Any) -> str:
        return _as_text(display_value)


class SamrasTitleLens(TrimmedStringLens):
    lens_id = "samras_title"

    def encode(self, display_value: Any) -> str:
        return " ".join(_as_text(display_value).split()).upper()

    def validate_display(self, display_value: Any) -> tuple[str, ...]:
        value = self.encode(display_value)
        if not value:
            return ("title_required",)
        try:
            value.encode("ascii")
        except UnicodeEncodeError:
            return ("title_must_be_ascii",)
        return ()


class EmailAddressLens(TrimmedStringLens):
    lens_id = "email_address"

    def encode(self, display_value: Any) -> str:
        return _as_text(display_value).lower()

    def validate_display(self, display_value: Any) -> tuple[str, ...]:
        value = self.encode(display_value)
        if not value:
            return ("email_required",)
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            return ("email_invalid",)
        return ()


class SecretReferenceLens(TrimmedStringLens):
    lens_id = "secret_reference"

    def decode(self, canonical_value: Any) -> str:
        value = _as_text(canonical_value)
        return value if value else "not_configured"

    def encode(self, display_value: Any) -> str:
        return _as_text(display_value)

    def validate_display(self, display_value: Any) -> tuple[str, ...]:
        value = self.encode(display_value)
        if not value:
            return ("secret_reference_required",)
        if "password" in value.lower():
            return ("secret_reference_must_not_contain_secret_value",)
        return ()


class NumericHyphenLens(TrimmedStringLens):
    lens_id = "numeric_hyphen"

    def validate_display(self, display_value: Any) -> tuple[str, ...]:
        value = self.encode(display_value)
        if not value:
            return ("numeric_hyphen_required",)
        parts = value.split("-")
        if any(not part.isdigit() for part in parts):
            return ("numeric_hyphen_invalid",)
        return ()


class BinaryTextLens(TrimmedStringLens):
    lens_id = "binary_text"

    def decode(self, canonical_value: Any) -> str:
        token = _as_text(canonical_value)
        if not token:
            return ""
        if any(bit not in {"0", "1"} for bit in token):
            return token
        groups = [token[index : index + 8] for index in range(0, len(token), 8)]
        chars: list[str] = []
        for group in groups:
            if len(group) < 8:
                break  # trailing partial byte — nothing decodable left
            value = int(group, 2)
            if value == 0:
                break  # NUL terminates the encode_label 512-bit zero padding
            if 32 <= value <= 126:
                chars.append(chr(value))
                continue
            # Non-printable byte: keep the readable run and mark the gap rather than
            # discarding the whole decode (which would hide a legible prefix).
            chars.append("·")
        decoded = "".join(chars).strip()
        return decoded or f"{len(token)} bits"

    def validate_display(self, display_value: Any) -> tuple[str, ...]:
        value = self.encode(display_value)
        if not value:
            return ("binary_text_required",)
        if any(bit not in {"0", "1"} for bit in value):
            return ("binary_text_invalid",)
        return ()
