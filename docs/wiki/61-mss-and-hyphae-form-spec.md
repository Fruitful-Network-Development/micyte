# 61 — MSS Form & Hyphae Form Spec

> Status: design-spec — **CORRECTED 2026-06-01**

[← Overview](00-overview-and-glossary.md)

> **Correction / upgrade.** The authoritative original MSS binary-sequence spec
> has been recovered from git history and restored at
> `docs/contracts/mss_binary_sequence/` (`MSS_convention.py`, the
> `anthology-notes.txt` worked example + anthology base, and a reference
> implementation). Treat **that** directory as the canonical wire spec; this page
> is the wiki-level summary. Two corrections to earlier framing here: (1) **MSS
> is a hash over the binary MSS *sequence*** of the document — a document's
> identity is its MSS, never a hyphae value; (2) **hyphae = the same codec over a
> datum's focus closure, and it retains the full ordinal rudi scaffold** (include
> `0-0-1`..`0-0-K`) — focus-exclusion drops off-focus *sibling* datums, it does
> **not** drop the preceding rudis. Today's `mos.mss_sha256_v1` (JSON-of-rows +
> SHA-256) is a canonical-ish **stand-in**, not the binary MSS sequence; building
> the real codec against the recovered spec is tracked separately.

This page specs the **MSS form**: the standardized single-sequence binary
encoding of one or more top-level datums, the way every datum document is
saved to the MOS database. It defines how **hyphae** is the *same* algorithm
plus a focus-exclusion preprocessing pass, and how the resulting sequence
relates to today's `compute_mss_hash` JSON identity and the SAMRAS bitstream
codec.

Related forward-references:
[`60-canonical-datum-and-hyphae-flags.md`](60-canonical-datum-and-hyphae-flags.md) ·
[`70-yaml-materialization-pipeline.md`](70-yaml-materialization-pipeline.md) ·
[`90-network-contract-architecture.md`](90-network-contract-architecture.md)

---

## Problem

The user's vision states a single, sharp definition:

> **MSS form** is the MSS standardization of encoding binary values into a
> single sequence, EXCEPT it can include more than one top-level datum. The
> standardization uses the address size, bitmap, start and stop slices, etc.,
> and it is the SAME algorithmic encode/decode process as **hyphae**, except
> for a preprocessing step that may have a hyphae value EXCLUDE datums that are
> not part of the focus. This is also how datum documents are saved to the MOS
> database: in MSS form, one per datum doc, with a title
> `<document_type>.<msn_id>.<sandbox>.<name>.<_blockchain_hash_version>`.

Three properties are asserted there that the code does **not** currently
embody as one coherent thing:

1. **MSS is a single *binary sequence*** built from an *address size*, a
   *bitmap*, and *start/stop slice* tables — i.e. a bitstream codec.
2. **Hyphae is MSS minus a focus-exclusion preprocessing pass** — one
   algorithm, two entry points.
3. **MSS is the on-disk save form**, one MSS sequence per datum document,
   keyed by a title whose last segment is a hash *of that MSS sequence*.

Today the repo splits these across two unrelated mechanisms:

- The thing literally **named "MSS"** (`compute_mss_hash`) is **not a binary
  sequence at all** — it is a SHA-256 over a canonical-JSON payload of sorted
  `{datum_address, raw}` rows. It produces an *identity hash*, never a
  decodable sequence, and it does not use an address size, bitmap, or
  start/stop slices.
- The thing that **is** the address-size / stop-slice / value-token bitstream
  codec is **SAMRAS** (`core/structures/samras/`), which is presented as a
  separate "tree-structure magnitude" codec, not as "MSS".
- **Hyphae** today is a *graph-closure derivation* over rows
  (`derive_hyphae_chain`, `build_document_semantics`), not "MSS with a
  preprocessing exclusion pass." It shares no encoder with SAMRAS.

So the terminology and representation are mismatched against the vision. This
page resolves that: it names the *intended* single binary form **MSS form**,
shows what already exists to build it from (SAMRAS), and specs how hyphae
becomes a thin preprocessing wrapper over the same encode/decode path while the
existing SHA-256 identity is preserved as the document version hash.

---

## Current reality (cited)

### 1. The thing named "MSS" is a JSON identity hash, not a binary sequence

`MyCiteV2/packages/core/mss/datum_identity.py:101` — `compute_mss_hash`
builds a `payload` dict of `policy: "mos.mss_sha256_v1"`, `source_kind`,
`document_metadata`, and a list of `{"datum_address", "raw"}` rows **sorted by
parsed address** (`datum_identity.py:116`), then returns
`{policy, version_hash, canonical_payload}` where `version_hash` is
`sha256:<hex>` over canonical JSON (`datum_identity.py:54`, `:50` —
`json.dumps(..., separators=(",", ":"), sort_keys=True)`).

The policy token is `MSS_VERSION_HASH_POLICY = "mos.mss_sha256_v1"`
(`datum_identity.py:13`). There is **no** address-size header, bitmap, or
start/stop slice — it is a content hash of a JSON document, not a
self-describing binary sequence.

### 2. Hyphae today is a graph-closure derivation, with no focus exclusion

`MyCiteV2/packages/core/mss/datum_identity.py:126` — `derive_hyphae_chain`
walks the transitive dependency closure of a `datum_address`
(`datum_identity.py:153` `_walk`), collects every reachable rudi address
(`layer=0, value_group=0`; `datum_identity.py:163`), and returns the rudi
prefix up to the highest reachable iteration `K` — every position `1..K` that
is actually present in the doc, in order (`datum_identity.py:172`–`:177`). It
does **not** take a focus set and does **not** exclude any datums on the basis
of focus (docstring, `datum_identity.py:130`).

The production engine is the richer
`MyCiteV2/packages/adapters/sql/datum_semantics.py:209` —
`build_document_semantics`, which per row computes a `semantic_hash`
(`datum_semantics.py:226` `semantic_hash_for`, policy
`HYPHAE_CHAIN_POLICY = "mos.hyphae_chain_v1"`, `:15`), a `hyphae_hash`, and a
`hyphae_chain` ordered as `rudi_prefix + closure` (`datum_semantics.py:302`).
`build_document_version_identity` (`datum_semantics.py:136`) reproduces the
same `mos.mss_sha256_v1` `version_hash` as `compute_mss_hash`. These hyphae
results are persisted per row in the `datum_row_semantics` table as
`hyphae_chain_json` (`MyCiteV2/packages/adapters/sql/_sqlite.py:76`; written at
`MyCiteV2/packages/adapters/sql/datum_store.py:423`, read back at
`datum_store.py:822`). None of this path consumes a focus argument.

> Note the layering inversion: this engine lives in the SQL adapter, not in
> `core/`. A sibling unit relocates it; this spec assumes the *algorithm* is
> what matters and is representation-agnostic about its eventual home.

### 3. SAMRAS is the actual address-size / bitmap / start-stop-slice bitstream

`MyCiteV2/packages/core/structures/samras/codec.py` is the real
single-sequence binary codec the vision describes:

- An **address-size header** encoded as a unary width field
  (`codec.py:35` `encode_unary_width`, decoded at `codec.py:42`
  `decode_unary_width`); the layout assembled at `codec.py:94`–`:101` is
  `[unary address_width][unary stop_count_width][stop_count][stop_address
  table][concatenated value tokens]`.
- **Start/stop slices**: `compute_stop_addresses` (`codec.py:55`) yields the
  cumulative offsets used to slice the value stream back into tokens; the
  decoder reconstructs `starts = [0, *stops]`, `ends = [*stops, len]`
  (`codec.py:163`).
- **Value tokens**: minimal-binary child-count magnitudes
  (`codec.py:19` `minimal_binary`); `decode_canonical_bitstream`
  (`codec.py:141`) round-trips a `[01]+` string back to a `SamrasStructure`
  and *rejects non-canonical* encodings (`codec.py:179`).
- The decoded shape is `SamrasStructure`
  (`MyCiteV2/packages/core/structures/samras/structure.py:48`), carrying
  `bitstream`, `address_width_bits`, `stop_addresses`, `value_tokens`,
  `values`, and the derived `addresses`.
- Validation / address derivation:
  `MyCiteV2/packages/core/structures/samras/validation.py:33`
  (`derive_addresses_from_child_counts`, a breadth-first child-count walk).

What SAMRAS does **not** do today: it encodes exactly **one** root tree
(`root_ref`, `structure.py:50`) of integer magnitudes; it carries no `raw`
row content, no notion of multiple independent top-level datums, and no
focus-exclusion pass. The vision's "bitmap" has no direct counterpart yet —
the closest analog is the stop-address slice table, not a presence bitmap.

### 4. The save title is `lv./stl./cptr.`, hash over the "MSS form"

`MyCiteV2/packages/core/document_naming/__init__.py:19` —
`ALLOWED_PREFIXES = ("lv", "stl", "cptr")`. Grammar (`:21`–`:22`):

- `lv.<msn_id>.<sandbox>.<name>.<hash>` (sandboxed live document)
- `stl.<msn_id>.<name>.<hash>` and `cptr.<msn_id>.<name>.<hash>` (no sandbox)

`<hash>` is a 64-char lowercase hex SHA-256 and is documented as being **"over
the document MSS form"** (`document_naming/__init__.py:74`–`:78`,
`format_canonical_document_id`). In practice that hash is the
`version_hash` from `compute_mss_hash` / `build_document_version_identity`
(stripped of its `sha256:` prefix at `__init__.py:59`). The contract lives at
`docs/contracts/datum_document_naming_taxonomy.md`.

**The mismatch in one line:** the title already claims its hash is "over the
MSS form," but the *only* MSS form that exists is JSON-rows+SHA-256, while the
vision's "MSS form" is a binary sequence (which today only SAMRAS produces, and
only for single integer trees).

---

## Proposed model

> Everything in this section is a **proposal**, not current behavior.

### MSS form = one self-describing binary sequence over ≥1 top-level datum

Define **MSS form** as a single bitstream that encodes an ordered list of
top-level datums (`roots`), reusing the SAMRAS field discipline (unary width
headers + slice tables + value tokens) and adding the two things SAMRAS lacks:
**multiple top-level roots** and **row content** (`raw`) per datum.

Conceptually:

```
MSS sequence
  = [ MSS magic/version ]
    [ address_size header   ]   # unary width, as SAMRAS codec.py:35
    [ root_count            ]   # NEW: number of top-level datums (≥1)
    [ presence bitmap       ]   # the vision's "bitmap": which addresses are present
    [ start/stop slice table]   # cumulative offsets, as SAMRAS codec.py:55
    [ value-token stream     ]   # per-datum payload tokens (structure + raw)
```

The encode/decode algorithm is **the SAMRAS algorithm generalized**: the same
unary-width address-size field, the same stop-address slicing, the same
canonical-only decode rule (reject non-canonical, `codec.py:179`). The only
new structural elements are `root_count` and the **presence bitmap** — a fixed
bit per candidate address declaring whether that datum participates in this
sequence. The bitmap is the hinge that makes the *next* point work.

There are two clean ways to realize the codec; this spec recommends **(B)** and
lists both as an open question:

- **(A) Reuse the SAMRAS codec directly** — extend
  `core/structures/samras/codec.py` with a `root_count`/bitmap-aware
  multi-root variant. Lowest new surface area; risk is overloading a codec
  whose contract is currently "one integer tree."
- **(B) A distinct MSS codec that *composes* SAMRAS** — a new
  `core/mss/` sequence codec that emits the address-size header + bitmap +
  multi-root framing, and delegates each root's structural magnitudes to the
  existing SAMRAS encode/decode (`encode_canonical_structure_from_values`,
  `codec.py:132`). Keeps SAMRAS's "single tree" contract intact and keeps the
  binary discipline DRY.

### Hyphae = MSS form + a focus-exclusion preprocessing pass

Under the vision, **hyphae and MSS are one algorithm**. The difference is a
*preprocessing* step that runs *before* the shared encoder:

```
hyphae(doc, focus) =
    MSS_encode( exclude_non_focus(doc, focus) )
MSS(doc) =
    MSS_encode( doc )                 # i.e. focus = "all top-level datums"
```

`exclude_non_focus` is the presence-bitmap producer: given a focus set (e.g. a
target datum and the transitive closure that today's `derive_hyphae_chain`
already computes, `datum_identity.py:153`), it clears the bitmap bits for every
address **not** in focus, so excluded datums contribute neither slices nor
value tokens. With an all-ones bitmap (no exclusion), `hyphae` *is* `MSS`.

This reframes the existing closure walk
(`datum_semantics.py:269` `_walk_closure`) as the **focus selector** feeding
the bitmap — the graph derivation stays, but its output becomes "which bits
are set" rather than "a JSON chain." The rudi-prefix densification
(`datum_semantics.py:295`) becomes a bitmap-construction rule.

### How MSS carries more than one top-level datum

`root_count` ≥ 1 plus the presence bitmap let a single MSS sequence frame N
independent top-level datums. Each root is laid out in canonical address order
(layer/value_group/iteration, matching `canonicalize_iteration_addresses`,
`MyCiteV2/packages/core/mss/canonicalization.py:50`), its structural magnitudes
encoded SAMRAS-style, and its `raw` row content carried in the value-token
stream. This is the property that distinguishes MSS from plain SAMRAS, which is
single-root by construction (`SamrasStructure.root_ref`, `structure.py:50`).

### The save title and how the hash is computed

Keep the existing title grammar
(`document_naming/__init__.py:65` `format_canonical_document_id`):

```
<document_type>.<msn_id>.<sandbox>.<name>.<hash>
```

The vision's `<document_type>` **is** today's prefix
(`lv` / `stl` / `cptr`, `__init__.py:19`); `<sandbox>` is present only for
`lv` (`__init__.py:94`). The `<hash>` becomes the SHA-256 **of the MSS binary
sequence bytes** — a true content hash of the saved form, satisfying the
docstring's existing claim (`__init__.py:74`) that the hash is "over the
document MSS form." One MSS sequence is stored per datum document, exactly as
the vision states.

Because the MSS sequence is canonical (single legal encoding for a given doc +
focus, enforced the way SAMRAS rejects non-canonical streams at
`codec.py:179`), the hash is deterministic without a separate JSON
canonicalization step.

---

## Data shapes / interfaces

> Proposed; sketch only.

### MSS sequence byte/bit layout (proposed)

| Field | Encoding | Source of pattern |
|---|---|---|
| magic / format version | fixed bits | new |
| `address_size` | unary width (`0…01`) | `codec.py:35` `encode_unary_width` |
| `root_count` | `address_size`-wide int | new (SAMRAS is single-root) |
| presence **bitmap** | one bit per candidate address, canonical order | new ("the bitmap") |
| `stop_count` + width | unary width + fixed int | `codec.py:86`–`:97` |
| start/stop slice table | `stop_count` × `address_size`-wide ints | `codec.py:55` `compute_stop_addresses` |
| value-token stream | concatenated minimal-binary tokens, sliced by stops | `codec.py:99`, `:160`–`:168` |

Decode mirrors `decode_canonical_bitstream` (`codec.py:141`): read widths,
read bitmap, read slice table, slice the value stream, **reject** any stream
that does not re-encode to itself (`codec.py:179`).

### Proposed interface surface

```python
# core/mss/ (proposed)

def encode_mss_form(document, *, focus=None) -> bytes:
    """Encode ≥1 top-level datum into one canonical MSS sequence.
    focus=None  -> full MSS form (all-ones bitmap).
    focus=<set> -> hyphae form (non-focus addresses cleared in the bitmap)."""

def decode_mss_form(sequence: bytes) -> "MssDocument":
    """Inverse of encode_mss_form; canonical-only (rejects non-canonical)."""

def mss_version_hash(sequence: bytes) -> str:
    """sha256 over the MSS sequence bytes -> the <hash> title segment."""
```

`focus` is the only difference between MSS and hyphae — it drives
`exclude_non_focus`, which sets the presence bitmap.

### Title grammar (unchanged; restated)

```
lv.<msn_id>.<sandbox>.<name>.<hash>     # ALLOWED_PREFIXES "lv"   (document_naming/__init__.py:19)
stl.<msn_id>.<name>.<hash>              # "stl"
cptr.<msn_id>.<name>.<hash>             # "cptr"
```

`<hash>` = 64 hex chars (`__init__.py:31` `_HEX_RE`), SHA-256 of the MSS
sequence; `<document_type>` = prefix; one MSS sequence per document.

---

## Migration path

1. **Keep `mos.mss_sha256_v1` as the version hash; do not break the title.**
   The lowest-risk path is to introduce the MSS *sequence* alongside the
   existing identity hash. `compute_mss_hash`
   (`datum_identity.py:101`) and `build_document_version_identity`
   (`datum_semantics.py:136`) continue to produce the `<hash>` segment, so all
   existing `lv./stl./cptr.` ids stay valid and the
   `documents.version_hash` column (`_sqlite.py:60`) is untouched. The MSS
   binary sequence is added as a new stored artifact (or recomputed on read),
   not a replacement key — until step 4.

2. **`<document_type>` ≡ prefix.** No rename needed:
   `lv`/`stl`/`cptr` already *are* the document types the vision calls
   `<document_type>` (`ALLOWED_PREFIXES`, `__init__.py:19`). Optionally
   document the mapping in
   `docs/contracts/datum_document_naming_taxonomy.md` so future readers do not
   expect a literal `mss.` prefix.

3. **Refactor hyphae into MSS + focus, behavior-preserving first.** Reframe
   `derive_hyphae_chain` (`datum_identity.py:126`) and the closure walk in
   `build_document_semantics` (`datum_semantics.py:269`) as the *focus
   selector* that produces the presence bitmap, while still emitting today's
   `hyphae_chain_json` (`_sqlite.py:76`) so `datum_store.py` readers
   (`datum_store.py:822`) keep working. Only after the bitmap path is proven
   does the JSON chain become a *projection* of the bitmap rather than the
   source of truth.

4. **Unify the hash last, behind a policy bump.** If/when the MSS *sequence*
   hash replaces the JSON identity hash, do it under a new policy token
   (e.g. `mos.mss_seq_v1`) so old documents remain verifiable under
   `mos.mss_sha256_v1` and migration can dual-write. Do **not** silently change
   what `<hash>` means for existing ids.

5. **Reuse vs. fork the codec.** Decide between proposal (A) extending
   `samras/codec.py` and (B) a composing `core/mss/` codec (recommended).
   Either way, SAMRAS's canonical-only decode guarantee (`codec.py:179`) and
   address derivation (`validation.py:33`) are the reuse anchors; do not
   reimplement bitstream framing.

---

## Open design questions

1. **What is the "bitmap," precisely?** This spec proposes a per-address
   *presence* bitmap (the focus selector's output). Is that the vision's
   intent, or does "bitmap" mean a per-bit value mask inside value tokens?
   SAMRAS has no bitmap today — only stop-address slices (`codec.py:55`).

2. **Codec reuse vs. distinct MSS codec** — (A) extend `samras/codec.py` to be
   multi-root + bitmap aware, or (B) new `core/mss/` codec that composes SAMRAS
   per root. (B) preserves SAMRAS's single-tree contract; (A) is less code.

3. **How is `raw` row content encoded into a *binary* value stream?** SAMRAS
   value tokens are integer magnitudes (`codec.py:19`); datum `raw` is
   arbitrary JSON-ish content (`datum_identity.py:59` `_row_tokens`). Does MSS
   binary-encode `raw`, or carry a hash/pointer to it while the bitstream
   encodes only structure?

4. **Does the title `<hash>` migrate to the sequence hash?** If yes, every
   existing `lv./stl./cptr.` id's hash changes — a global rename. If no, MSS
   sequence and identity hash diverge permanently. (Step 4 above proposes a
   policy-gated dual-write; confirm which.)

5. **Focus identity** — should `hyphae(doc, focus)` and `MSS(doc)` over the
   same focused subset produce *byte-identical* sequences (and therefore the
   same hash)? The vision implies yes ("same algorithm"); confirm so the
   bitmap, not a separate flag, is the sole differentiator.

6. **Where does the engine live?** `build_document_semantics` is in the SQL
   adapter (`datum_semantics.py`); MSS/hyphae encoding is pure-core work.
   Coordinate with the relocation unit so the codec lands in `core/`.

---

## Acceptance

This page is **design-spec** and ships no code. It is accepted when:

- [x] Problem states the vision's MSS definition and names the precise
  mismatch: "MSS" today = JSON-rows + SHA-256 identity (`compute_mss_hash`),
  while the vision's MSS = a single binary sequence (today only SAMRAS).
- [x] Current reality cites real `path:line` for `compute_mss_hash`
  (`datum_identity.py:101`), `derive_hyphae_chain` (`:126`),
  `build_document_semantics` (`datum_semantics.py:209`),
  `build_document_version_identity` (`:136`), the SAMRAS codec fields
  (`codec.py:35`, `:55`, `:141`, `:179`), and the title grammar
  (`document_naming/__init__.py:19`, `:65`).
- [x] Proposed model defines the single MSS encode/decode algorithm
  (address size + bitmap + start/stop slices), states hyphae = MSS + a
  focus-exclusion preprocessing pass, explains multi-top-level support via
  `root_count` + bitmap, and decides the SAMRAS-reuse relationship.
- [x] Data shapes give a byte/sequence layout sketch and restate the title
  grammar `<document_type>.<msn_id>.<sandbox>.<name>.<hash>`.
- [x] Migration path reconciles `lv./stl./cptr.` with `<document_type>` and
  states the dual-write/keep-then-unify hash strategy.
- [x] Open questions and forward-refs to siblings (`60-…`, `70-…`, `90-…`)
  are present.
