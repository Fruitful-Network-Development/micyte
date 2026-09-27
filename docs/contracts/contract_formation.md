# Contract formation

## Status

Canonical, as built (LIVE since 2026-08-02; page written 2026-09-17, TASK-2026-09-16-002 P5).
Pinned by `fnd_app/tests/architecture/test_contract_pages_are_pinned.py` (every path here
exists) and by the handshake, negotiation and store tests under `fnd_app/tests/`.

## Purpose

State, in one place, how two instances form a contract on the msn network — so that
micyte.com can be the standardizing reference for it and an instance built from the
public package speaks the same handshake as FND's. The wiki page
`docs/wiki/90-network-contract-architecture.md` is the narrative; this is the contract.

## Identity comes from the contact card, never from the contract

An instance is identified by its msn contact card (`msn_profile_and_contact_card/`): the
card carries `public_signature` and `instance_endpoint`. A contract never introduces an
identity; it binds two identities that already exist.

## The handshake

`fnd_app/instances/_shared/runtime/contract_handshake.py`

| step | function | carries |
|---|---|---|
| request | `build_request` | signed with the card's key; a fresh X25519 ephemeral |
| verify | `verify_request` | checked against the requester's CARD signature |
| offer | `build_offer` | the responder mints the contract's symmetric key and seals it to the ECDH |
| open | `open_offer` | the requester unseals it |
| traffic | `seal_traffic` | every later message sealed with that key |
| expiry | `key_is_expired` | epoch + `key_period_seconds` (default 30 days; a parameter so rotation is testable) |

Schemas: `mycite.v2.network.contract.request.v1`, `.offer.v1`, `.sealed.v1`. Skew
tolerance `HANDSHAKE_SKEW_SECONDS = 120`. A signature key SIGNS; it does not agree —
signing the ephemeral is what stops a machine in the middle, which is why both are
present and neither is enough.

## Replay protection is a sequence

`fnd_app/instances/_shared/runtime/contract_sequence_store.py` — one SQLite store
(`contract_transport.sqlite3`) both gunicorn workers write, with an atomic
`UPDATE … WHERE last_seq < ?`. A sequence beats a nonce: bounded state, and it carries
ordering.

## Lifecycle

`fnd_app/instances/_shared/runtime/contract_negotiation.py` — `open_request`,
`receive_request`, `accept_request`, `answer_request`, `refuse_request`,
`revoke_contract`; the legal moves are derived from the record's state, so an illegal move
raises rather than being written. Records persist as `mycite.portal.contract.v2` under
`<private>/contracts/` (`contract_store.py`). Revoking destroys the key.

## Key material

`fnd_app/instances/_shared/runtime/instance_keys.py` — a vault at `<private>/keys/`, 0600
inside 0700, which refuses to re-mint and refuses wide permissions; `vault://` references
resolve through `resolve_vault_ref`. An epoch is minted once: re-minting the same bytes is
idempotent, different bytes raises. Key material never enters the local audit log.

## What is public without a contract

`/__mss/public/stills` and `/__mss/public/stills/<name>.mss` serve published stills to an
unidentified requester; `/__mss/public/registry.mss` serves the msn registry still (P5).
A closed or unpublished resource answers 404, never 403. Discovery cannot require a
contract — a contract is not how you learn to form one.

## Not yet standardized (proposals in wiki 90)

Resolving a `hy.<msn>.<sandbox>.<document>.<hash>.<addr>` magnet against a remote
instance; rotation cadence; what an open session may offer toward joining.
