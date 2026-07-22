# 90 — Network & Contract Architecture

> Status: design-spec
> [← Overview](00-overview-and-glossary.md)

This page specifies the **future network layer** for a MiCyte portal instance:
how one portal advertises itself, how two portals establish an encrypted
relationship, and how they exchange datum documents under that relationship. It
is the single largest delta between the current codebase and the product vision:
**almost every package this layer needs is an empty 1-LOC scaffold today.**

Everything under **Proposed model**, **Data shapes / interfaces**, and
**Migration path** is a *proposal*. The **Current reality** section is grounded
in code that exists today (cited `path:line`). Nothing here authorizes
implementing crypto or contract code; this page exists so that work can be
planned coherently.

---

## Problem

The product vision describes a peer-to-peer network of portal instances:

- Each instance exposes an **msn contact card** and an **FND profile card** as
  its public-facing point of contact. The card tells outside APIs *what is
  available for request* and *what the instance's public key is*.
- An instance tracks **contracts**: relationships established via
  **asymmetric-encryption key exchange** that then run on a **timely (rotating)
  symmetric key**.
- In a contract, roles assign one party **Manager** and the other
  **Subordinate**. Multiple relationships can exist, and either party may take
  either role across different relationships.
- Under a relationship, the **Manager** publishes **YAML-convention template
  files** (and optionally a base **MSS form** of a datum document). The
  **Subordinate** fills *only the empty/undefined datum fields* of that template,
  using the **same pre-defined datum-base reference abstractions** the Manager
  used, then **recompiles the MSS form**. That recompiled MSS *is* the
  Subordinate's contribution to the relationship. This is also the mechanism for
  **resource sharing**.
- Because the `msn_id` structure is always changing, every portal holds a
  **default Subordinate relationship to the FND legal-entities portal**. FND is
  the Manager and defines the field for the `msn_id` contact card (domain
  reachable, and/or IPv4, and/or IPv6); each Subordinate fills in its own
  reachable access domain/IP for its `msn_id`.
- The FND portal's `msn_id` contact card additionally defines **public resources
  that can be pulled without a contract** — the **`msn_registry` MSS file**: the
  datum-entry abstractions of all current `msn_id` contact cards (DNS-like) and
  where they can be reached.

**Today none of this network behavior exists.** The packages reserved for it are
inert scaffolds, and the one "network" service that does exist is a *read-only
presenter* of the local system log — not a network transport. See below.

---

## Current reality

Mapping each vision element to the code that would host it. Unless noted, the
package is a **2-file scaffold** (`README.md` + `__init__.py`) with no behavior.

### Reserved-but-empty stubs

| Vision element | Stub package | Evidence |
|---|---|---|
| Asymmetric + symmetric key primitives | `core/crypto` | `micyte/core/crypto/README.md:3` — "Placeholder for pure cryptographic primitives split out from v1 `vault_session`." `micyte/core/crypto/__init__.py:1` — `"""Inert package scaffold."""` |
| Contract model + Manager/Subordinate roles | `modules/domains/contracts` | `micyte/domains/contracts/README.md:3` — "Placeholder for contract domain semantics only." `__init__.py:1` inert. |
| Cross-portal datum lookup / fill | `modules/domains/reference_exchange` | `micyte/domains/reference_exchange/README.md:3` — "Placeholder for reference-exchange domain semantics only." `__init__.py:1` inert. |
| Sandbox orchestration (template publish/fill runtime) | `sandboxes/orchestration` | `fnd_app/packages/sandboxes/orchestration/README.md:3` — "shared sandbox orchestration helpers that do not own domain semantics." |
| System-scoped orchestration boundary | `sandboxes/system` | `fnd_app/packages/sandboxes/system/README.md:3` — "system-scoped orchestration boundaries only." |
| Shell-owned mediation surface | `state_machine/mediation_surface` | `micyte/state_machine/mediation_surface/README.md:3` — "shell-owned mediation surface behavior." |

### Partial / related code that exists

- **"Network" today is local-only, read-only.**
  `fnd_app/packages/modules/cross_domain/network_root/service.py:20`
  (`NetworkRootReadModelService`) is a *presenter* over the portal-instance
  **system-log workbench**, not a network transport. Its own notes are explicit:
  `service.py:60-62` — "NETWORK is the portal-instance system-log workbench …
  read-only, non-reducer-owned, and does not host tool or sandbox runtime
  behavior." The result `kind` is `network_system_log_workspace`
  (`service.py:68`). It already surfaces `contract_filters` / `contract_count`
  / per-record `contract_id` (`service.py:44`, `:56`, `:102`) — but those are
  filters over the *local* audit log, **not** cross-portal contracts.

- **Read-model port for that surface.**
  `micyte/ports/network_root_read_model/contracts.py:44`
  (`NetworkRootReadModelRequest`) carries `portal_tenant_id` + optional
  `portal_domain` (`:45-47`); the port protocol
  `NetworkRootReadModelPort.read_network_root_model` is at
  `contracts.py:150`. This is the natural read seam to extend for a future
  `msn_registry` read — but it currently returns only local system-log payloads.

- **Domain validation (no IP support yet).**
  `micyte/core/identities/domains.py:14` (`is_plain_domain`) and
  `:37` (`require_plain_domain`) validate plain DNS domains only. There is **no**
  IPv4/IPv6 validation, which the `msn_id` contact-card field requires
  ("domain reachable and/or IPv4 and/or IPv6").

- **Portal authority read seam.**
  `micyte/ports/portal_authority/contracts.py:49`
  (`PortalAuthorityRequest`) and `:81` (`PortalAuthoritySource`: capabilities +
  `tool_exposure_policy` + `ownership_posture`). Its README is explicit that
  **grant mutation, identity hashing, and runtime composition are out of scope
  this phase** (`micyte/ports/portal_authority/README.md:15-19`).
  This seam describes *what a portal exposes* locally; a network layer would
  consume it to decide what to advertise on a contact card.

- **The only "symmetric_key" reference is a deny-list, not an implementation.**
  `fnd_app/packages/modules/cross_domain/local_audit/service.py:25` lists
  `"symmetric_key"` inside `FORBIDDEN_LOCAL_AUDIT_KEYS`
  (`service.py:18-30`, alongside `private_key`, `hmac_key`, `api_key`, …). i.e.
  the codebase already *forbids persisting* key material into the local audit
  log — there is no code that creates, rotates, or transports a symmetric key.

### Building blocks that already work (the network layer will compose these)

- **MSS form + version hash.**
  `micyte/core/mss/datum_identity.py:101`
  (`compute_mss_hash`) computes the canonical MSS version hash under policy
  `MSS_VERSION_HASH_POLICY = "mos.mss_sha256_v1"` (`:13`); hyphae chains derive
  at `:126` (`derive_hyphae_chain`). The SQL-side equivalents
  `build_document_version_identity` / `build_document_semantics` /
  `preview_document_insert` live in
  `micyte/adapters/sql/datum_semantics.py:136`, `:209`, `:474`.
  → The Subordinate's "recompile the MSS form" step *is* a call into this
  existing identity engine. See `61-mss-and-hyphae-form-spec.md`.

- **WORKBOOK-YAML template/transport form.**
  `micyte/core/datum_io/codec.py:97` (`workbook_to_yaml`) and `:112`
  (`workbook_from_yaml`), schema
  `DATUM_IO_WORKBOOK_SCHEMA = "mycite.v2.datum_io.workbook.v1"` (`:26`), with
  single-document `to_yaml`/`from_yaml` at `:55`/`:88`. The module docstring
  (`codec.py:1-9`) calls this a **transport-only** form that **preserves the MSS
  version hash** on round-trip — exactly the "YAML-convention template file" the
  Manager publishes. See `70-yaml-materialization-pipeline.md`.

- **`msn_id`-keyed document naming.**
  `micyte/core/document_naming/__init__.py:35` (`ParsedDocumentId`,
  field `msn_id` at `:39`), `:65` (`format_canonical_document_id`, which
  validates `msn_id` at `:82-84`), and `:109` (`parse_canonical_document_id`).
  Canonical ids already embed an `msn_id` segment
  (`lv.<msn_id>.<sandbox>.<name>.<hash>`), so a contact card *per `msn_id`* fits
  the existing namespace.

**Net:** the *data plane* (MSS, hyphae, WORKBOOK-YAML, `msn_id` naming) exists
and is solid. The *network plane* (keys, contracts, roles, contact card,
registry, cross-portal exchange) is entirely unbuilt.

---

## Proposed model

> All of this is a proposal. Names are suggestions for the eventual
> implementation, chosen to fit existing seams.

### 1. Public point of contact — msn contact card + FND profile card

Each portal instance publishes two related but distinct artifacts:

- **msn contact card** (per `msn_id`): a small datum document describing *how to
  reach this `msn_id`* and *what it offers*:
  - reachable access: `domain` (validated by `is_plain_domain`,
    `domains.py:14`) **and/or** IPv4 **and/or** IPv6 (new validators needed);
  - the portal's **advertised public key** (the contract-establishment key);
  - a manifest of **requestable resources** (sandbox/doc references the portal
    is willing to negotiate a contract over);
  - a manifest of **no-contract public resources** (pullable without a contract).
- **FND profile card**: the human/brand-facing profile (the FND legal-entities
  presentation). It is the *discovery* surface; the msn contact card is the
  *machine* surface. The two share an `@id`/`msn_id` linkage.

Because both are datum documents, they are authored, versioned, and transported
with the *existing* MSS + WORKBOOK-YAML machinery — no new document format.

### 2. Public-key advertisement

The contact card carries the portal's **long-lived asymmetric public key**. This
key is *only* used to bootstrap a contract (key agreement / authentication), not
for bulk data. Private key material lives behind `core/crypto` (proposed home)
and must **never** appear in the local audit log — the deny-list at
`local_audit/service.py:18-30` already enforces this invariant and should be
extended to cover any new key field names.

### 3. Contract establishment — asymmetric handshake → timely symmetric key

A **contract** is established by:

1. **Discover** the counterparty's msn contact card (via the registry — §7 — or
   a known domain/IP).
2. **Handshake**: an asymmetric-key exchange authenticated by each party's
   advertised public key, agreeing on a fresh **symmetric session key**.
3. **Run**: all subsequent datum exchange under the contract is encrypted with
   that symmetric key, which is **timely** — it has a bounded lifetime and is
   **rotated** on a cadence (and/or on key-volume). Rotation re-runs a light
   handshake; the contract record persists across rotations.

`core/crypto` owns the primitives (key generation, agreement, symmetric
encrypt/decrypt, rotation schedule helpers). `modules/domains/contracts` owns the
*contract lifecycle* (propose → accept → active → rotating → revoked) and the
*role assignment*; it must not embed crypto, only call into `core/crypto`.

### 4. Manager / Subordinate roles + multiple relationships

A contract names exactly two parties and assigns **roles** per *relationship*:

- **Manager** — defines templates and the base MSS doc shape; owns the schema.
- **Subordinate** — fills empty datum fields and recompiles; owns the values.

A single contract can carry **multiple relationships**, and the **same party can
be Manager in one relationship and Subordinate in another**. Roles are therefore
a property of the *relationship*, not of the contract or the party globally.

### 5. Template-driven Subordinate fill (the resource-sharing mechanism)

This is the core data exchange and is built entirely on existing data-plane
parts:

1. **Manager publishes** a **WORKBOOK-YAML template** (`codec.py:97`
   `workbook_to_yaml`) — and optionally a **base MSS document** — over the
   contract's symmetric channel. The template contains **empty/undefined datum
   fields** plus the **datum-base reference abstractions** (the `rf.*` reference
   tokens / hyphae anchors) those fields resolve against.
2. **Subordinate fills only the empty fields.** It may *not* add, move, or
   redefine fields; it may only supply values for fields the Manager left empty,
   and only using the *same* pre-defined datum-base abstractions. This constraint
   is enforceable with the existing preview/validation functions
   (`datum_semantics.py:474` `preview_document_insert` and friends) — a fill that
   introduces a new address or changes structure is rejected.
3. **Subordinate recompiles MSS.** Calling `compute_mss_hash`
   (`datum_identity.py:101`) over the filled document yields a new MSS version
   hash. **That recompiled MSS form is the Subordinate's contribution** —
   returned to the Manager over the channel.
4. **Resource sharing** is the same flow with the roles reading naturally: the
   Manager "shares a resource" by publishing its shape; the Subordinate
   "contributes" by returning a filled, recompiled MSS. Either direction of
   sharing is just a relationship with the appropriate role assignment.

`modules/domains/reference_exchange` owns step (1)/(3) marshaling: resolving
which datum-base abstractions travel with a template, and validating that a
returned MSS only fills declared-empty fields.

### 6. Default FND Subordinate contract (msn_id field definition)

Every portal ships with **one pre-established relationship**: it is a
**Subordinate to the FND legal-entities portal** (FND is **Manager**). Because the
`msn_id` structure changes over time, FND publishes the **template for the
`msn_id` contact-card field** — defining which of `{domain, IPv4, IPv6}` are
present and how they're shaped. Each portal, as Subordinate, **fills in its own
reachable access** values and recompiles. This keeps every portal's contact card
schema-compatible with the network's current `msn_id` convention without each
portal hard-coding it.

### 7. `msn_registry` — no-contract public pull (DNS-like)

The FND portal's own msn contact card additionally exposes **public resources
that require no contract**. The headline one is the **`msn_registry` MSS file**:

- a datum document whose entries are the **datum-entry abstractions of every
  current `msn_id` contact card** plus **where each can be accessed**
  (domain/IPv4/IPv6);
- pullable by any portal **without** establishing a contract — the network's
  bootstrap/discovery layer, analogous to DNS;
- itself an MSS document, so it is versioned and integrity-checkable with
  `compute_mss_hash` like any other datum doc; freshness is conveyed by its MSS
  version hash + a published timestamp.

A portal that wants to contact a peer it has never met first pulls `msn_registry`
from FND (no contract), looks up the peer's `msn_id` → contact card location,
fetches that contact card, reads the peer's public key, and *then* runs the
asymmetric handshake (§3) to form a contract.

---

## Data shapes / interfaces

> Sketches only — field names indicative. Each shape names its proposed host
> package.

### msn contact card (datum document — host: authored as a normal datum doc; advertised via a new network adapter)

```yaml
# transported as datum_io WORKBOOK-YAML (codec.py:97), one sheet
msn_id: <msn_id>                      # matches document_naming msn_id segment
access:
  domain: portal.example.org          # validated by is_plain_domain (domains.py:14)
  ipv4: 203.0.113.10                   # NEW validator needed in core/identities
  ipv6: "2001:db8::10"                 # NEW validator needed
public_key:
  alg: <RSA|ECDSA|Ed25519>            # see open questions
  pem: <advertised public key>         # private half lives behind core/crypto
requestable:                           # negotiable only under a contract
  - { ref: "lv.<msn_id>.<sandbox>.<name>", role_hint: subordinate }
public_pull:                           # no-contract resources (FND: msn_registry)
  - { ref: "stl.<msn_id>.msn_registry", freshness: mss_version_hash }
```

### contract record (host: `modules/domains/contracts`)

```yaml
contract_id: <stable id>
parties:
  - { msn_id: <self>,  public_key_ref: ... }
  - { msn_id: <peer>,  public_key_ref: ... }
state: proposed | accepted | active | rotating | revoked
session:
  symmetric_key_ref: <opaque handle into core/crypto; NEVER the raw key>
  established_at: <hops/ts>
  rotates_at: <hops/ts>                # "timely" symmetric key
relationships:                         # multiple, role per-relationship
  - relationship_id: <id>
    manager:    <self|peer msn_id>
    subordinate:<peer|self msn_id>
    template_ref: "<WORKBOOK-YAML doc id>"   # Manager-published
    base_mss_ref: "<optional base MSS doc id>"
    contributions:                            # Subordinate-returned recompiled MSS
      - { mss_version_hash: "sha256:…", at: <hops/ts> }
```

Note the deliberate name collision avoidance: the *existing*
`network_root` "contract" filters (`service.py:44`) are **local audit-log
correspondence rows**, not these network contract records. The new model lives in
a different package and must not be conflated with the read-model presenter.

### msn_registry MSS layout (host: read seam via `ports/network_root_read_model`; authored as `stl.` doc)

```yaml
# an MSS datum document; entries are contact-card abstractions + locations
schema: msn_registry.v1
entries:
  - { msn_id: <peer-a>, access: {domain|ipv4|ipv6}, card_ref: <doc id>, card_mss: "sha256:…" }
  - { msn_id: <peer-b>, access: {…}, card_ref: <doc id>, card_mss: "sha256:…" }
published_at: <hops/ts>
registry_mss: "sha256:…"               # compute_mss_hash over this doc (datum_identity.py:101)
```

### package ownership summary (proposed)

| Concern | Proposed host | Today |
|---|---|---|
| Key gen / agreement / symmetric encrypt / rotation | `core/crypto` | scaffold (`core/crypto/README.md:3`) |
| Contract lifecycle + role assignment | `modules/domains/contracts` | scaffold (`.../contracts/README.md:3`) |
| Template publish + Subordinate-fill validation + cross-portal lookup | `modules/domains/reference_exchange` | scaffold (`.../reference_exchange/README.md:3`) |
| `msn_registry` / contact-card **read** | extend `ports/network_root_read_model` | local-only read-model (`contracts.py:44`, `:150`) |
| Reachable-access validation (domain + IPv4 + IPv6) | extend `core/identities` | domain-only (`domains.py:14`) |
| Sandbox runtime to host the publish/fill workflow | `sandboxes/orchestration` / `sandboxes/system` | scaffolds |
| Shell mediation of contract events into the local log | `state_machine/mediation_surface` | scaffold |
| MSS recompile + version hash (reused, not new) | `core/mss/datum_identity` | exists (`:101`) |
| WORKBOOK-YAML template transport (reused, not new) | `core/datum_io/codec` | exists (`:97`) |

---

## Migration path

Phased so each step is independently testable and never ships half a security
boundary. (Coarse roadmap; sequencing tracked in `99-roadmap.md`.)

1. **Crypto primitives** — implement `core/crypto`: key generation, asymmetric
   key agreement/auth, symmetric encrypt/decrypt, rotation-schedule helpers.
   Extend the audit deny-list (`local_audit/service.py:18-30`) to cover any new
   private-key field names. *No network I/O yet.*
2. **Contract model + roles** — implement `modules/domains/contracts`: contract
   record, state machine (`proposed→active→rotating→revoked`), per-relationship
   Manager/Subordinate assignment. Pure domain logic over `core/crypto` handles;
   no transport.
3. **Contact card + default FND Subordinate contract** — define the msn contact
   card datum-doc shape; add IPv4/IPv6 validators to `core/identities`; ship the
   pre-established FND-Manager / self-Subordinate relationship that fills the
   `msn_id` access field.
4. **`msn_registry`** — author the registry as an `stl.` MSS doc; expose a
   **no-contract public pull** read path by extending
   `ports/network_root_read_model` (and a new transport adapter). Discovery works
   before any contract exists.
5. **Template-driven fill** — implement the publish/fill workflow in
   `modules/domains/reference_exchange` + a sandbox runtime under
   `sandboxes/orchestration`: Manager publishes WORKBOOK-YAML (`codec.py:97`),
   Subordinate fills only empty fields (validated via
   `datum_semantics.py:474`) and recompiles MSS (`datum_identity.py:101`).
6. **Reference exchange (general resource sharing)** — generalize step 5 beyond
   the FND default: arbitrary Manager↔Subordinate resource sharing under any
   active contract, with contract events mediated into the local log via
   `state_machine/mediation_surface`.

A desktop/offline instance follows the same path but pulls `msn_registry` and
syncs contracts opportunistically; see `95-desktop-app-local-db.md`.

---

## Open design questions

- **Asymmetric algorithm**: RSA vs ECDSA vs Ed25519/X25519 for the advertised
  public key. Ed25519 (sign) + X25519 (agreement) is the modern default; RSA is
  the most universally interoperable. Decide before step 1, since the contact
  card carries the algorithm tag.
- **Symmetric key rotation cadence**: time-based, volume-based, or both? What is
  "timely"? Does rotation require a full re-handshake or a ratchet derived from
  the existing session?
- **Registry freshness / consistency**: how stale may a cached `msn_registry`
  be? Push (FND notifies) vs pull (portals poll) vs TTL on the MSS version hash?
  How are revoked/rotated `msn_id`s reflected (analogous to DNS negative caching)?
- **Auth for cross-portal pulls**: `msn_registry` and contact cards are pullable
  *without* a contract — what (if anything) rate-limits or authenticates those
  anonymous pulls? Is the public-pull manifest itself signed by FND so a
  Subordinate can trust a registry it fetched from an untrusted relay?
- **Trust root**: is FND's own public key pinned/shipped with every portal, or
  is there a bootstrap-trust step? (FND is the de-facto CA of this network.)
- **Naming collision**: the local `network_root` read-model already uses
  "contract" for audit-log correspondence (`service.py:44`). Keep network
  contracts in `modules/domains/contracts` and avoid overloading the term in the
  read-model, or rename one side, before either surfaces in UI.

---

## Acceptance

This page is **design-spec** and is accepted when:

- It states the problem (the network layer is entirely stubbed) and summarizes
  the vision faithfully.
- Every vision element is mapped to its **actual** current stub or partial with a
  resolvable `path:line` citation, and the stub-vs-partial distinction matches
  what is in the tree today.
- The proposed model defines each element — contact card + FND profile card,
  public-key advertisement, asymmetric handshake → timely symmetric key,
  Manager/Subordinate multi-relationship roles, template-driven Subordinate fill
  via WORKBOOK-YAML + MSS recompile, resource sharing, the default FND
  Subordinate contract, and the `msn_registry` no-contract pull — and is clearly
  labelled as a proposal.
- Data-shape sketches name a proposed host package for each interface.
- A phased migration path and a set of open design questions are recorded.
- No crypto/contract code is implemented by this unit (docs-only).
