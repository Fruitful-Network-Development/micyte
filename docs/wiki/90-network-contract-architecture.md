# 90 — Network & Contract Architecture

> Status: **part as-built, part design-spec** (rewritten 2026-08-04)
> [← Overview](00-overview-and-glossary.md)

This page specifies the **network layer** for a MiCyte portal instance: how one
instance advertises itself, how two instances establish an authenticated encrypted
relationship, and how they exchange datum documents under it.

**Read this first.** Until 2026-08-04 this page opened by declaring that "almost
every package this layer needs is an empty 1-LOC scaffold today". That was true
when it was written and has been false since **2026-08-02**. Identity, the signed
handshake, the minted symmetric key, replay protection, closed-channel admission
and an outbound client are all **live**. Anyone building "the network layer" from
scratch is building a second one.

Sections are labelled. **As-built** claims cite `path:line`. **Proposed** sections
are proposals and nothing here authorizes implementing them.

The account/alias model — what it means for one instance to have a *presence* on
another's channel — is **not specified here**. It has its own design of record:
the Network Cooperation Convention (2026-08-04, internal design note).
This page owns the transport under it.

---

## Problem

A peer-to-peer network of portal instances, where:

- each instance publishes a **contact card** — its point of contact, saying what
  it is reachable at and what its public key is;
- instances track **contracts**: relationships bootstrapped by asymmetric key
  exchange and then run on a **rotating symmetric key**;
- under a contract, instances exchange datum documents and **share resources**
  without either side hosting a second copy of the other's data;
- discovery works before any contract exists, because a contract cannot be the
  thing that tells you how to form a contract.

---

## As-built (LIVE since 2026-08-02)

Every claim in this section is code on the box today. Commits: `e9af4d3b`,
`21f04959` (handshake + transport), and the outbound client that followed.

### Identity comes from the contact card, never from the contract

The card publishes `public_signature` — **registrar address `3-1-17`**
(`micyte/core/datum_ops/field_registry.py:105`). That is the identity a
handshake verifies against.

**It cannot live on the contract.** A contract carrying the key that authorises
it authorises itself. The test that pins the rule clears the card entry, leaves
the contract `ACTIVE`, and asserts the handshake refuses.

The **address** is a second card field, `instance_endpoint` — **`3-1-18`**
(`field_registry.py:114`) — and not the `dns` cell, which is a *website* domain.
Publishing an endpoint is both the opt-in to being reachable and the switch that
makes the inbound route answer at all. See
`micyte/core/identities/domains.py` for the domain validation it reuses.

> **Encoding trap, permanent:** the `niu-baciloid-256-64` babelette holds **64
> characters**, not 256 bits. An Ed25519 PEM is ~113 characters and does **not**
> fit. Base64 of the raw 32 bytes is 44 and does. The PEM is rebuilt at verify
> time.

### The handshake

`fnd_app/instances/_shared/runtime/contract_handshake.py`

| Step | Function | Note |
|---|---|---|
| Request | `build_request` (`:78`) | signed with the card key; carries a fresh X25519 ephemeral |
| Verify | `verify_request` (`:111`) | against the requester's **card** signature |
| Offer | `build_offer` (`:161`) | responder **mints the contract's symmetric key** and seals it to the ECDH |
| Open | `open_offer` (`:220`) | requester unseals it |
| Traffic | `seal_traffic` (`:277`) | every subsequent message sealed with that key |
| Expiry | `key_is_expired` (`:305`) | epoch + `key_period_seconds`, a parameter so rotation is testable in ms |

A signature key **signs**; it does not agree. Signing the ephemeral is what stops
a machine-in-the-middle — that is why both are present and neither is enough.

Schemas: `mycite.v2.network.contract.request.v1` / `.offer.v1` / `.sealed.v1`
(`:39-41`). Skew tolerance `HANDSHAKE_SKEW_SECONDS = 120` (`:45`).

### Replay protection is a sequence, not a nonce

`contract_sequence_store.py` — a SQLite store at `contract_transport.sqlite3`
(`:30`) that **both gunicorn workers write**, with an atomic
`UPDATE … WHERE last_seq < ?` (`accept_sequence`, `:57`).

This replaced a per-process nonce cache, which two workers made unsound. A
sequence beats a nonce twice over: bounded state, and it carries **ordering**.

### Contract lifecycle

`contract_negotiation.py` — `open_request` (`:61`), `receive_request` (`:166`),
`accept_request` (`:189`), `answer_request` (`:210`), `refuse_request` (`:289`),
`revoke_contract` (`:297`). `_legal_events` (`:157`) derives the legal moves from
the record's state, so an illegal move raises rather than being written.

`contract_store.py` persists records as `mycite.portal.contract.v2` (`:33`) under
`<private>/contracts/`. Revoking destroys the key.

### Key material

`instance_keys.py` — a vault at `<private>/keys/`, **0600 inside 0700**, which
refuses to re-mint and refuses wide permissions (`_FORBIDDEN_MODE_BITS`, `:43`),
and resolves the `vault://` ref (`resolve_vault_ref`, `:93`) that dangled since
the start.

An epoch is minted **once**: re-minting the *same* bytes is idempotent, different
bytes raises. That is what makes collection-by-re-request safe (below).

The audit deny-list at `local_audit/service.py:18-30` forbids persisting key
material into the local log, and still does.

### Closed-channel admission — two doors

`closed_channel_admission.py`. **Sealed** traffic (possession of the contract key
IS the proof — exactly two instances hold it) and a **signed** bootstrap (headers
at `:37-45`, `CLOCK_SKEW_SECONDS = 300` at `:50`).

Every refusal is the **identical 404** the open route gives an unknown channel.
The reason is logged, never returned. No CORS on that route.

### The outbound client — requests actually send

`instance_client.py` — `post_contract_request` (`:115`) to
`POST /__instance/contract/request` (`:61`), a **sibling** family to `/__channel/`
rather than a widening of it: `/__channel/` is GET-only by construction and that
is what makes it safe unauthenticated, so the write door earns its own safety by
verifying the card signature **before recording anything**.

`endpoint_for` (`:162`) reads the peer's address off its card.

> **Re-requesting IS collecting.** `build_request` never persists its ephemeral,
> so the same signed message is also the poll. Undecided → "recorded". Decided and
> keyed → **re-seal the existing key** to the ephemeral in hand.
> Two traps, both paid for once already: never **mint** on a collection (it
> rotates the key out from under a counterparty who already settled, for asking
> twice), and carry the original `key_minted_at` (restamping restarts the period,
> so rotation never fires).

### Crypto homes

`micyte/core/crypto/signature.py` (the port) and `channel.py` (the cipher shape),
with the Ed25519 peripheral behind them. `core/crypto` is **no longer a scaffold**.

### What is genuinely still local-only

`modules/cross_domain/network_root/service.py:20` is a **presenter over the local
system log**, not a transport. Its `contract_filters` / `contract_id`
(`:44`, `:56`, `:102`) filter **audit-log correspondence rows** and have nothing
to do with network contracts. Do not conflate them; the naming collision is
recorded here so nobody "unifies" them.

---

## As-built: the channel surface

Specified in the Hosted Channel Convention (2026-08-02, internal design note)
and summarized here only where the network layer touches it.

- A **hosted channel** is an outward-facing surface terminating at a sandbox the
  instance hosts. `micyte/channels/` — the third register beside `micyte/tools/`
  and `micyte/automation/`, with mutual refusals.
- **Open** channels admit any caller: routes under `/__channel/`, outside
  `/portal`, **GET-only by construction**, 404-not-403. No write route is
  registered — the posture is "no write path exists", not "writes are denied".
  A refusal implies an authorizer that could be wrong; an absence cannot be.
- **Closed** channels admit contract-holding instances, gated by
  `ChannelState.ACTIVE.grants_channel` + `granted_sandboxes()`.
- A channel is denoted **as data**, on the registrar `channels` document, one row
  per (entity, channel, access, hosting msn). `build_profile` picks it up with
  zero code change.

### Sources manifests — the cross-sandbox mechanism, with a reader

`micyte/core/sources.py`. A sandbox never reads another sandbox's documents; it
reads its own `sources` manifest, whose rows the owning sandbox published to it.
A row is name + kind + `rf.3-1-12` content hash.

**Two hash families**, dispatched from the row's declared kind — this is a real
trap and it is worth knowing before touching a manifest:

- `datum_document` rows pin the **document-id version hash** (already in the
  canonical id; verifying costs nothing);
- `boundary` / `taxonomy` / `profiles` / `events` rows pin the **MSS bitstream
  hash** of the document's datum closure (must be encoded to check).

These are different numbers for the same document. A resolver that assumed one
family would report every row of the other as total drift.

**Fault asymmetry:** a *stale* pin is a fault (mechanical fix: re-pin it). A
*missing* or *unverifiable* source is reported, not gated — it needs a decision
about the data, and a gate that fails forever teaches everyone to ignore it.

---

## As-built: the data plane it composes

- **MSS version hash + hyphae.** `micyte/core/mss/`. A document's version hash is
  the MSS hash of its downward closure; a datum's hyphae value is the MSS hash of
  *that datum's* closure.
- **A datum address is a document-local coordinate.** `4-1-1` is not a name —
  on the live instance **7,241 addresses are claimed by two or more documents**.
  Closures resolve through `DocumentScopedIndex` (`micyte/core/mss/document_adapter.py`),
  which puts the document's own rows in front of the tenant index. Before
  2026-08-04, 627 of 630 documents hashed a closure they did not contain.
- **A hyphae names its document.** `micyte/core/mss/hyphae.py` —
  `build_hyphae(address, *, index, document, source_msn)` requires the document,
  refuses one that does not *carry* the address, and writes the canonical
  `document_id` into the payload. Schema `mycite.v2.mos.hyphae.v2`; v1 is refused
  by name because it cannot say where its focus datum came from.
  **This is the network's citation primitive** — see the cooperation convention §3.
- **Canonical document ids** already embed the msn:
  `lv.<msn_id>.<sandbox>.<name>.<version_hash>`
  (`micyte/core/document_naming/__init__.py:65`, `:109`).
- **WORKBOOK-YAML** transport form, MSS-hash-preserving on round-trip
  (`micyte/core/datum_io/codec.py:97`, `:112`).

---

## Proposed — what is still unbuilt

> Proposals. Nothing here is authorized by this page.

### 1. `msn_registry` — discovery without a contract

A contract cannot be how you learn to form a contract, so discovery must work
unauthenticated. The proposal: FND publishes an `msn_registry` MSS artifact —
every current contact card's reachable address and card reference — pullable with
no contract, over the same public-stills discipline `/__mss/public/stills/` already
uses (allowlist, 404-not-403). Versioned and integrity-checkable like any other
MSS document.

An instance contacting a peer it has never met pulls the registry, resolves the
peer's `msn_id` → card, reads `public_signature` and `instance_endpoint`, and
*then* handshakes.

**Open:** freshness (push / poll / TTL), whether the registry is signed by FND so
it can be trusted through an untrusted relay, and whether FND's key is pinned at
ship time or bootstrapped. FND is the de-facto trust root of this network and that
should be a decision, not a default.

### 2. Resolving a magnet reference against a remote instance

The cooperation convention specifies the *reference*
(`hy.<msn>.<sandbox>.<document>.<version_hash>.<address>`) and what resolving it
returns (a hyphae). The transport exists; the **resolve operation on top of it
does not**, and it needs its own design pass covering batching, partial failure,
and what an unreachable member renders as.

### 3. Rotation cadence

`key_is_expired` takes `key_period_seconds` as a parameter and the default is 30
days (`contract_handshake.py:50`). Whether rotation should also be volume-based,
and whether it re-handshakes or ratchets from the existing session, is undecided.

### 4. What an open session may offer toward joining

Joining requires a contract, a contract requires a card and a signature, so a bare
browser cannot join. What an open channel may *offer* toward joining — and how it
does so without acquiring a write path — is undesigned. The constraint is
non-negotiable: no write route under `/__channel/`.

---

## Superseded — the Manager/Subordinate template model

Earlier revisions of this page specified an exchange in which a **Manager**
published a WORKBOOK-YAML template, a **Subordinate** filled only its empty fields
and recompiled the MSS, and *that recompiled MSS was the contribution*; plus a
default Subordinate relationship every instance held to FND.

**That model is superseded** by the cooperation convention (2026-08-04). What
survives and what does not:

| | |
|---|---|
| **Survives** | The published blank/empty document as the **shape** of a relationship — convention §2a. Versioned, so "which version of the agreement" is answerable. |
| **Survives** | Filling only declared-empty addresses, structure unchanged. Still enforceable with `preview_document_insert` (`micyte/core/datum_semantics/engine.py:545` — the earlier revision of this page cited `adapters/sql/datum_semantics.py:474`, which no longer exists). |
| **Superseded** | The **roles**. Manager/Subordinate made every relationship hierarchical; channel membership is not. |
| **Superseded** | Filling with **values**. The member binds **references** to datums it already holds, and the channel resolves them. Returning a filled document duplicates the member's data into a second copy that drifts on the next edit — the thing this network exists to avoid. |
| **Superseded** | The default FND-Manager relationship. Discovery is `msn_registry` (§1 above), which needs no relationship at all. |

The one-line version: **the contribution is not a filled document, it is a
resolvable citation.**

---

## Migration path

1. ~~Crypto primitives~~ — **done** (`core/crypto`, Ed25519 peripheral).
2. ~~Contract model + lifecycle~~ — **done** (`contract_store`, `contract_negotiation`).
3. ~~Contact card + reachable address~~ — **done** (`3-1-17`, `3-1-18`).
4. ~~Authenticated transport + replay protection~~ — **done** (handshake, sequence store).
5. ~~Outbound client~~ — **done** (`instance_client`).
6. **`msn_registry`** — discovery without a contract. Next.
7. **Magnet resolution** — the remote-read operation over the existing transport.
8. **Accounts / aliases** — per the cooperation convention, once 6 and 7 hold.

**Not built, and the honest reason:** no delivery between two *live* instances has
ever happened. FND publishes the only signature and the only endpoint in a
236-node registry, and it is not its own counterparty. The two-instance proof is
`fnd_app/tests/integration/test_contract_delivery_over_tcp.py` — a real socket,
two private directories.

---

## Acceptance

This page is accepted when:

- Every **as-built** claim cites a resolvable `path:line` and is true of the tree
  today. A claim that goes stale is a defect in this page, not a footnote.
- The as-built / proposed / superseded split is explicit, and no reader can mistake
  a proposal for something that exists — **or** something that exists for something
  they must build.
- It does not restate the account/alias model that the cooperation convention owns.
- No crypto or contract code is implemented by editing this page.
