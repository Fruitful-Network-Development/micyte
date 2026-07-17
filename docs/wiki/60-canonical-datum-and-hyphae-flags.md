# Canonical Datum & Hyphae Flags

> Status: design-spec — **CORRECTED 2026-06-01**

[← Overview](00-overview-and-glossary.md)

> **Correction (supersedes parts of this page).** An earlier draft framed the
> canonical hyphae value as a *minimum-complete, address-independent* fold that
> **excludes** the unreferenced rudi prefix, and proposed "retiring the
> rudi-range fill." **That is wrong.** Per the authoritative MOS spec
> (`docs/personal_notes/MOS/mycelial_ontological_schema.md` and
> `docs/contracts/mss_binary_sequence/`), the canonical hyphae value **must
> include all preceding rudi datums even if not used directly** (e.g. an
> abstraction using `0-0-5` includes `0-0-1`..`0-0-5`). The rudis are the
> ordinal/incremental/nominal frames; the value is canonical *because* it is
> anchored to the universal rudi starting position. So the rudi scaffold is
> retained, never retired, and the value is *not* "address-independent" in the
> sense earlier claimed. `compile_hyphae_value` now carries the rudi context.
> Read the "minimum-but-complete / address-independent" passages below in that
> light.

This page specifies how a **canonical datum** earns a stable, content-derived
identity (a **hyphae value**), how that value "raises a flag," and how that flag
becomes the binding key for **lenses** and **tools**. Everything under "Proposed
model" and after is a *proposal*; the "Current reality" section describes what
ships today.

---

## Problem

The near-term tool-building effort needs a way to say: *"this exact kind of
datum — wherever it appears, in any document, in any tenant — should show with
this lens and offer these tools."* That binding has to survive the datum being
copied, re-nested, renamed, or re-addressed, because a `layer-vg-iteration`
address is positional and changes under ordinary edits (insert/move shift every
sibling's iteration — see `preview_document_insert` /
`preview_document_move` in
`MyCiteV2/packages/adapters/sql/datum_semantics.py:474` and `:587`).

Today binding is keyed on two coarse, *non-canonical* signals:

1. **Archetype / source-kind strings** for tools
   (`recognize_applicable_tools` in
   `MyCiteV2/packages/state_machine/portal_shell/tool_eligibility.py:64`), and
2. **`recognized_family` / `value_kind` / overlay strings** for lenses
   (`DatumLensRegistry.resolve` in
   `MyCiteV2/packages/state_machine/lens/registry.py:51`).

Both are insufficient against the vision:

- **A family string is a *bucket*, not an identity.** `recognized_family` is one
  of a tiny closed vocabulary — `nominal_babelette`, `network_babelette`,
  `samras`, `hops`, … derived purely from a substring match on the anchor label
  (`_family_contract` in
  `MyCiteV2/packages/modules/domains/datum_recognition/service.py:126`). Two
  datums that are semantically different but share an anchor label collapse to
  the same family, and a datum whose anchor label is unrecognized falls to
  `unrecognized_family` (`service.py:533`) and binds to nothing. There is no way
  to flag *one specific datum* or *one specific family root*.

- **Archetype binding is widened, not exact.** `recognize_applicable_tools`
  derives an archetype *set* from document metadata plus every rudi row reached
  through the hyphae chain, then offers any tool whose `applies_to_archetype`
  *intersects* that set (`tool_eligibility.py:96`–`112`). This is a deliberately
  broad "anything upstream applies" rule — useful for a generic palette, useless
  as the precise `datum → tool` binding the vision calls for.

- **Neither key is content-canonical.** Nothing here is keyed on the compiled
  MSS form of the datum. There is no registry anywhere that maps a *hyphae
  value* to a tool or a lens. The richer per-row `hyphae_hash` that the SQL
  engine already computes (see below) is computed, stored, and then **never
  consulted** for tool or lens binding.

The vision: compile the datum's MSS along its **minimum-but-complete underlying
path of datum abstraction**, hash it to a **hyphae value**, and use a match
against a **registry of registered hyphae values** as the binding key. That is
the mechanism this page specs.

---

## Current reality

Cited facts, each read from the file before citing.

### 1. The core hyphae chain is fully inclusive — no minimum-but-complete path

`derive_hyphae_chain` in
`MyCiteV2/packages/core/mss/datum_identity.py:126` returns **every** rudi address
`0-0-1 .. 0-0-K`, where `K` is the highest rudi iteration reachable in the
transitive dependency closure of the target address. The docstring is explicit:
*"Every position 1..K is included even if not directly referenced by
datum_address"* (`datum_identity.py:134`–`135`), and the implementation fills the
range `range(1, max_k + 1)` (`datum_identity.py:172`–`177`). So:

- It is **fully inclusive**: it does not prune to the datums the target actually
  depends on.
- It performs **no focus exclusion**: the target row's own non-rudi abstraction
  is not isolated.
- It returns only the **rudi prefix** (`layer=0, value_group=0`), not the
  minimal closure of mixed-layer datums that *define* the target.

### 2. The MSS version hash is whole-document, not per-datum-path

`compute_mss_hash` in `MyCiteV2/packages/core/mss/datum_identity.py:101` hashes a
canonical payload of **all** sorted rows plus `source_kind` and
`document_metadata` (`datum_identity.py:110`–`123`). It is a *document version*
identity, not a *single datum's* canonical identity, and it has no notion of an
abstraction path.

### 3. The richer per-row semantic + hyphae engine exists — but in the SQL adapter

`MyCiteV2/packages/adapters/sql/datum_semantics.py` is the engine that actually
computes content-derived identities:

- `build_document_version_identity` (`datum_semantics.py:136`) produces the same
  whole-document `version_hash` as `compute_mss_hash` (the core function's
  docstring says so at `datum_identity.py:104`–`106`).
- `build_document_semantics` (`datum_semantics.py:209`) computes, **per row**, a
  `semantic_hash` (`datum_semantics.py:226`–`258`, recursively folding each
  local dependency's hash so the value is content-canonical and
  address-independent) and a `hyphae_hash`
  (`datum_semantics.py:314`–`324`) over the row's ordered abstraction chain,
  anchored by an `anchor_context_hash` (`datum_semantics.py:219`–`220`). Each
  row also gets a `hyphae_chain` object listing the chain `addresses` and their
  semantic hashes (`datum_semantics.py:325`–`331`).

This is **closer to the vision** than the core function — it is per-datum and
content-derived — but its `hyphae_chain` still prepends the *full* rudi prefix
`range(1, max_rudi + 1)` (`datum_semantics.py:296`–`301`) before the closure, so
it is still **inclusive, not minimum-but-complete**.

### 4. There is a core → adapter import inversion

`MyCiteV2/packages/core/datum_ops/ops.py:24` and
`MyCiteV2/packages/core/datum_ops/node_ops.py:17` both import
(`parse_datum_address`, `preview_document_*`) **from**
`MyCiteV2.packages.adapters.sql.datum_semantics`. A core package depending on a
SQL adapter is an inversion of the dependency direction. A separate wiki unit
covers relocating this engine to `core/datum_semantics/`; this page assumes that
relocation as a prerequisite (see Migration path) and forward-refs
`05-engineering-standards.md`.

### 5. Tool binding has no hyphae-value registry

`recognize_applicable_tools`
(`MyCiteV2/packages/state_machine/portal_shell/tool_eligibility.py:64`) matches
`applies_to_archetype` / `applies_to_source_kind`
(`tool_eligibility.py:104`–`110`), widened via `derive_hyphae_chain`
(`tool_eligibility.py:92`). `PortalToolRegistryEntry`
(`MyCiteV2/packages/state_machine/portal_shell/shell.py:477`) carries
`applies_to_archetype`, `applies_to_source_kind`, and a reserved-but-unconsumed
`manipulates_datum_kinds` (`shell.py:490`–`499`) — but **no hyphae-value field**.
There is no registry keyed on a hyphae VALUE.

### 6. Lens binding resolves by family / value-kind / overlay strings

`DatumLensRegistry` (`MyCiteV2/packages/state_machine/lens/registry.py:25`)
holds three string-keyed dicts — `_family_lenses`, `_value_kind_lenses`,
`_overlay_lenses` (`registry.py:29`–`48`) — and `resolve`
(`registry.py:51`–`67`) checks them in that order, falling back to
`IdentityLens`. The keys are the recognition vocabulary from `_family_contract`
(`service.py:126`–`142`), e.g. `samras` → `NumericHyphenLens`,
`nominal_babelette` → `BinaryTextLens`. None of these keys is a hyphae value;
the registry never sees one.

### 7. `recognized_family` is a substring match on an anchor label

`_family_contract`
(`MyCiteV2/packages/modules/domains/datum_recognition/service.py:126`) maps an
anchor label to `(family, value_kind, overlay_kind)` by substring tests
(`"samras" in label`, `"hops" in label`, etc.). `_build_reference_bindings`
(`service.py:476`) takes the **first** recognized family it sees on the row
(`service.py:534`–`538`) and otherwise emits `unrecognized_family`
(`service.py:533`). Families today are therefore label heuristics, not roots in a
structural family tree.

---

## Proposed model

> **Proposal.** None of the following ships today.

### A. The minimum-but-complete abstraction path (plain terms)

For a target datum `T` in a compiled document, walk `T`'s **local dependency
graph** (the same `_row_local_refs` edge relation used today —
`datum_semantics.py:101`) and keep a datum on the path **iff** it is *required to
define `T`*:

1. Start from `T`. Include `T`.
2. Follow each local reference edge from a kept node to the datum it points at;
   include that datum. Repeat transitively.
3. **Stop at each branch** when you reach a datum with no further outgoing
   reference edges (a rudi / leaf magnitude).
4. The path is the **minimal closure** so reached — every datum that
   participates in defining `T`, and **no others**.

This differs from today's chain in two concrete ways:

- **No rudi-range fill.** We do *not* prepend `0-0-1 .. 0-0-K`. We include only
  the rudis (and intermediate datums) actually on a dependency edge from `T`.
  Contrast `datum_semantics.py:296`–`301` and `datum_identity.py:172`–`177`,
  which both fill the whole range.
- **Focus is the root, not a sibling.** `T` is the path root; sibling datums in
  `T`'s family that `T` does not reference are excluded ("focus exclusion").

"Minimum-but-complete" = the *smallest* node set that still *fully* determines
`T`'s meaning. Whether the path is rooted per-datum or per-family is an open
question (below).

### B. Compiling MSS along that path → the canonical hyphae VALUE

"Compile MSS along the path" means: take the path's datums **in
dependency-resolved order** and fold each one's *content* into a single hash, the
way `build_document_semantics` already folds `semantic_hash` recursively
(`datum_semantics.py:244`–`256`) — but over the *minimum-but-complete* path
instead of the inclusive chain. The fold MUST be:

- **Content-canonical / address-independent** — re-nesting or re-addressing `T`
  (an insert/move that shifts iterations) must not change the value. The
  existing `semantic_hash` already achieves this by replacing addresses with
  `local_ref` semantic hashes (`_remap_semantic_raw`, `datum_semantics.py:160`).
- **Anchor-context aware** — folded under the document's `anchor_context_hash`
  (`datum_semantics.py:219`) so the same bytes under a different anchor
  vocabulary do not falsely collide.
- **Deterministic** — canonical JSON, sorted keys (as `_sha256_token` /
  `dumps_json` already do, `datum_semantics.py:53`).

The result is the datum's **hyphae value**: a single token, e.g.
`sha256:…`, that *is* the canonical reference to that datum. The exact byte/JSON
form of "MSS" along the path (bitstream vs. JSON rows) is deferred to
`61-mss-and-hyphae-form-spec.md`.

### C. Raising a flag

A datum **raises a flag** when its compiled hyphae value matches a value present
in the **hyphae-flag registry** (Section E). Two scopes raise flags:

- **Per-datum flag** — the datum's own hyphae value matches a registered value.
- **Family-root flag** — the hyphae value of a *family's root common datum*
  (the shared minimum-but-complete path prefix common to every member of the
  family) matches a registered value; every member of that family then inherits
  the flag. This is what "lenses/tools bind to a family's root common datum"
  means.

Flag-raising is a *recognition-time* step: after a document is compiled,
each datum (and each family root) computes its hyphae value and is looked up in
the registry; a hit produces a **flag event** (Section D) carrying the matched
value and the bound `tool_id` / `lens_id`.

### D. How tools / lenses subscribe

Tools and lenses do **not** subscribe to families or archetypes. They register a
**hyphae value** (or a family-root hyphae value) in the registry and name
themselves as the binding target. At recognition time:

- The **lens resolver** (`registry.py:51`) gains a *first, highest-priority*
  branch: if the datum carries a raised flag with a `lens_id`, resolve that lens
  directly; otherwise fall through to today's family/value-kind/overlay logic.
- The **tool eligibility** recognizer (`tool_eligibility.py:64`) gains a
  parallel path: tools bound to a raised flag's hyphae value are *always*
  eligible for that datum, in addition to (not instead of) the existing
  archetype/source-kind widening, which remains as the generic fallback.

This makes the binding **exact and content-derived**: a flagged datum offers
exactly the tool(s)/lens(es) registered for its hyphae value, anywhere it
appears.

---

## Data shapes / interfaces

> **Proposal.** Sketches, not final schemas. Field names are illustrative.

### Where things live

- **`core/datum_semantics/`** *(new, relocated)* — the engine currently at
  `adapters/sql/datum_semantics.py`, moved into core (resolving the inversion at
  `ops.py:24` / `node_ops.py:17`). It gains a
  `build_minimum_complete_path(document, target_address) -> Path` and a
  `compile_hyphae_value(path) -> str` alongside the existing
  `build_document_semantics`.
- **`core/hyphae_flags/`** *(new)* — a pure, store-agnostic registry of
  `hyphae_value → {tool_id?, lens_id?}` bindings, plus the flag-event shape and
  the lookup function. Pure so both the lens registry and the tool recognizer
  can consult it without importing an adapter.

### Registry record (sketch)

```python
@dataclass(frozen=True)
class HyphaeFlag:
    hyphae_value: str          # "sha256:…" — the canonical compiled value, the KEY
    scope: str                 # "datum" | "family_root"
    tool_id: str = ""          # optional: tool bound to this value
    lens_id: str = ""          # optional: lens bound to this value
    label: str = ""            # human-facing name of the flag
    description: str = ""
    # at least one of tool_id / lens_id must be set
```

A registry is an immutable mapping `hyphae_value -> tuple[HyphaeFlag, ...]`
(one value MAY carry both a tool and a lens binding, or several tools), with a
single lookup:

```python
def lookup_flags(registry, hyphae_value: str) -> tuple[HyphaeFlag, ...]: ...
```

### Flag event (sketch)

Emitted at recognition time when a datum/family-root's compiled value hits the
registry. Carried alongside the existing `DatumRecognitionRow`
(`service.py:245`) — e.g. a new `raised_flags: tuple[RaisedFlag, ...]` field, or
a side channel keyed by `datum_address`:

```python
@dataclass(frozen=True)
class RaisedFlag:
    datum_address: str         # where it was raised
    hyphae_value: str          # the value that matched
    scope: str                 # "datum" | "family_root"
    tool_ids: tuple[str, ...]  # bound tools (possibly empty)
    lens_id: str = ""          # bound lens (possibly empty)
```

### How the consumers consult it

- **`lens/registry.py`** — `resolve(...)` gains a `raised_flags` (or
  `flag_lens_id`) parameter checked *before* the `_family_lenses` branch at
  `registry.py:59`. A flagged datum's `lens_id` wins; unflagged datums behave
  exactly as today.
- **`portal_shell/tool_eligibility.py`** — `recognize_applicable_tools(...)`
  gains access to the raised flags for the selected datum and unions the
  flag-bound tools into `eligible` (`tool_eligibility.py:100`–`111`) before
  sorting. `PortalToolRegistryEntry` (`shell.py:477`) MAY gain an
  `applies_to_hyphae_value: tuple[str, ...]` field so a tool can declare its
  binding inline, mirroring `applies_to_archetype`.

---

## Migration path

Strictly incremental; each step ships and is reversible before the next. The
existing archetype / family-string binding is kept as a **fallback throughout**,
so nothing regresses if a datum is unflagged.

1. **Dedupe the engine into core.** Relocate `adapters/sql/datum_semantics.py`
   to `core/datum_semantics/`, re-pointing `ops.py:24` and `node_ops.py:17`
   imports. (Tracked by a separate unit; prerequisite for the rest.) Pure
   refactor, no behavior change.
2. **Add `build_minimum_complete_path` + `compile_hyphae_value`** next to the
   existing inclusive engine — additive, exercised by tests, consumed by nothing
   yet. Keep the inclusive `derive_hyphae_chain` /
   `build_document_semantics.hyphae_chain` in place.
3. **Add `core/hyphae_flags/`** — the registry, record, event, and `lookup_flags`
   — seeded empty. No consumer reads it yet.
4. **Raise flags at recognition time** — compute each datum/family-root's hyphae
   value during `_recognize_document` (`service.py:573`) and attach
   `RaisedFlag`s. With an empty registry this is a no-op on output.
5. **Re-point lens binding** — add the flag branch to `resolve`
   (`registry.py:51`); unflagged datums unchanged.
6. **Re-point tool binding** — union flag-bound tools in
   `recognize_applicable_tools` (`tool_eligibility.py:64`); archetype widening
   stays as fallback.
7. **(Optional, later)** retire the inclusive rudi-range fill once all live
   bindings use minimum-but-complete values.

---

## Open design questions

1. **Per-datum or per-family path root?** Is the minimum-but-complete path rooted
   at the individual datum, or at the family's root common datum? Both are in the
   vision ("bind to a datum's flagged hyphae value OR to a family's root common
   datum"). Likely both are computed; which one a given flag keys on is a
   registry property (`scope` field). Need a precise definition of "family root
   common datum" — the shared path *prefix*? the deepest common ancestor in the
   dependency DAG?
2. **MSS form along the path — bitstream or JSON?** The fold needs a canonical
   serialization. Today the engine folds JSON (`_remap_semantic_raw` +
   `dumps_json`). The vision's "MSS form" may be a bitstream. Deferred to
   `61-mss-and-hyphae-form-spec.md`; the hyphae value's *stability guarantees*
   (address-independence, anchor-awareness) must hold under whichever form is
   chosen.
3. **Collision & versioning.** Hyphae values are SHA-256 tokens; collisions are
   negligible, but the *policy string* (`HYPHAE_CHAIN_POLICY`,
   `datum_semantics.py:15`) must version the path algorithm so a future change to
   "minimum-but-complete" produces distinct values and old registry entries are
   detectably stale.
4. **Where is the registry sourced?** In-code constant, a MOS datum document, or
   per-tenant config? A datum-document-backed registry would be self-hosting (the
   registry is itself canonical data) but introduces a bootstrap dependency.
5. **Flag precedence.** When a datum raises both a per-datum flag and inherits a
   family-root flag with conflicting `lens_id`s, which wins? (Proposed: per-datum
   over family-root; document explicitly.)
6. **Authoring surface.** How do tool/lens authors discover and register a hyphae
   value? See `80-tool-authoring-guide.md` and `81-lens-authoring-guide.md` for
   the author-facing workflow.

---

## Acceptance

"Done" for the *spec* (this page) means: the minimum-but-complete path algorithm,
the compile-to-hyphae-value step, the registry/flag/event shapes, and the
consult points in `lens/registry.py` and `tool_eligibility.py` are all defined
and cited against real code.

"Done" for the *implementation this spec drives* (future units) means:

- The engine lives in `core/datum_semantics/` (inversion at `ops.py:24` /
  `node_ops.py:17` resolved).
- `build_minimum_complete_path` returns the minimal definitional closure of a
  target datum — no rudi-range fill, focus-excluded — and `compile_hyphae_value`
  folds it into a stable, address-independent, anchor-aware token.
- `core/hyphae_flags/` holds a pure `hyphae_value → {tool_id?, lens_id?}`
  registry with a single `lookup_flags`.
- A flagged datum (per-datum *or* via its family root) resolves its bound lens
  and offers its bound tools, **anywhere it appears**, while unflagged datums
  behave exactly as today (archetype/family-string fallback intact).
- The same datum, re-nested or re-addressed by an insert/move
  (`datum_semantics.py:474` / `:587`), keeps the same hyphae value and therefore
  the same flag.

---

*Forward references:* [`61-mss-and-hyphae-form-spec.md`](61-mss-and-hyphae-form-spec.md) ·
[`80-tool-authoring-guide.md`](80-tool-authoring-guide.md) ·
[`81-lens-authoring-guide.md`](81-lens-authoring-guide.md) ·
[`05-engineering-standards.md`](05-engineering-standards.md)
