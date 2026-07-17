# 81 — Lens Authoring Guide

> Status: how-to
> [← Overview](00-overview-and-glossary.md)

## Goal

Teach you how to author a **lens** for the portal workbench. A lens is a small,
stateless codec that applies a workbench **display** change without touching how
a datum is stored. The motivating example: a datum whose canonical value is a
raw **binary magnitude** (a `0`/`1` bit string) can be shown in the workbench as
its **nominal ASCII value** (human-readable text) — and written back as the
canonical binary. That exact transform already ships as `BinaryTextLens` and is
the lens you will model your own on.

Today, a lens is selected automatically for a datum based on its **recognized
family** or its **primary value kind** (and, secondarily, an overlay kind). You
author one by:

1. implementing a `Lens` subclass (`decode` / `encode` / `validate_display`),
2. registering it under the right key in `DatumLensRegistry`, and
3. confirming the workbench resolves and applies it.

> **Heads up — the vision vs. today.** The product vision is that lenses are
> *managed* from a Utilities page and *toggled ON/OFF* from the Control Panel,
> keyed off a datum's flagged hyphae value or a family's root common datum.
> **None of that exists yet.** Lenses auto-apply by family/value-kind, there is
> no manage page, no on/off toggle, and no first-class hyphae-value flag
> binding. This guide teaches the *real* way to add a lens today and clearly
> marks the future model in its own section below.

## Prerequisites

### The `Lens` contract

Every lens is a stateless codec defined by the abstract base class in
[`MyCiteV2/packages/state_machine/lens/base.py:13`](../../MyCiteV2/packages/state_machine/lens/base.py):

```python
class Lens(ABC):
    """Stateless codec overlay for display/canonical transforms."""

    lens_id = "lens"

    @abstractmethod
    def decode(self, canonical_value: Any) -> Any:   # canonical -> what the workbench shows
        raise NotImplementedError

    @abstractmethod
    def encode(self, display_value: Any) -> Any:     # what the user typed -> canonical (stored)
        raise NotImplementedError

    def validate_display(self, display_value: Any) -> tuple[str, ...]:
        del display_value
        return ()                                    # tuple of issue codes; () means OK
```

The three methods and their roles
([`base.py:18`](../../MyCiteV2/packages/state_machine/lens/base.py)):

- **`decode(canonical_value)` → display value.** Called on the read path to turn
  the stored canonical value into what the workbench renders. This is where the
  binary→ASCII transform lives.
- **`encode(display_value)` → canonical value.** Called on the write/staging
  path to turn the user-entered display value back into the canonical value that
  gets stored. `decode` and `encode` must round-trip (see Pitfalls).
- **`validate_display(display_value)` → tuple of issue codes.** Returns an empty
  tuple when the input is acceptable, or a tuple of short string codes (e.g.
  `("binary_text_invalid",)`) when it is not. The base implementation returns
  `()` (accept everything); override it when your lens has constraints.

Each lens also sets a unique class attribute `lens_id`
([`base.py:16`](../../MyCiteV2/packages/state_machine/lens/base.py)) — a short
stable string used to label the lens in surfaces and in the staging envelope.

### Where lenses live

| Concern | File |
| --- | --- |
| Abstract `Lens` + built-in lenses | [`MyCiteV2/packages/state_machine/lens/base.py`](../../MyCiteV2/packages/state_machine/lens/base.py) |
| Family / value-kind / overlay dispatch | [`MyCiteV2/packages/state_machine/lens/registry.py`](../../MyCiteV2/packages/state_machine/lens/registry.py) |
| Public exports | [`MyCiteV2/packages/state_machine/lens/__init__.py`](../../MyCiteV2/packages/state_machine/lens/__init__.py) |
| Package authority notes | [`MyCiteV2/packages/state_machine/lens/README.md`](../../MyCiteV2/packages/state_machine/lens/README.md) |
| Display application (read path) | [`MyCiteV2/packages/tools/workbench_ui/service.py`](../../MyCiteV2/packages/tools/workbench_ui/service.py) |
| Encode + validate on write (staging) | [`MyCiteV2/packages/state_machine/nimm/staging.py`](../../MyCiteV2/packages/state_machine/nimm/staging.py) |
| Registry tests | [`MyCiteV2/tests/unit/test_state_machine_lens_registry.py`](../../MyCiteV2/tests/unit/test_state_machine_lens_registry.py) |

The built-in lenses you can reuse or subclass (all in
[`base.py`](../../MyCiteV2/packages/state_machine/lens/base.py)): `IdentityLens`
(pass-through), `TrimmedStringLens` (trims whitespace; a convenient base),
`SamrasTitleLens`, `EmailAddressLens`, `SecretReferenceLens`,
`NumericHyphenLens`, and `BinaryTextLens` (binary→ASCII with a bit-count
fallback — the nominal-ASCII example).

## Step-by-step

### 1. Implement a `Lens` subclass

Subclass `Lens` directly, or — more commonly — subclass `TrimmedStringLens`
([`base.py:41`](../../MyCiteV2/packages/state_machine/lens/base.py)) when your
canonical value is text and you want whitespace trimming for free. Give it a
unique `lens_id`. Implement the methods your transform needs; `TrimmedStringLens`
already provides a sane `decode`/`encode`, so you only override what differs.

Sketch (not added to the codebase — illustrative):

```python
class MyExampleLens(TrimmedStringLens):
    lens_id = "my_example"

    def decode(self, canonical_value: Any) -> str:
        # canonical (stored) -> display (shown in the workbench)
        ...

    def encode(self, display_value: Any) -> str:
        # display (user input) -> canonical (stored)
        ...

    def validate_display(self, display_value: Any) -> tuple[str, ...]:
        # return () if acceptable, else a tuple of short issue codes
        ...
```

Keep the lens **stateless and pure**: no I/O, no shared mutable state, no
network. The registry holds one shared instance per key (see step 3), so any
hidden state would leak across datums.

### 2. Choose a decode / encode round-trip

Decide the canonical (stored) form and the display (shown/edited) form, then make
sure they round-trip. The rule of thumb: for any reasonable display value `d`,
`decode(encode(d))` should reproduce `d` (modulo deliberate normalization such as
trimming or case-folding). The canonical value is the source of truth; the
display value is derived.

`BinaryTextLens` shows how a *deliberate* asymmetry can be valid:

- `encode` keeps the binary string as-is (inherited from `TrimmedStringLens`),
  so the **canonical value stored is always the bit string**.
- `decode` turns a printable bit string into ASCII text *for display only*, and
  falls back to a `"<N> bits"` summary when the bits are not printable.

So `BinaryTextLens` is effectively a **read-oriented** lens: it never rewrites
the canonical magnitude, it only makes it legible. Your lens may be symmetric
(like `EmailAddressLens`, which lowercases on `encode`) or read-oriented (like
`BinaryTextLens`) — choose deliberately and document which.

### 3. Register it under the right key in `DatumLensRegistry`

Auto-resolution lives in
[`MyCiteV2/packages/state_machine/lens/registry.py`](../../MyCiteV2/packages/state_machine/lens/registry.py).
`DatumLensRegistry.__init__`
([`registry.py:28`](../../MyCiteV2/packages/state_machine/lens/registry.py))
holds three dispatch maps, and `resolve`
([`registry.py:51`](../../MyCiteV2/packages/state_machine/lens/registry.py))
checks them **in priority order**:

1. **`_family_lenses`** — keyed by `recognized_family` (e.g.
   `"nominal_babelette"` → `BinaryTextLens()`)
   ([`registry.py:29`](../../MyCiteV2/packages/state_machine/lens/registry.py)).
   **Highest priority.**
2. **`_overlay_lenses`** — keyed by `overlay_kind`
   ([`registry.py:45`](../../MyCiteV2/packages/state_machine/lens/registry.py)).
3. **`_value_kind_lenses`** — keyed by `primary_value_kind` (e.g.
   `"binary_string"` → `BinaryTextLens()`)
   ([`registry.py:38`](../../MyCiteV2/packages/state_machine/lens/registry.py)).
4. Falls back to `IdentityLens` (`matched_on="fallback"`) if nothing matches
   ([`registry.py:67`](../../MyCiteV2/packages/state_machine/lens/registry.py)).

To wire in your lens, add an instance under the appropriate key. Bind to a
**family** when every datum in that recognized family should get the lens; bind
to a **value kind** when the transform follows the value's shape regardless of
family; bind to an **overlay** for an overlay-specific projection. Example
(family binding):

```python
self._family_lenses = {
    "nominal_babelette": BinaryTextLens(),
    # ...existing keys...
    "my_family": MyExampleLens(),   # <- your registration
}
```

All keys are lowercased before lookup — `resolve` calls `_as_text(...).lower()`
on the inputs
([`registry.py:58`](../../MyCiteV2/packages/state_machine/lens/registry.py)) — so
register keys in lower case. If your lens lives in a new module, also export it
from
[`MyCiteV2/packages/state_machine/lens/__init__.py`](../../MyCiteV2/packages/state_machine/lens/__init__.py)
so callers can import it by name.

### 4. Confirm the workbench applies it

The read path is in the workbench UI read service. For each datum row,
`_row_items` calls `resolve_datum_lens(...)` with the row's recognized family,
primary value kind, and overlay kind
([`service.py:528`](../../MyCiteV2/packages/tools/workbench_ui/service.py)), then
calls the resolved lens's `decode` on the row's `primary_value_token` to build
the `display_value`
([`service.py:533`](../../MyCiteV2/packages/tools/workbench_ui/service.py)):

```python
lens_resolution = resolve_datum_lens(
    recognized_family=recognized_family,
    primary_value_kind=render_hints.get("primary_value_kind"),
    overlay_kind=render_hints.get("overlay_kind"),
)
display_value = _first_non_empty(
    lens_resolution.lens.decode(primary_value_token) if primary_value_token else "",
    _joined_labels(row.raw),
    _object_ref(row.raw, datum_address=row.datum_address),
)
```

The row also carries `resolved_lens` (the `lens_id`) and `resolved_lens_match`
(which map matched: `family` / `overlay` / `value_kind` / `fallback`)
([`service.py:558`](../../MyCiteV2/packages/tools/workbench_ui/service.py)), and
the selected row surfaces them in a "Lens Resolution" interface panel
([`service.py:846`](../../MyCiteV2/packages/tools/workbench_ui/service.py)). Use
those fields to verify your lens resolved as intended: a matching datum should
report your `lens_id` with the expected `resolved_lens_match`.

### 5. Add validation messages (write path)

On the write/staging path, `StagingArea.stage_with_lens`
([`staging.py:60`](../../MyCiteV2/packages/state_machine/nimm/staging.py)) runs
your lens against the user's display input:

```python
issues = lens.validate_display(display_value)
canonical_value = lens.encode(display_value)
replacement = StagedValue(
    target=normalized_target,
    lens_id=_as_text(getattr(lens, "lens_id", "lens")) or "lens",
    display_value=display_value,
    canonical_value=canonical_value,
    validation_issues=issues,
)
```

So `validate_display` runs **before** `encode`, and its issue codes are stored on
the `StagedValue` and carried into the compiled NIMM manipulation envelope
([`staging.py:90`](../../MyCiteV2/packages/state_machine/nimm/staging.py)). Return
short, stable, machine-readable codes (snake_case), not prose — mirror the
built-ins. For example, `BinaryTextLens.validate_display`
([`base.py:139`](../../MyCiteV2/packages/state_machine/lens/base.py)) returns
`("binary_text_required",)` for empty input and `("binary_text_invalid",)` when
any character is not `0`/`1`. Surfaces map these codes to human messages; the
lens only emits the codes.

## Worked example — `BinaryTextLens`

`BinaryTextLens` ([`base.py:115`](../../MyCiteV2/packages/state_machine/lens/base.py))
is the canonical "show the nominal ASCII value instead of the raw binary
magnitude" lens. It subclasses `TrimmedStringLens`, so `encode` is inherited:
the **canonical value stored stays the binary string** (only trimmed). All the
interesting work is in `decode`:

```python
class BinaryTextLens(TrimmedStringLens):
    lens_id = "binary_text"

    def decode(self, canonical_value: Any) -> str:
        token = _as_text(canonical_value)
        if not token:
            return ""
        if any(bit not in {"0", "1"} for bit in token):
            return token                              # not binary -> show as-is
        groups = [token[index : index + 8] for index in range(0, len(token), 8)]
        chars: list[str] = []
        for group in groups:
            if len(group) < 8:
                break                                 # trailing partial byte
            value = int(group, 2)
            if value == 0:
                break                                 # NUL terminates
            if 32 <= value <= 126:
                chars.append(chr(value))              # printable ASCII
                continue
            return f"{len(token)} bits"               # non-printable -> bit-count fallback
        decoded = "".join(chars).strip()
        return decoded or f"{len(token)} bits"
```

Reading the decode path:

1. Empty canonical → empty display.
2. If any character is not `0`/`1`, it is not a binary magnitude, so return it
   verbatim (defensive pass-through).
3. Otherwise split into 8-bit groups. For each full byte: stop at a NUL (`0`),
   append the character if it is printable ASCII (`32–126`), and **fall back to
   `"<N> bits"`** the moment a byte is non-printable.
4. If decoding yields nothing usable, fall back to the `"<N> bits"` summary.

That `"<N> bits"` **bit-count fallback** is the key design move: a lens that
makes a value legible when it can must still produce *something* honest when it
cannot — never an exception, never a misleading partial string.

`validate_display` ([`base.py:139`](../../MyCiteV2/packages/state_machine/lens/base.py))
guards the write side: a stored canonical value must be a non-empty pure-binary
string (`("binary_text_required",)` / `("binary_text_invalid",)`).

The registry maps three recognized families and the `binary_string` value kind
to this lens
([`registry.py:29`](../../MyCiteV2/packages/state_machine/lens/registry.py)), so
e.g. a `nominal_babelette` datum automatically renders its binary magnitude as
nominal ASCII text in the workbench, with no per-datum configuration.

## Pitfalls

- **`decode` / `encode` must round-trip.** Display is derived from canonical;
  re-encoding the displayed value must reproduce the canonical value (modulo
  intentional normalization like trimming or case-folding). If you cannot make
  it round-trip safely, make the lens **read-oriented** like `BinaryTextLens`
  (keep `encode` a faithful pass-through and only beautify in `decode`) rather
  than silently rewriting the stored value.
- **The canonical value is what is stored; the display is throwaway.** The
  workbench shows `decode(...)` output; the catalog/MOS holds the canonical
  value, and the staging envelope carries `encode(...)` output. Never let a lens
  smuggle display formatting into the canonical value.
- **Keep lenses pure and bounded.** No I/O, no global state, no unbounded work.
  Registry instances are shared across every datum that matches a key, so hidden
  state corrupts other rows. Bound the output (cf. the `"<N> bits"` fallback) and
  never raise on malformed input — return a safe display string or an issue code.
- **Resolution is priority-ordered.** `family` beats `overlay` beats
  `value_kind` beats the identity fallback
  ([`registry.py:51`](../../MyCiteV2/packages/state_machine/lens/registry.py)).
  If your lens does not appear to apply, check whether a higher-priority key
  already matched the datum.
- **Register keys in lower case.** `resolve` lowercases its inputs before lookup
  ([`registry.py:58`](../../MyCiteV2/packages/state_machine/lens/registry.py)),
  so an upper/mixed-case key will never match.
- **Emit codes, not sentences.** `validate_display` returns short snake_case
  issue codes; human-readable copy is the surface's job.

## Future: managed lenses & toggles

> **Not yet built.** Everything in this section describes the intended product
> model. As of today it does **not** exist in the code — lenses auto-apply by
> `recognized_family` / `primary_value_kind` (and overlay), there is no manage
> page, no on/off control, and no hyphae-value flag binding. Author lenses using
> the steps above; treat this section as forward-looking design only.

The vision:

- **Managed from a Utilities page.** A lens catalog will be authored/curated from
  a dedicated Utilities surface — discover available lenses, see which datum
  families or value flags they apply to, and manage the bindings there rather
  than by editing `DatumLensRegistry` in code.
- **Turned ON/OFF from the Control Panel.** Whether a lens is *active* for a
  given surface/session will be a Control-Panel toggle, decoupling "a lens
  exists and is bound" (Utilities) from "a lens is currently applied" (Control
  Panel). Today the closest analogue is the workbench `interpreted` vs `raw`
  lens mode ([`service.py:34`](../../MyCiteV2/packages/tools/workbench_ui/service.py)),
  which is a coarse global switch, not a per-lens toggle.
- **Bound to a flagged hyphae VALUE or a family's root common datum.** Lenses
  will key off a datum's **flagged hyphae value** or a **family's root common
  datum**, not only the recognized family / value kind they dispatch on today.
  This makes a lens a first-class property you can attach to a value, abstracted
  from a common datum.

For the canonical-datum and hyphae-flag model these bindings will build on, see
[60 — Canonical Datum and Hyphae Flags](60-canonical-datum-and-hyphae-flags.md).
For where lenses sit in the broader as-built tooling picture (and the gap
between today's auto-resolution and the managed model), see
[40 — Tools and Lenses, As-Built](40-tools-and-lenses-asbuilt.md).

## Testing your lens

Follow the pattern in
[`MyCiteV2/tests/unit/test_state_machine_lens_registry.py`](../../MyCiteV2/tests/unit/test_state_machine_lens_registry.py).
It is a plain `unittest` module with two kinds of checks you should replicate:

```python
from MyCiteV2.packages.state_machine.lens import BinaryTextLens, resolve_datum_lens


class StateMachineLensRegistryTests(unittest.TestCase):
    def test_binary_text_lens_decodes_printable_ascii(self) -> None:
        self.assertEqual(BinaryTextLens().decode("0100000101000010"), "AB")

    def test_registry_prefers_family_then_value_kind(self) -> None:
        self.assertEqual(
            resolve_datum_lens(recognized_family="nominal_babelette").lens_id,
            "binary_text",
        )
        self.assertEqual(
            resolve_datum_lens(primary_value_kind="numeric_hyphen").lens_id,
            "numeric_hyphen",
        )
```

For your own lens, add:

1. **A codec test** — exercise `decode` (including any fallback branch) and
   `encode`, and assert a representative `decode(encode(value))` round-trip.
2. **A validation test** — assert `validate_display` returns `()` for good input
   and your specific issue codes for bad input.
3. **A resolution test** — call `resolve_datum_lens(...)` with the family /
   value-kind / overlay you registered under and assert `.lens_id` equals your
   lens's `lens_id` (and, if you care about priority, that a higher-priority key
   still wins).

Run just this module from the repo root:

```bash
python -m pytest MyCiteV2/tests/unit/test_state_machine_lens_registry.py
```

## See also

- [00 — Overview and Glossary](00-overview-and-glossary.md)
- [40 — Tools and Lenses, As-Built](40-tools-and-lenses-asbuilt.md) *(forward ref)*
- [60 — Canonical Datum and Hyphae Flags](60-canonical-datum-and-hyphae-flags.md) *(forward ref)*
- [`lens/README.md`](../../MyCiteV2/packages/state_machine/lens/README.md) — package authority + contract notes
- [`lens/base.py`](../../MyCiteV2/packages/state_machine/lens/base.py) — `Lens` + built-ins
- [`lens/registry.py`](../../MyCiteV2/packages/state_machine/lens/registry.py) — `DatumLensRegistry` dispatch
- [`workbench_ui/service.py`](../../MyCiteV2/packages/tools/workbench_ui/service.py) — display application
- [`nimm/staging.py`](../../MyCiteV2/packages/state_machine/nimm/staging.py) — encode + validate on write
