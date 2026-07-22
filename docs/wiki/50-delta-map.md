# 50 — Delta Map: Vision vs. As-Built

> Status: as-built &nbsp;·&nbsp; [← Overview](00-overview-and-glossary.md)

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
| One canonical MSS identity routine | `micyte/core/mss/datum_identity.py:101` (`compute_mss_hash`) is a near-duplicate of `micyte/adapters/sql/datum_semantics.py:136` (`build_document_version_identity`); the core docstring (`datum_identity.py:106`) admits it "Produces the same version_hash". Core copy is consumed only by `micyte/state_machine/portal_shell/tool_eligibility.py:21` (`derive_hyphae_chain`) plus tests. | Two implementations of the same SHA256-over-canonical-rows identity drift independently; the core copy exists mainly to avoid the inverted import above. | HIGH | [61-mss-and-hyphae-form-spec.md](61-mss-and-hyphae-form-spec.md), [05-engineering-standards.md](05-engineering-standards.md) |
| Architecture test pins the core→adapter boundary | No `fnd_app/tests/architecture/test_core_datum_ops_boundaries.py` exists (sibling guards do: e.g. `test_core_datum_refs_boundaries.py`, `test_datum_store_port_boundaries.py`, `test_state_machine_boundaries.py`) | The one boundary that is actually violated is the one with no guard, so the inversion can re-grow silently. | HIGH | [05-engineering-standards.md](05-engineering-standards.md) |
| MSS = canonical single-sequence **bitstream** (address size, bitmap, start/stop slices); hyphae = MSS + focus-exclusion preprocessing | MSS document identity is **JSON payload + SHA256**: `micyte/adapters/sql/datum_semantics.py:14` (`MSS_VERSION_HASH_POLICY = "mos.mss_sha256_v1"`) and `:136`. Hyphae chain is a rudi dependency-closure (`:209` `build_document_semantics`, policy `"mos.hyphae_chain_v1"` at `:15`). A real bitstream codec exists only for SAMRAS node-address magnitudes (`micyte/core/structures/samras/codec.py:42`), not for document MSS. No `focus`-exclusion preprocessing exists anywhere in `core/mss`, `datum_semantics`, or `core/datum_ops`. | MSS form-factor and hyphae-derivation differ from the vision's bitstream/focus-exclusion model; there is no single canonical bitstream for whole documents. | MED | [61-mss-and-hyphae-form-spec.md](61-mss-and-hyphae-form-spec.md) |

### L2 — SURFACE (operate within MOS rules; one MSS doc per document)

| Vision element | Current state (cited path:line) | Gap | Severity | Spec page that closes it |
|---|---|---|---|---|
| MOS is the single canonical store; surface persists datum docs in MSS form, one per doc | MOS-only authority is enforced (`fnd_app/tests/architecture/test_no_disk_datum_authorities.py`, `test_no_filesystem_datum_authority_in_runtime.py`); SQL adapter is the sole backend (`micyte/adapters/sql/datum_store.py`) behind the port protocol (`micyte/ports/datum_store/contracts.py:8`). | Largely as-built. Residual: the MSS "form" persisted is the JSON-row + SHA256 identity (see L1 row above), not the vision bitstream. | LOW | [61-mss-and-hyphae-form-spec.md](61-mss-and-hyphae-form-spec.md) |

### L3 — UI (load docs as WORKBOOK-YAML; modular fns/tools/lenses; pipeline to MOS-save)

| Vision element | Current state (cited path:line) | Gap | Severity | Spec page that closes it |
|---|---|---|---|---|
| One WORKBOOK-YAML materialization that both **loads** the doc into the UI and **pipelines edits back** to MOS-save | **Split path.** WRITE path uses the WORKBOOK-YAML codec: `fnd_app/instances/_shared/runtime/portal_datum_workbench_mutation_runtime.py:511` calls `workbook_codec.from_yaml(...)` (codec at `micyte/core/datum_io/codec.py:1`, transport-only; wrapper at `micyte/core/datum_ops/workbook.py:16`). READ path skips the codec entirely: `micyte/tools/workbench_ui/service.py:14` imports `datum_semantics` and projects SQL→JSON directly (`json.dumps`/`raw_json` at `service.py:538`,`:579`). | The UI reads through one representation (SQL→JSON) and writes through another (YAML codec). A round-trip is never a single materialized artifact, so load/edit/save is not one pipeline. | HIGH | [70-yaml-materialization-pipeline.md](70-yaml-materialization-pipeline.md) |
| Excel-like UX over the YAML at runtime | Workbench UI exists (`micyte/tools/workbench_ui/service.py:1`, 992 LOC) and renders cells/overlays, but it operates on the SQL→JSON projection, not on the YAML workbook. | UX is present but not unified on the WORKBOOK-YAML substrate the vision specifies. | MED | [70-yaml-materialization-pipeline.md](70-yaml-materialization-pipeline.md) |

### Tools & Lenses

| Vision element | Current state (cited path:line) | Gap | Severity | Spec page that closes it |
|---|---|---|---|---|
| Compiled-hyphae value vs registered value → **"raise a flag"** → bind tool to that hyphae value / family-root datum | Tool binding is set-intersection, not a flag: `micyte/state_machine/portal_shell/tool_eligibility.py:64` matches `applies_to_archetype`/`applies_to_source_kind` against an archetype set widened along the hyphae chain (`:96`–`:110`). No "raise a flag" / "hyphae-flag" / "minimum-but-complete abstraction path" symbol exists in `packages`. | There is no flag artifact emitted on hyphae-value match, and no minimum-but-complete compilation path; eligibility is computed from archetype/source_kind tokens. | MED | [60-canonical-datum-and-hyphae-flags.md](60-canonical-datum-and-hyphae-flags.md), [80-tool-authoring-guide.md](80-tool-authoring-guide.md) |
| Lenses keyed to **flags** (nominal ASCII vs binary magnitude); managed in **Utilities**, toggled in **Control Panel** | Lens binding resolves on `family` → `overlay` → `value_kind` (`micyte/state_machine/lens/registry.py:51`–`:66`), consumed at `micyte/tools/workbench_ui/service.py:528`. Lenses are display transforms (`IdentityLens`, `BinaryTextLens`, … at `micyte/state_machine/lens/base.py:31`–`:115`). No flag keying. | Lenses change display but are not keyed to hyphae flags. | MED | [81-lens-authoring-guide.md](81-lens-authoring-guide.md), [60-canonical-datum-and-hyphae-flags.md](60-canonical-datum-and-hyphae-flags.md) |
| Lens lifecycle UX: **manage in Utilities, toggle in Control Panel** | No Utilities-manage / Control-Panel-toggle UX: a search for `control.panel`/`utilities` across `state_machine/lens`, `tools`, and `instances/` returns nothing lens-related. | The lens management/toggle surface does not exist. | MED | [81-lens-authoring-guide.md](81-lens-authoring-guide.md) |
| Tools searched in menu-bar, dropdown-added to an interface panel, bound to family-root datum | Palette eligibility recognizer exists (`tool_eligibility.py:64`) and a tool-surface adapter is wired (`fnd_app/instances/_shared/portal_host/static/v2_portal_tool_surface_adapter.js`). | Mechanism is archetype/source_kind eligibility, not family-root/hyphae-flag binding (see row above). | MED | [80-tool-authoring-guide.md](80-tool-authoring-guide.md) |

### FUTURE NETWORK (msn cards, contracts, keys, Manager/Subordinate, msn_registry)

| Vision element | Current state (cited path:line) | Gap | Severity | Spec page that closes it |
|---|---|---|---|---|
| Pure crypto primitives (asymmetric-key contracts + timely symmetric key) | `micyte/core/crypto/__init__.py:1` is `"""Inert package scaffold."""`; `micyte/core/crypto/README.md:1` = "Placeholder…". | Entirely stubbed. | LOW now / HIGH later | [90-network-contract-architecture.md](90-network-contract-architecture.md) |
| Contract domain (Manager defines template + base MSS; Subordinate fills + recompiles) | `micyte/domains/contracts/__init__.py:1` — 1-LOC scaffold. | Entirely stubbed; no Manager/Subordinate roles. | LOW now / HIGH later | [90-network-contract-architecture.md](90-network-contract-architecture.md) |
| Reference exchange / resource sharing | `micyte/domains/reference_exchange/__init__.py:1` — 1-LOC scaffold. | Entirely stubbed. | LOW now / HIGH later | [90-network-contract-architecture.md](90-network-contract-architecture.md) |
| msn contact card + FND profile card (advertise requestable resources + public key); FND `msn_registry` MSS (DNS-like) | No `msn_registry` / `contact_card` / `profile_card` / `public_key` artifact in `packages` (the lone `symmetric_key` hit at `fnd_app/packages/modules/cross_domain/local_audit/service.py:25` is an audit-redaction key list, unrelated). Mediation + system/orchestration sandboxes are scaffolds: `micyte/state_machine/mediation_surface/__init__.py:1`, `fnd_app/packages/sandboxes/orchestration/__init__.py:1`, `fnd_app/packages/sandboxes/system/__init__.py:1`. | Cards, registry, and mediation surface do not exist. | LOW now / HIGH later | [90-network-contract-architecture.md](90-network-contract-architecture.md) |
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

5. **Network/crypto/contract future fully stubbed (LOW now / HIGH later).**
   Seven directories (`core/crypto`, `modules/domains/contracts`,
   `modules/domains/reference_exchange`, `sandboxes/orchestration`,
   `sandboxes/system`, `state_machine/mediation_surface`, `tools/_shared`) are
   1-LOC `__init__.py` + 3-LOC README placeholders. The persistence port is
   already form-factor-agnostic, so the desktop end-state is reachable, but no
   network artifact, card, registry, or local-DB adapter exists yet. Closed by
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
- Stand up the network future (crypto, contracts, cards, `msn_registry`,
  Manager/Subordinate roles) and the desktop local-DB adapter (delta #5).
  See [90-network-contract-architecture.md](90-network-contract-architecture.md),
  [95-desktop-app-local-db.md](95-desktop-app-local-db.md),
  [99-roadmap.md](99-roadmap.md).
