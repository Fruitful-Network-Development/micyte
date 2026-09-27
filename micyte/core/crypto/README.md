# Crypto

Status: **built** (2026-08-02). Ports only — the implementations are FND-side.

micyte depends on `pyyaml` + `shapely` and nothing else, so this package declares
the *shape* of cryptographic operations and a peripheral supplies the
`cryptography`-backed implementation. An install that never engages a closed
channel pays nothing for either.

- `signature.py` — request signature verification port (Ed25519 in practice).
- `channel.py` — cipher / sealed-channel shape. Encrypt the bytes, never alter the
  plaintext: that rule is what lets one viewer decode both an open (plain) and a
  closed (sealed) session.

Private key material lives in the FND-side vault (`instance_keys.py` — 0600 inside
0700, refuses to re-mint, refuses wide permissions) and must never reach the local
audit log, which `local_audit/service.py` enforces with a deny-list.

Design spec: [`90-network-contract-architecture.md`](../../../docs/wiki/90-network-contract-architecture.md)
