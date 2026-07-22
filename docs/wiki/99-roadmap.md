# 99 — Development Roadmap

> Status: as-built
>
> [← Overview](00-overview-and-glossary.md)

This is the sequenced development roadmap for the MiCyte Portal. It ties the
rest of the wiki together so you can **decide what to build next** with the
dependencies made explicit. Tools and lenses are the near-term focus; the
network / crypto / contract layer is deferred; a desktop-app form factor is the
long horizon.

Every `path:line` citation below points at the **current** state of the tree
(verified on disk). Sibling wiki links (`6x`, `7x`, `8x`, `9x` pages) are the
design specs each track depends on; some are forward references authored by
other units in this batch.

---

## How to read this roadmap

The work is organized into five tracks. Tracks are **mostly** sequential, but
not strictly — Track 1 (tools-first) is the product goal, and the only reason
Track 0 comes first is that a handful of foundation deltas *unblock* clean tool
authoring. Read it this way:

- **Track 0 — Foundations / hygiene.** Close the structural debt that makes the
  "simplified core" leak. Cheap, high-leverage, and partly landing in this
  batch. Everything else sits on top of it.
- **Track 1 — Tools-first (near-term).** The actual deliverable: demo sandboxes
  and tools/lenses bound to hyphae values. This is where development effort
  should concentrate.
- **Track 2 — MSS / YAML model coherence.** Reconcile the identity model and
  unify read + write on one WORKBOOK-YAML representation. Track 1 *can* proceed
  on the current split, but converges faster once this lands.
- **Track 3 — Network layer (deferred).** Crypto → contracts → contact card →
  msn_registry → reference exchange. Stubbed today; do not build until Track 1
  is delivering value.
- **Track 4 — Desktop app + local DB (long horizon).** Persistence is already
  form-factor-agnostic, so this is a packaging exercise, not a rewrite.

Each track names the **deltas** it consumes (numbered `D1`–`D6`, defined in the
[delta map](50-delta-map.md)) and links the spec page that describes the target
design.

Delta shorthand used throughout:

| ID | Delta | Severity (now) | Landing in this batch? |
|----|-------|----------------|------------------------|
| D1 | core→adapter inversion + duplicate engine + missing boundary test | HIGH | **partial** (see Track 0) |
| D2 | materialization read/write split (two codecs) | HIGH | spec only |
| D3 | no hyphae-flag mechanism; MSS-vs-SAMRAS terminology drift | MED | spec only |
| D4 | no Utilities-manage / Control-Panel-toggle lens UX | MED | spec only |
| D5 | network / crypto / contract future stubbed | LOW now / HIGH later | spec only |
| D6 | desktop app + local DB | long horizon | spec only |

---

## Track 0 — Foundations / hygiene

**Goal:** make the "simplified core" claim true on disk, so tool authors can
import the datum engine from `core/` without reaching through an adapter.

**Deltas:** D1.

### What is wrong today

The datum-operation layer lives in `core/`, but its core algebra **imports the
SQL adapter**, inverting the intended dependency direction:

- [`micyte/core/datum_ops/ops.py:24`](../../micyte/core/datum_ops/ops.py) —
  `from micyte.adapters.sql.datum_semantics import (...)`.
- [`micyte/core/datum_ops/node_ops.py:17`](../../micyte/core/datum_ops/node_ops.py) —
  `from micyte.adapters.sql.datum_semantics import parse_datum_address`.

The recognition/identity logic is **duplicated**: the MSS-hash and
address-recognition routines live both in
[`micyte/core/mss/datum_identity.py`](../../micyte/core/mss/datum_identity.py)
and in the adapter
[`micyte/adapters/sql/datum_semantics.py`](../../micyte/adapters/sql/datum_semantics.py),
so the canonical engine is ambiguous.

There is **no boundary test** asserting that `core/datum_ops` may not import
`adapters/*`. The architecture suite already has analogous guards
(`test_core_datum_refs_boundaries.py`, `test_core_datum_rules_boundaries.py` in
[`fnd_app/tests/architecture/`](../../fnd_app/tests/architecture)) — but
**not** `test_core_datum_ops_boundaries.py`, so the inversion is uncaught.

### What to do

0a. **Relocate the engine into `core/datum_semantics/`** so the address parser,
    MSS-hash, and recognition routines have a single home in `core/`, and have
    `datum_ops` and the SQL adapter both depend *inward* on it. (Removes the
    duplication between `datum_identity.py` and the adapter.)

0b. **Flip the imports** in `ops.py` and `node_ops.py` to the new `core/`
    engine; the SQL adapter keeps only SQL-shaped concerns.

0c. **Add `test_core_datum_ops_boundaries.py`** to
    [`fnd_app/tests/architecture/`](../../fnd_app/tests/architecture) so the
    inversion can never silently return.

0d. **Document the future stubs** (Track 3 dirs) as deliberately empty so they
    are not mistaken for dead code: see
    [`micyte/core/crypto`](../../micyte/core/crypto),
    [`micyte/domains/contracts`](../../micyte/domains/contracts),
    [`micyte/domains/reference_exchange`](../../micyte/domains/reference_exchange),
    [`micyte/state_machine/mediation_surface`](../../micyte/state_machine/mediation_surface),
    [`fnd_app/packages/sandboxes`](../../fnd_app/packages/sandboxes), and
    [`micyte/tools/_shared`](../../micyte/tools/_shared)
    (each is a `README.md` + `__init__.py` placeholder today).

> **Landing in THIS batch:** 0a + 0b + 0c. A sibling unit relocates the engine
> into `core/datum_semantics/`, flips the two imports, and adds the boundary
> test. 0d (stub documentation) is captured by the spec pages, not code.

**Spec pages:** [`05-engineering-standards.md`](05-engineering-standards.md) ·
[`50-delta-map.md`](50-delta-map.md) ·
[`60-canonical-datum-and-hyphae-flags.md`](60-canonical-datum-and-hyphae-flags.md).

---

## Track 1 — Tools-first (near-term) ★ primary focus

**Goal:** stand up **demo sandboxes** and author **tools + lenses** that bind to
hyphae values, so the portal demonstrably *does something* with recognized data.
This is the track that justifies continued development.

**Deltas:** D3 (the hyphae-flag mechanism it depends on), D2 (read-path YAML),
D4 (the lens-management UX it depends on).

### What is needed before authoring is pleasant

1. **A hyphae-flag mechanism** (D3). Tools bind to *flags* on recognized hyphae
   values, but there is no first-class flag-declaration path yet — recognition
   and identity live in
   [`micyte/core/mss/datum_identity.py`](../../micyte/core/mss/datum_identity.py)
   and the adapter
   [`micyte/adapters/sql/datum_semantics.py`](../../micyte/adapters/sql/datum_semantics.py).
   The "minimum-but-complete" path (smallest set of flags that still round-trips
   a document) is specified in
   [`60-canonical-datum-and-hyphae-flags.md`](60-canonical-datum-and-hyphae-flags.md).

2. **Read-path YAML unification** (D2, partial). The lens/read path currently
   projects SQL → display JSON in
   [`micyte/tools/workbench_ui/service.py`](../../micyte/tools/workbench_ui/service.py)
   (imports `datum_semantics`, builds JSON rows for the grid), while the write
   path round-trips through the WORKBOOK-YAML codec
   [`micyte/core/datum_io/codec.py`](../../micyte/core/datum_io/codec.py).
   Tools become easier to author when they read and write the *same* YAML
   shape. (Full reconciliation is Track 2; Track 1 needs only the read path to
   speak the codec's vocabulary.)

3. **Utilities-manage / Control-Panel-toggle lens UX** (D4). The lens registry
   resolves presentation lenses
   ([`micyte/state_machine/lens/registry.py`](../../micyte/state_machine/lens/registry.py)
   — `DatumLensRegistry` maps families/value-kinds to lenses) but there is **no
   user surface** to manage or toggle lenses; the file contains no
   "Utilities" / "Control Panel" affordance. Authors and operators need a way to
   switch lenses without code changes.

### What to do

- Build one or two **demo sandboxes** under
  [`fnd_app/packages/sandboxes`](../../fnd_app/packages/sandboxes) following
  the cookbook, each exercising a real recognized family.
- Author **tools** bound to hyphae flags per the tool guide.
- Author **lenses** and register them, then expose the Utilities/Control-Panel
  toggle per the lens guide.

**Spec pages:** [`80-tool-authoring-guide.md`](80-tool-authoring-guide.md) ·
[`81-lens-authoring-guide.md`](81-lens-authoring-guide.md) ·
[`82-demo-sandbox-cookbook.md`](82-demo-sandbox-cookbook.md) ·
[`60-canonical-datum-and-hyphae-flags.md`](60-canonical-datum-and-hyphae-flags.md) ·
[`70-yaml-materialization-pipeline.md`](70-yaml-materialization-pipeline.md).

---

## Track 2 — MSS / YAML model coherence

**Goal:** one identity model, one materialization format. Reconcile the **MSS
form** with hyphae-focus preprocessing, and **unify the read and write paths**
on WORKBOOK-YAML.

**Deltas:** D3 (terminology), D2 (read/write unification).

### What is incoherent today

- **MSS vs SAMRAS terminology drift** (D3). MSS identity lives in
  [`micyte/core/mss/datum_identity.py`](../../micyte/core/mss/datum_identity.py)
  (`MSS_VERSION_HASH_POLICY = "mos.mss_sha256_v1"`), recognition/parsing lives in
  [`micyte/adapters/sql/datum_semantics.py`](../../micyte/adapters/sql/datum_semantics.py),
  and the SAMRAS structures live under
  [`micyte/core/structures/samras`](../../micyte/core/structures/samras).
  The same concepts wear different names across these three homes. The spec
  reconciles the vocabulary and defines how hyphae-focus preprocessing relates
  to the MSS form.

- **Two codecs, two shapes** (D2). The write path serializes through
  [`micyte/core/datum_io/codec.py`](../../micyte/core/datum_io/codec.py)
  (consumed by
  [`micyte/core/datum_ops/workbook.py`](../../micyte/core/datum_ops/workbook.py)
  and the mutation runtime
  [`fnd_app/instances/_shared/runtime/portal_datum_workbench_mutation_runtime.py`](../../fnd_app/instances/_shared/runtime/portal_datum_workbench_mutation_runtime.py)),
  while the read path hand-projects SQL → JSON in
  [`micyte/tools/workbench_ui/service.py`](../../micyte/tools/workbench_ui/service.py).
  Two representations means two places to keep correct.

### What to do

- Settle the MSS / hyphae-form vocabulary and the focus-preprocessing pipeline.
- Make the read path consume the **same** WORKBOOK-YAML projection the write
  path produces, so a document looks identical going out and coming back in
  (the codec already guarantees `from_yaml(to_yaml(doc))` preserves the MSS
  hash — extend that guarantee to the display projection).

**Spec pages:** [`61-mss-and-hyphae-form-spec.md`](61-mss-and-hyphae-form-spec.md) ·
[`70-yaml-materialization-pipeline.md`](70-yaml-materialization-pipeline.md) ·
[`60-canonical-datum-and-hyphae-flags.md`](60-canonical-datum-and-hyphae-flags.md).

---

## Track 3 — Network layer (deferred)

**Goal:** the eventual multi-party network — but **not now**. Everything here is
deliberately stubbed. Build it only once Track 1 is delivering value and Track 2
has stabilized the model.

**Deltas:** D5.

### Stubbed today (README + `__init__.py` only)

- [`micyte/core/crypto`](../../micyte/core/crypto)
- [`micyte/domains/contracts`](../../micyte/domains/contracts)
- [`micyte/domains/reference_exchange`](../../micyte/domains/reference_exchange)
- [`micyte/state_machine/mediation_surface`](../../micyte/state_machine/mediation_surface)
- [`fnd_app/packages/sandboxes`](../../fnd_app/packages/sandboxes) (also used by Track 1)

> **Cleanup audit (2026-07-21).** The directories above are **intentional
> deferred scaffolds (empty; the deferred network/crypto/handshake layer)** —
> each is a 1-LOC `__init__.py` (`"""Inert package scaffold."""`) plus a short
> README stub, carrying **zero functional references** (nothing `import`s them,
> and no config or test depends on them — only the descriptive citations in this
> wiki). They are safe to carry as-is or remove later. Audited scaffolds, at
> their **actual on-disk paths**: `micyte/core/crypto`,
> `micyte/domains/contracts`, `micyte/domains/reference_exchange`,
> `micyte/state_machine/mediation_surface`,
> `fnd_app/packages/sandboxes/orchestration`,
> `fnd_app/packages/sandboxes/system` (plus the similar `micyte/tools/_shared`).
> Note the two `domains` scaffolds now live under `micyte/domains/`, **not**
> `fnd_app/packages/modules/domains/` as the links above still read.
>
> **Vestigial artifact.** The in-repo `agentic/evidence/reports/*.md` (4 files,
> dated 2026-05-10) is **vestigial** — superseded records with zero code/config
> references; it is prunable. No live code or config reference points at the
> in-repo copy.

### Intended build order (within this track)

1. **crypto** — signing/identity primitives ([`core/crypto`](../../micyte/core/crypto)).
2. **contracts** — the agreement model ([`modules/domains/contracts`](../../micyte/domains/contracts)).
3. **contact card + default FND subordinate** — a node's published identity,
   defaulting to an FND-subordinate relationship.
4. **msn_registry** — the network's name/address registry.
5. **template-driven fill** — contact cards and contracts populated from
   templates.
6. **reference exchange** — cross-node reference sharing
   ([`modules/domains/reference_exchange`](../../micyte/domains/reference_exchange)),
   brokered through the
   [`mediation_surface`](../../micyte/state_machine/mediation_surface).

**Spec page:** [`90-network-contract-architecture.md`](90-network-contract-architecture.md).

---

## Track 4 — Desktop app + local DB (long horizon)

**Goal:** ship the portal as a desktop app backed by a local database.

**Deltas:** D6.

Persistence is already **form-factor-agnostic** (the MOS database is reached
through a port, not hard-wired to a server deployment), so this is a packaging
and local-store-binding exercise rather than a rewrite. It is the **last** thing
to build: it benefits from a stable tool/lens surface (Tracks 1–2) and an
optional network layer (Track 3).

**Spec page:** [`95-desktop-app-local-db.md`](95-desktop-app-local-db.md).

---

## Dependency graph

A directed acyclic graph of which deltas unblock which. Arrows read
"unblocks / is prerequisite for".

```
                       ┌─────────────────────────────────────────┐
                       │ Track 0 — Foundations                    │
                       │ D1: core→adapter inversion,              │
                       │     dedupe engine, boundary test         │
                       └───────────────┬─────────────────────────┘
                                       │ (clean core/ to author against)
                                       ▼
        ┌──────────────────────────────────────────────────────────┐
        │ Track 1 — Tools-first (near-term)  ★                       │
        │   needs: D3 hyphae-flags ─┐                                │
        │          D2 read-path YAML├─► demo sandboxes + tools/lenses│
        │          D4 lens UX ──────┘                                │
        └───────────────┬───────────────────────────┬──────────────┘
                        │ converges faster with      │ matures into
                        ▼                             ▼
        ┌──────────────────────────────┐   (Track 1 must be delivering
        │ Track 2 — MSS/YAML coherence  │    value before starting ↓)
        │   D3 terminology              │             │
        │   D2 read+write unification   │             ▼
        └──────────────────────────────┘   ┌──────────────────────────┐
                                            │ Track 3 — Network (defer) │
                                            │ D5: crypto → contracts →  │
                                            │ contact card/FND-sub →    │
                                            │ msn_registry → template   │
                                            │ fill → reference exchange │
                                            └─────────────┬────────────┘
                                                          │ optional input
                                                          ▼
                                            ┌──────────────────────────┐
                                            │ Track 4 — Desktop + local │
                                            │ DB (D6, long horizon)     │
                                            └──────────────────────────┘
```

Key edges:

- **D1 → everything.** A clean `core/` is the substrate all authoring sits on.
- **D3 + D2(read) + D4 → Track 1.** You cannot bind tools to flags without the
  flag mechanism (D3), read them ergonomically without read-path YAML (D2), or
  let operators switch presentation without the lens UX (D4).
- **D2 + D3 → Track 2.** Full read/write unification and the settled MSS form.
- **Track 1 (delivering) → Track 3.** Do not start the network until tools earn
  their keep.
- **Tracks 1–3 → Track 4.** Desktop packaging is last; it consumes a stable
  surface.

---

## Suggested ordering

A single numbered sequence with rationale. Steps 1–3 are the only ones that
should touch code in the near term.

1. **Close D1 (core→adapter inversion + dedupe + boundary test).** *Why first:*
   cheapest high-leverage fix; makes "simplified core" real and prevents
   regressions via the new architecture test. **(Landing in this batch.)**
2. **Define + implement the hyphae-flag mechanism (D3, mechanism only).** *Why
   next:* tools are meaningless without something to bind to; this is the
   smallest unit of product value.
3. **Unify the read path on WORKBOOK-YAML (D2, read path).** *Why:* makes tool
   authoring symmetric (read shape == write shape) before you write many tools.
4. **Add the Utilities/Control-Panel lens UX (D4).** *Why:* lets operators see
   the payoff of recognized data without code changes — turns Track 1 into a
   demo.
5. **Build demo sandboxes + the first tools/lenses (Track 1 body).** *Why:* the
   actual deliverable; everything above existed to make this clean.
6. **Reconcile MSS/SAMRAS terminology + full read/write YAML unification
   (Track 2).** *Why:* converge the model once real tools have exercised it; do
   it after you know what tools actually need.
7. **Network layer, in stub order (Track 3): crypto → contracts → contact card
   + default FND subordinate → msn_registry → template-driven fill → reference
   exchange.** *Why deferred:* LOW value until single-node tooling is proven;
   HIGH cost and surface area.
8. **Desktop app + local DB (Track 4).** *Why last:* packaging on top of a
   stable, form-factor-agnostic core.

---

## What this batch delivered

This batch delivered the **wiki** (this roadmap plus the spec pages it links)
and **three code fixes** that close Track 0's D1:

1. Relocated the datum engine into `core/datum_semantics/` (removing the
   duplication between
   [`core/mss/datum_identity.py`](../../micyte/core/mss/datum_identity.py)
   and
   [`adapters/sql/datum_semantics.py`](../../micyte/adapters/sql/datum_semantics.py)).
2. Flipped the inverted imports in
   [`core/datum_ops/ops.py`](../../micyte/core/datum_ops/ops.py) and
   [`core/datum_ops/node_ops.py`](../../micyte/core/datum_ops/node_ops.py)
   to depend inward on `core/`.
3. Added `test_core_datum_ops_boundaries.py` to
   [`fnd_app/tests/architecture/`](../../fnd_app/tests/architecture).

**Everything else on this roadmap is design-spec → future work.** Tracks 1–4
are sequenced and specified here and in the linked pages, but were not
implemented in this batch. Use this page to decide what to build next.

---

[← Overview](00-overview-and-glossary.md) ·
[Delta map](50-delta-map.md) ·
[Engineering standards](05-engineering-standards.md)
