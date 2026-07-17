from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import (
    BinaryTextLens,
    EmailAddressLens,
    IdentityLens,
    Lens,
    NumericHyphenLens,
    SamrasTitleLens,
    SecretReferenceLens,
    TrimmedStringLens,
)

# Human-facing metadata for the Utilities → Lenses management surface, keyed by
# lens_id. (label, description). Lenses themselves stay pure codecs.
_LENS_METADATA: dict[str, tuple[str, str]] = {
    "trimmed_string": ("Trimmed text", "Strips surrounding whitespace on display."),
    "numeric_hyphen": ("Numeric hyphen", "Renders SAMRAS/HOPS node addresses as <a>-<b>-<c>."),
    "binary_text": ("Binary → ASCII", "Decodes a binary title blob to nominal ASCII text."),
    "samras_title": ("SAMRAS title", "Decodes a SAMRAS-encoded title."),
    "email_address": ("Email address", "Lowercases / normalizes an email address."),
    "secret_reference": ("Secret reference", "Renders a vault secret reference, never the value."),
}


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


@dataclass(frozen=True)
class LensResolution:
    lens: Lens
    matched_on: str
    token: str

    @property
    def lens_id(self) -> str:
        return _as_text(getattr(self.lens, "lens_id", "")) or "identity"


class DatumLensRegistry:
    """Resolve a bounded presentation lens for recognized datum families/kinds."""

    def __init__(self) -> None:
        self._family_lenses = {
            "nominal_babelette": BinaryTextLens(),
            "network_babelette": BinaryTextLens(),
            "title_babelette": BinaryTextLens(),
            "samras": NumericHyphenLens(),
            "samras_babelette": NumericHyphenLens(),
            "hops": NumericHyphenLens(),
            "hops_babelette": NumericHyphenLens(),
        }
        self._value_kind_lenses = {
            "binary_string": BinaryTextLens(),
            "numeric_hyphen": NumericHyphenLens(),
            "literal_text": TrimmedStringLens(),
            "tuple": IdentityLens(),
            "unknown": IdentityLens(),
        }
        self._overlay_lenses = {
            "title_babelette": BinaryTextLens(),
            "binary_overlay": BinaryTextLens(),
        }
        self._default_lens = IdentityLens()
        # Lens-id → lens, for resolving a hyphae-flag's bound lens_id. Covers the
        # full built-in surface so a flag can name any of them.
        self._by_lens_id = {
            lens.lens_id: lens
            for lens in (
                IdentityLens(),
                TrimmedStringLens(),
                NumericHyphenLens(),
                BinaryTextLens(),
                SamrasTitleLens(),
                EmailAddressLens(),
                SecretReferenceLens(),
            )
        }

    def lens_by_id(self, lens_id: object) -> Lens | None:
        return self._by_lens_id.get(_as_text(lens_id))

    def catalog(self) -> list[dict[str, Any]]:
        """All built-in lenses + what binds to each — powers the Utilities → Lenses
        management surface. Excludes ``identity`` (the always-on passthrough)."""
        bindings: dict[str, dict[str, list[str]]] = {
            lens_id: {"families": [], "value_kinds": [], "overlays": []}
            for lens_id in self._by_lens_id
        }
        for family, lens in self._family_lenses.items():
            bindings[lens.lens_id]["families"].append(family)
        for value_kind, lens in self._value_kind_lenses.items():
            bindings[lens.lens_id]["value_kinds"].append(value_kind)
        for overlay, lens in self._overlay_lenses.items():
            bindings[lens.lens_id]["overlays"].append(overlay)
        out: list[dict[str, Any]] = []
        for lens_id in sorted(self._by_lens_id):
            if lens_id == "identity":
                continue
            label, description = _LENS_METADATA.get(lens_id, (lens_id, ""))
            out.append(
                {
                    "lens_id": lens_id,
                    "label": label,
                    "description": description,
                    "bindings": {k: sorted(v) for k, v in bindings[lens_id].items()},
                }
            )
        return out

    def resolve(
        self,
        *,
        recognized_family: object = "",
        primary_value_kind: object = "",
        overlay_kind: object = "",
        flag_lens_id: object = "",
        enabled_lens_ids: object = None,
    ) -> LensResolution:
        resolution = self._resolve_binding(
            recognized_family=recognized_family,
            primary_value_kind=primary_value_kind,
            overlay_kind=overlay_kind,
            flag_lens_id=flag_lens_id,
        )
        # Control-Panel toggle: a lens the operator turned OFF falls back to the
        # always-on identity passthrough. ``enabled_lens_ids=None`` (the default)
        # means "no policy → everything enabled" — fully behavior-preserving.
        if enabled_lens_ids is not None:
            enabled = {_as_text(item) for item in enabled_lens_ids}
            if resolution.lens_id != "identity" and resolution.lens_id not in enabled:
                return LensResolution(lens=self._default_lens, matched_on="lens_disabled", token=resolution.lens_id)
        return resolution

    def _resolve_binding(
        self,
        *,
        recognized_family: object,
        primary_value_kind: object,
        overlay_kind: object,
        flag_lens_id: object,
    ) -> LensResolution:
        # Highest precedence: a hyphae-flag explicitly bound a lens to this datum
        # (by its canonical hyphae value). Falls through to the family/value-kind
        # resolution below when unset or unknown — so an empty flag registry is
        # fully behavior-preserving.
        flag_lens_token = _as_text(flag_lens_id)
        if flag_lens_token:
            flag_lens = self._by_lens_id.get(flag_lens_token)
            if flag_lens is not None:
                return LensResolution(lens=flag_lens, matched_on="hyphae_flag", token=flag_lens_token)
        family = _as_text(recognized_family).lower()
        if family in self._family_lenses:
            return LensResolution(lens=self._family_lenses[family], matched_on="family", token=family)
        overlay = _as_text(overlay_kind).lower()
        if overlay in self._overlay_lenses:
            return LensResolution(lens=self._overlay_lenses[overlay], matched_on="overlay", token=overlay)
        value_kind = _as_text(primary_value_kind).lower() or "unknown"
        if value_kind in self._value_kind_lenses:
            return LensResolution(lens=self._value_kind_lenses[value_kind], matched_on="value_kind", token=value_kind)
        return LensResolution(lens=self._default_lens, matched_on="fallback", token="identity")


DEFAULT_DATUM_LENS_REGISTRY = DatumLensRegistry()


def resolve_datum_lens(
    *,
    recognized_family: object = "",
    primary_value_kind: object = "",
    overlay_kind: object = "",
    flag_lens_id: object = "",
    enabled_lens_ids: object = None,
) -> LensResolution:
    return DEFAULT_DATUM_LENS_REGISTRY.resolve(
        recognized_family=recognized_family,
        primary_value_kind=primary_value_kind,
        overlay_kind=overlay_kind,
        flag_lens_id=flag_lens_id,
        enabled_lens_ids=enabled_lens_ids,
    )


__all__ = ["DEFAULT_DATUM_LENS_REGISTRY", "DatumLensRegistry", "LensResolution", "resolve_datum_lens"]
