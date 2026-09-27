# 50 — Delta Map: Vision vs. As-Built

> Status: as-built &nbsp;·&nbsp; [← Overview](00-overview-and-glossary.md) &nbsp;·&nbsp; **re-audited 2026-08-23**

**Re-audited 2026-08-23, and four rows had CLOSED without anybody moving them.** A gap map
is the one page where staleness does active harm: a closed gap listed as open sends
somebody to build a thing that exists, and the severity column makes it look urgent while
it does it. Each correction below cites what closed it.

Two rows were wrong about a FILE:

* *"No `test_core_datum_ops_boundaries.py` exists"* — it does, and it is the guard the row
  asked for.
* *"992 LOC"* for the workbench read service — 1,448 now. A line count in prose is a
  measurement with a shelf life; it is kept only where the row's argument turns on size.

Two were wrong about a SURFACE:

* *"The lens management/toggle surface does not exist"* — `/portal/api/lenses` and
  `/portal/api/lenses/toggle` both ship, and `fnd_app/tests/unit/test_lens_management.py`
  covers "the full stack of the lens Utilities/Control-Panel UX": catalog, per-lens
  bindings, the resolver honouring an enabled-set, persistence, and the round trip.
* the menu-bar tool search is in `templates/portal.html` as
  `[data-menubar-tool-search-mount]`, browser-verified 2026-08-23.

One row is worth reading with its history rather than deleting: **"toggle in Control
Panel"** names a surface that was RETIRED on 2026-08-16. The capability survived the
surface — the toggles moved rather than went away — which is why the row reads as open
against a search for "control panel" and is closed against a search for what it does.

This is the **delta-map hub** for the MiCyte Portal re-orientation. It tabulates,
layer by layer, the distance between the target architecture (L1 CORE / L2
SURFACE / L3 UI / Tools & Lenses / Network / Desktop) and what is actually on
disk today. Every "Current state" cell cites a real `path:line` that was read
before the claim was written; every "Spec page that closes it" links to the
forward-reference page that will carry the normative design.

Paths are repo-relative (rooted at the repository top). Since the 2026-07-16 core
extraction the shippable core lives under `micyte/` (`core` / `ports` /
`state_machine` / `tools` / `adapters` / `domains`) and the FND app + portal host
under `fnd_app/`. Spec-page links are relative to `docs/wiki/`.

> **2026-07-22 reconciliation.** The datum-address / hyphae / MSS-semantics engine
> was **relocated from the SQL adapter into core** — its canonical home is now
> `micyte/core/datum_semantics/engine.py` (it depends only on `ports` + the stdlib,
> so it was never SQL-coupled; `micyte/adapters/sql/datum_semantics.py` is a
> back-compat re-export shim). This **resolves the "core→adapter inversion"** that
> rows #1 and #3 below flag as HIGH: `micyte/core/datum_ops/ops.py:25` and
> `micyte/core/datum_ops/node_ops.py:21` now `import from micyte.core.datum_semantics`
> (core→core), and **no `micyte/core` module imports `micyte.adapters`** (verified
> 2026-07-22). The `datum_semantics.py:<line>` citations in the rows below point at
> the shim; the real engine lines are `MSS_VERSION_HASH_POLICY`=20,
> `build_document_version_identity`=142, `build_document_semantics`=345,
> `preview_document_insert`/`_delete`/`_move`=545/597/658, and `compute_mss_hash` is
> now `micyte/core/mss/datum_identity.py:30`. A row-by-row rebase onto these lines is
> the remaining delta-map cleanup.

---

## Master delta table

### L1 — CORE (lean MOS datum-database library)

| Vision element | Current state (cited path:line) | Gap | Severity | Spec page that closes it |
|---|---|---|---|---|
| `core/` is the lean, dependency-free datum library; adapters depend on core, never the reverse | `micyte/core/datum_ops/ops.py:24` and `micyte/core/datum_ops/node_ops.py:17` both `import from micyte.adapters.sql.datum_semantics` | **core→adapter inversion.** The real 663-LOC engine lives in the adapter (`micyte/adapters/sql/datum_semantics.py:1`, which itself only imports `ports/datum_store`); `core` reaches *up* into it for `parse_datum_address` and the `preview_document_*` reorder engine. | HIGH | [05-engineering-standards.md](05-engineering-standards.md), [61-mss-and-hyphae-form-spec.md](61-mss-and-hyphae-form-spec.md) |
| One canonical MSS identity routine | `micyte/core/mss/datum_identity.py:101` (`compute_mss_hash`) is a near-duplicate of `micyte/core/datum_semantics/engine.py:143` (`build_document_version_identity`); the core docstring (`datum_identity.py:106`) admits it "Produces the same version_hash". Core copy is consumed only by `micyte/state_machine/portal_shell/tool_eligibility.py:21` (`derive_hyphae_chain`) plus tests. | Two implementations of the same SHA256-over-canonical-rows identity drift independently; the core copy exists mainly to avoid the inverted import above. | HIGH | [61-mss-and-hyphae-form-spec.md](61-mss-and-hyphae-form-spec.md), [05-engineering-standards.md](05-engineering-standards.md) |
| Architecture test pins the core→adapter boundary | **CLOSED (re-audit 2026-08-23).** `fnd_app/tests/architecture/test_core_datum_ops_boundaries.py` exists and is the guard this row asked for, beside its siblings `test_core_datum_refs_boundaries.py`, `test_datum_store_port_boundaries.py`, `test_state_machine_boundaries.py` and `test_micyte_fnd_boundary.py` | The one boundary that is actually violated is the one with no guard, so the inversion can re-grow silently. | HIGH | [05-engineering-standards.md](05-engineering-standards.md) |
| MSS = canonical single-sequence **bitstream** (address size, bitmap, start/stop slices); hyphae = MSS + focus-exclusion preprocessing | MSS document identity is **JSON payload + SHA256**: `micyte/adapters/sql/datum_semantics.py:14` (`MSS_VERSION_HASH_POLICY = "mos.mss_sha256_v1"`) and `:136`. Hyphae chain is a rudi dependency-closure (`:209` `build_document_semantics`, policy `"mos.hyphae_chain_v1"` at `:15`). A real bitstream codec exists only for SAMRAS node-address magnitudes (`micyte/core/structures/samras/codec.py:42`), not for document MSS. No `focus`-exclusion preprocessing exists anywhere in `core/mss`, `datum_semantics`, or `core/datum_ops`. | MSS form-factor and hyphae-derivation differ from the vision's bitstream/focus-exclusion model; there is no single canonical bitstream for whole documents. | MED | [61-mss-and-hyphae-form-spec.md](61-mss-and-hyphae-form-spec.md) |

### L2 — SURFACE (operate within MOS rules; one MSS doc per document)

| Vision element | Current state (cited path:line) | Gap | Severity | Spec page that closes it |
|---|---|---|---|---|
| MOS is the single canonical store; surface persists datum docs in MSS form, one per doc | MOS-only authority is enforced (`fnd_app/tests/architecture/test_no_disk_datum_authorities.py`, `test_no_filesystem_datum_authority_in_runtime.py`); SQL adapter is the sole backend (`micyte/adapters/sql/datum_store.py`) behind the port protocol (`micyte/ports/datum_store/contracts.py:8`). | Largely as-built. Residual: the MSS "form" persisted is the JSON-row + SHA256 identity (see L1 row above), not the vision bitstream. | LOW | [61-mss-and-hyphae-form-spec.md](61-mss-and-hyphae-form-spec.md) |

### L3 — UI (load docs as WORKBOOK-YAML; modular fns/tools/lenses; pipeline to MOS-save)

| Vision element | Current state (cited path:line) | Gap | Severity | Spec page that closes it |
|---|---|---|---|---|
| One WORKBOOK-YAML materialization that both **loads** the doc into the UI and **pipelines edits back** to MOS-save | **Split path.** WRITE path uses the WORKBOOK-YAML codec: `fnd_app/instances/_shared/runtime/portal_datum_workbench_mutation_runtime.py:511` calls `workbook_codec.from_yaml(...)` (codec at `micyte/core/datum_io/codec.py:1`, transport-only; wrapper at `micyte/core/datum_ops/workbook.py:16`). READ path skips the codec entirely: `micyte/tools/workbench_ui/service.py:14` imports `datum_semantics` and projects SQL→JSON directly (`json.dumps`/`raw_json` at `service.py:538`,`:579`). | The UI reads through one representation (SQL→JSON) and writes through another (YAML codec). A round-trip is never a single materialized artifact, so load/edit/save is not one pipeline. | HIGH | [70-yaml-materialization-pipeline.md](70-yaml-materialization-pipeline.md) |
| Excel-like UX over the YAML at runtime | Workbench UI exists (`micyte/tools/workbench_ui/service.py`, 1,448 LOC as of 2026-08-23) and renders cells/overlays, but it operates on the SQL→JSON projection, not on the YAML workbook. | UX is present but not unified on the WORKBOOK-YAML substrate the vision specifies. | MED | [70-yaml-materialization-pipeline.md](70-yaml-materialization-pipeline.md) |

### Tools & Lenses

| Vision element | Current state (cited path:line) | Gap | Severity | Spec page that closes it |
|---|---|---|---|---|
| Compiled-hyphae value vs registered value → **"raise a flag"** → bind tool to that hyphae value / family-root datum | Tool binding is set-intersection, not a flag: `micyte/state_machine/portal_shell/tool_eligibility.py:64` matches `applies_to_archetype`/`applies_to_source_kind` against an archetype set widened along the hyphae chain (`:96`–`:110`). No "raise a flag" / "hyphae-flag" / "minimum-but-complete abstraction path" symbol exists in `packages`. | There is no flag artifact emitted on hyphae-value match, and no minimum-but-complete compilation path; eligibility is computed from archetype/source_kind tokens. | MED | [60-canonical-datum-and-hyphae-flags.md](60-canonical-datum-and-hyphae-flags.md), [80-tool-authoring-guide.md](80-tool-authoring-guide.md) |
| Lenses keyed to **flags** (nominal ASCII vs binary magnitude); managed in **Utilities**, toggled in **Control Panel** | Lens binding resolves on `family` → `overlay` → `value_kind` (`micyte/state_machine/lens/registry.py:51`–`:66`), consumed at `micyte/tools/workbench_ui/service.py:528`. Lenses are display transforms (`IdentityLens`, `BinaryTextLens`, … at `micyte/state_machine/lens/base.py:31`–`:115`). No flag keying. | Lenses change display but are not keyed to hyphae flags. | MED | [81-lens-authoring-guide.md](81-lens-authoring-guide.md), [60-canonical-datum-and-hyphae-flags.md](60-canonical-datum-and-hyphae-flags.md) |
| Lens lifecycle UX: **manage in Utilities, toggle in Control Panel** | **CLOSED (re-audit 2026-08-23).** `/portal/api/lenses` and `/portal/api/lenses/toggle` ship, and `test_lens_management.py` covers the whole stack — catalog, per-lens bindings, the resolver honouring an enabled-set (disabled → identity passthrough), persistence, and the round trip. The original search missed it because it looked for the words: the CONTROL PANEL was retired 2026-08-16 and the toggles moved rather than went away. | Closed. The vision's *placement* is superseded, not its capability. | MED | [81-lens-authoring-guide.md](81-lens-authoring-guide.md) |
| Tools searched in menu-bar, dropdown-added to an interface panel, bound to family-root datum | Palette eligibility recognizer exists (`tool_eligibility.py:64`) and a tool-surface adapter is wired (`fnd_app/instances/_shared/portal_host/static/v2_portal_tool_surface_adapter.js`). | Mechanism is archetype/source_kind eligibility, not family-root/hyphae-flag binding (see row above). | MED | [80-tool-authoring-guide.md](80-tool-authoring-guide.md) |

### NETWORK (msn cards, contracts, keys, msn_registry)

> **Rewritten 2026-08-04.** Every row in this block previously read "entirely
> stubbed", which was true when written and false since **2026-08-02**. A
> `__init__.py` that is still a 1-LOC scaffold does **not** mean the package is
> empty — `core/crypto` and `domains/contracts` both carry real modules beside an
> inert `__init__`, and citing only the `__init__` was how this block went stale
> without any line moving. Cite the module that does the work.

| Vision element | Current state (cited path:line) | Gap | Severity | Spec page |
|---|---|---|---|---|
| Pure crypto primitives (asymmetric bootstrap + timely symmetric key) | **BUILT.** `micyte/core/crypto/signature.py` (verification port) + `channel.py` (cipher shape), Ed25519 peripheral FND-side. The `__init__.py:1` scaffold docstring remains and is misleading — the package is not inert. | Only the algorithm-agility question is open (§Proposed). | CLOSED | [90-network-contract-architecture.md](90-network-contract-architecture.md) |
| Contract lifecycle | **BUILT.** `micyte/domains/contracts/channel.py` (`ChannelState`, 190 LOC) + `fnd_app/instances/_shared/runtime/contract_store.py:33`, `contract_negotiation.py:61`–`:297`, `contract_sequence_store.py:57`. | — | CLOSED | [90-network-contract-architecture.md](90-network-contract-architecture.md) |
| ~~Manager/Subordinate template fill~~ | **SUPERSEDED**, not built. The member binds *references*; the channel resolves them. See the "Superseded" section of the spec page and the Network Cooperation Convention (2026-08-04, internal design note) §2a. | Returning a filled document was the duplication this network exists to avoid. | N/A | [90-network-contract-architecture.md](90-network-contract-architecture.md) |
| Reference exchange / resource sharing | **PARTIAL.** `micyte/domains/reference_exchange/message.py` (P2P message, 185 LOC) exists; `micyte/core/references.py` reads contract-declared `rc.<owner>.<resource>` grants. | The *resolve a magnet against a remote instance* operation is undesigned. | MED | [90-network-contract-architecture.md](90-network-contract-architecture.md) |
| msn contact card (reachable address + public key) | **BUILT as card fields**: `public_signature` `3-1-17` and `instance_endpoint` `3-1-18` (`micyte/core/datum_ops/field_registry.py:105`, `:114`). Identity is read from the card, never from the contract. | — | CLOSED | [90-network-contract-architecture.md](90-network-contract-architecture.md) |
| FND `msn_registry` MSS (DNS-like, no-contract pull) | **NOT BUILT.** The publication discipline it would use exists (`/__mss/public/stills/`, allowlist + 404-not-403). | Discovery still requires knowing the peer already. | MED | [90-network-contract-architecture.md](90-network-contract-architecture.md) |
| Shell mediation of contract events into the local log | `micyte/state_machine/mediation_surface/__init__.py:1` — still a scaffold. | Genuinely stubbed. | LOW | [90-network-contract-architecture.md](90-network-contract-architecture.md) |
| Two LIVE instances exchanging anything | **NOT DONE, and not a code gap.** FND publishes the only signature and the only endpoint in a 236-node registry and is not its own counterparty. Proof exists over a real socket: `fnd_app/tests/integration/test_contract_delivery_over_tcp.py`. | Needs a second instance, not a second implementation. | — | [90-network-contract-architecture.md](90-network-contract-architecture.md) |
| Cross-tool shared scaffolding for network tools | `micyte/tools/_shared/__init__.py:1` — 1-LOC scaffold. | Entirely stubbed. | LOW now / HIGH later | [80-tool-authoring-guide.md](80-tool-authoring-guide.md) |

### DESKTOP (end state: desktop app with local DB)

| Vision element | Current state (cited path:line) | Gap | Severity | Spec page that closes it |
|---|---|---|---|---|
| Persistence is form-factor-agnostic so a local-DB desktop build is possible | Persistence is already behind a port protocol: `micyte/ports/datum_store/contracts.py:8` defines the document/row schemas and a `@runtime_checkable` protocol; the only backend today is `micyte/adapters/sql/datum_store.py`. | Foundation is desktop-ready (swap the adapter), but **no local-DB adapter and no desktop shell exist**; nothing wires a local store. | LOW now / HIGH later | [95-desktop-app-local-db.md](95-desktop-app-local-db.md), [99-roadmap.md](99-roadmap.md) |

---

## Top 5 deltas, ranked

1. **core→adapter import inversion (HIGH).** The "lean core" claim is the most
   load-bearing one in the whole re-orientation, and it is false at the
   import level: `core/datum_ops/{ops,node_ops}.py` reach up into
   `adapters/sql/datum_semantics.py`, which holds the real 663-LOC engine.
   Until this flips, "simplified core" cannot be true and the duplicate identity
   routine (#2) cannot be retired. Closed by [05-engineering-standards.md](05-engineering-standards.md) +
   [61-mss-and-hyphae-form-spec.md](61-mss-and-hyphae-form-spec.md).

2. **Duplicate MSS identity + missing boundary test (HIGH).**
   `core/mss/datum_identity.py:101` and `adapters/sql/datum_semantics.py:136`
   compute the same hash two ways, and there is no
   `tests/architecture/test_core_datum_ops_boundaries.py` to stop the inversion
   from regrowing. These two are the cleanup that #1 unlocks.

3. **Materialization read/write split (HIGH).** The UI reads via SQL→JSON
   (`workbench_ui/service.py`) and writes via the WORKBOOK-YAML codec
   (`mutation_runtime.py:511`). The vision wants one YAML materialization for
   the whole load→edit→save loop. Closed by
   [70-yaml-materialization-pipeline.md](70-yaml-materialization-pipeline.md).

4. **No hyphae-flag mechanism (MED).** Neither tools (`tool_eligibility.py`)
   nor lenses (`lens/registry.py`) bind on a "raised flag" from a
   compiled-hyphae value match; both use token/family intersection. This is the
   conceptual center of the Tools & Lenses vision and is absent. Closed by
   [60-canonical-datum-and-hyphae-flags.md](60-canonical-datum-and-hyphae-flags.md).

5. **Network transport BUILT; discovery and remote reads still missing
   (was "fully stubbed" — corrected 2026-08-04).** Identity from the contact
   card (`3-1-17`/`3-1-18`), a signed X25519 handshake minting a rotating
   symmetric key, a monotonic replay sequence store both workers share,
   closed-channel admission, and an outbound client are **live since
   2026-08-02**. `core/crypto`, `domains/contracts` and
   `domains/reference_exchange` carry real modules beside `__init__.py`
   scaffolds that were never updated — **citing only an `__init__` is how this
   entry stayed wrong while the code moved**. Still genuinely absent:
   `msn_registry` (discovery without a contract), resolving a reference against
   a remote instance, `state_machine/mediation_surface`, `tools/_shared`, and
   the local-DB adapter. **Two live instances have never exchanged anything** —
   that needs a second instance, not more code. Closed by
   [90-network-contract-architecture.md](90-network-contract-architecture.md) +
   [95-desktop-app-local-db.md](95-desktop-app-local-db.md).

---

## Quick wins vs. deep work

**Quick wins (mechanical, low-risk, mostly within `core`/tests):**

- Add `fnd_app/tests/architecture/test_core_datum_ops_boundaries.py` to assert
  `core/datum_ops/*` never imports from `adapters/*` (a *failing* guard at first —
  it documents delta #1 and turns green once #1 is fixed). See
  [05-engineering-standards.md](05-engineering-standards.md).
- De-duplicate MSS identity: make `core/mss/datum_identity.py` and
  `adapters/sql/datum_semantics.py` share one implementation once the import
  direction is settled (delta #2).
- Move `parse_datum_address` / address algebra down into `core` so
  `datum_ops` stops importing it from the adapter (the first concrete step of
  delta #1).

**Deep work (design-first, cross-layer, needs the spec pages):**

- Unify materialization on WORKBOOK-YAML for both read and write
  (delta #3) — touches `tools/workbench_ui/service.py`, `core/datum_io`, and
  the mutation runtime. See [70-yaml-materialization-pipeline.md](70-yaml-materialization-pipeline.md).
- Define and implement the hyphae-flag mechanism and (if adopted) the
  bitstream MSS form (deltas #3/#4) — net-new semantics across `core/mss`,
  the lens registry, and tool eligibility. See
  [60-canonical-datum-and-hyphae-flags.md](60-canonical-datum-and-hyphae-flags.md),
  [61-mss-and-hyphae-form-spec.md](61-mss-and-hyphae-form-spec.md),
  [80-tool-authoring-guide.md](80-tool-authoring-guide.md),
  [81-lens-authoring-guide.md](81-lens-authoring-guide.md).
- Build the lens management/toggle UX (Utilities + Control Panel) — net-new UI
  (delta #4 lifecycle). See [81-lens-authoring-guide.md](81-lens-authoring-guide.md).
- Finish the network: `msn_registry` (discovery without a contract) and resolving
  a reference against a remote instance. Crypto, contracts and cards are **done**;
  the Manager/Subordinate roles are **superseded, not pending**. Plus the desktop
  local-DB adapter (delta #5).
  See [90-network-contract-architecture.md](90-network-contract-architecture.md),
  [95-desktop-app-local-db.md](95-desktop-app-local-db.md),
  [99-roadmap.md](99-roadmap.md).
