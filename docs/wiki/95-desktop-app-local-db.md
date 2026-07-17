# Desktop App with a Local MOS Database

> Status: design-spec
[← Overview](00-overview-and-glossary.md)

This page specifies the eventual transition of the MiCyte Portal from a
server-hosted Flask app into a **desktop application that carries its own local
authority database** — one MOS SQLite DB per install. The same datum/MOS rules
apply unchanged; the only thing that moves is the *form factor* of the host.

Everything in **Current reality** is cited to code that exists today. Everything
in **Proposed model** and later sections is a **proposal** and is labelled as
such.

---

## Problem

The user wants each desktop install to be a self-contained authority: it boots,
opens (or creates) a local MOS database, and serves the portal UI inside a
native window — no remote server required. To get there the host must be
**form-factor-agnostic**: the same core/ports/adapters must run whether the
process is a long-lived server on EC2 or a short-lived desktop process behind a
WebView.

A "desktop app with a local DB" concretely requires:

1. **Per-install authority storage** — a writable SQLite file the install owns,
   created on first launch if absent, with the full MOS schema materialized
   automatically.
2. **A host that does not assume "server"** — no hard dependency on EC2,
   systemd, nginx, or a fixed public hostname for the *core* request path.
3. **A core/ports layer that never reaches for server-only infrastructure** so
   the desktop bootstrap can compose the same app object with different config.
4. **A way for an isolated install to still participate in the network** — i.e.
   contracts and contact cards across installs (see
   [`90-network-contract-architecture.md`](90-network-contract-architecture.md)).
5. **Offline-first behavior** — the install must be fully usable with no
   connectivity, deferring any network/registry exchange.

The good news: most of (1)–(3) is already true. The work is mostly *packaging*
and a thin *bootstrap harness*, not a re-architecture.

---

## Current reality (cited)

### SQLite is already the per-instance authority

The authoritative datum store is a SQLite adapter keyed by a DB file path. Its
constructor takes only a `db_file` plus an optional clock and the
`allow_legacy_writes` flag — nothing about servers, networks, or hostnames:

- `MyCiteV2/packages/adapters/sql/datum_store.py:117` —
  `SqliteSystemDatumStoreAdapter.__init__(self, db_file, *, clock=None, allow_legacy_writes=False)`.
- It implements the inward port contracts directly
  (`SystemDatumStorePort`, `AuthoritativeDatumDocumentMutationPort`,
  `PublicationTenantSummaryPort`, `PublicationProfileBasicsWritePort` —
  `MyCiteV2/packages/adapters/sql/datum_store.py:111`).

The schema is self-materializing. Opening any DB path creates the parent
directory and runs the schema script, so a *brand-new file* becomes a valid MOS
authority on first open — exactly what a fresh desktop install needs:

- `MyCiteV2/packages/adapters/sql/_sqlite.py:138` — `connect_sqlite()` does
  `path.parent.mkdir(parents=True, exist_ok=True)`, `PRAGMA foreign_keys = ON`,
  `PRAGMA journal_mode = WAL`, then `executescript(SCHEMA_SQL)`.
- The full MOS schema (`documents`, `datum_*_semantics`,
  `authoritative_catalog_snapshots`, `audit_records`, …) lives in
  `MyCiteV2/packages/adapters/sql/_sqlite.py:9` onward.

### Multiple instances / multiple DBs are already supported

Adapters are cached per resolved DB path, so the same process can address many
authority DBs and a desktop install can simply point at its own file:

- `MyCiteV2/instances/_shared/datum_store_accessor.py:17` —
  `_DATUM_STORE_BY_AUTHORITY_DB: dict[str, SqliteSystemDatumStoreAdapter]`.
- `MyCiteV2/instances/_shared/datum_store_accessor.py:26` —
  `_datum_store_for_authority_db(authority_db_file)` resolves the path
  (`str(root.resolve())`) and caches one adapter per DB
  (`MyCiteV2/instances/_shared/datum_store_accessor.py:39`).

The live server install today is just one such DB, at
`<instance-private-dir>/mos_authority.sqlite3`.

### The host is form-factor-agnostic

`create_app()` builds a Flask app from a single config object and falls back to
environment only when no config is passed — so a desktop bootstrap can construct
the config in-process and never touch the environment:

- `MyCiteV2/instances/_shared/portal_host/app.py:1601` —
  `def create_app(config: V2PortalHostConfig | None = None) -> Flask`, with
  `host_config = config or V2PortalHostConfig.from_env()`.
- The host stows the config on the app and serves its own bundled static JS and
  templates from paths relative to the module
  (`MyCiteV2/instances/_shared/portal_host/app.py:1605`–`1612`), so there is no
  external asset server in the core request path.
- Config carries the per-install authority DB explicitly:
  `V2PortalHostConfig.authority_db_file: Path | None`
  (`MyCiteV2/instances/_shared/portal_host/app.py:587`), surfaced in `/healthz`
  as `configured`/`exists`/`path`
  (`MyCiteV2/instances/_shared/portal_host/app.py:840`–`842`).

The front end is plain static JavaScript modules
(`MyCiteV2/instances/_shared/portal_host/static/v2_portal_shell.js`,
`v2_portal_shell_core.js`, `v2_portal_system_workspace.js`,
`v2_portal_network_workspace.js`, …) — i.e. a WebView pointed at the local host
gets the full UI with no build step.

### Hexagonal separation is enforced by contract

The ports layer is forbidden from importing adapters, tools, sandboxes, or
instances, so the core never assumes a server:

- `MyCiteV2/packages/ports/forbidden_dependencies.md` lists
  `packages/adapters/`, `packages/tools/`, `packages/sandboxes/`, `instances/`,
  and "runtime path helpers" as forbidden.
- `MyCiteV2/packages/ports/allowed_dependencies.md` restricts ports to
  `packages/core/`, `packages/modules/`, and (only for explicit surface
  contracts) `packages/state_machine/`.
- Network reads are themselves a port — `NetworkRootReadModelPort`
  (`MyCiteV2/packages/ports/network_root_read_model/contracts.py:148`) — a pure
  protocol over JSON-serializable request/result dataclasses, with no transport
  baked in.

### The seam for cross-install participation already exists in the schema

Each document row records both an `msn_id` and an `origin` discriminator:

- `MyCiteV2/packages/adapters/sql/_sqlite.py:57` — `msn_id TEXT NOT NULL`.
- `MyCiteV2/packages/adapters/sql/_sqlite.py:62` —
  `origin TEXT NOT NULL DEFAULT 'local' CHECK (origin IN ('local','foreign'))`.

So a local MOS already distinguishes documents it authored (`local`) from
documents mirrored in from elsewhere (`foreign`), and the network workspace
already renders a per-record **Linked Contract** view
(`MyCiteV2/instances/_shared/portal_host/static/v2_portal_network_workspace.js:207`).
That is the hook a desktop install uses to join the network without giving up
local authority. See
[`90-network-contract-architecture.md`](90-network-contract-architecture.md).

---

## Proposed model

> The following is a **proposal**, not implemented behavior.

### Embed the existing Flask host in a desktop shell

Keep `create_app()` exactly as-is and run it as a localhost-bound server inside
the desktop process; point a WebView at it. Candidate shells:

| Shell | How it embeds | Trade-off |
|---|---|---|
| **pywebview** | Same Python process; spawn `create_app()` on a loopback port, open a native WebView at `http://127.0.0.1:<port>/portal`. | Lowest friction — Python already in the bundle; the host code is reused verbatim. |
| **Tauri** | Rust shell + system WebView; runs the Python host as a bundled sidecar. | Smallest/most secure binary, auto-update built in; adds a Rust toolchain and a sidecar IPC seam. |
| **Electron** | Chromium + Node shell; runs the Python host as a child process. | Most familiar/portable; largest bundle, ships a full Chromium. |

In every option the *contract* is identical: a loopback HTTP host + a WebView.
The recommendation is **pywebview first** (reuses the Python runtime with no
sidecar), revisiting **Tauri** if binary size / auto-update / code-signing
become priorities.

### One local MOS SQLite per install

The shell picks a per-user, writable, app-private path (e.g. an OS app-data
directory) and passes it as `authority_db_file`. Because `connect_sqlite()`
auto-creates the file, directory, and schema
(`MyCiteV2/packages/adapters/sql/_sqlite.py:138`), first launch needs no
migration step — the empty file *becomes* a valid MOS. The same datum/MOS rules,
canonical-id posture, and L2 surface persistence apply unchanged
(see [`20-l2-surface-persistence.md`](20-l2-surface-persistence.md)).

### Network participation via the msn contact card

An offline install is still a first-class network member: its documents carry an
`msn_id` and `origin='local'` today
(`MyCiteV2/packages/adapters/sql/_sqlite.py:57`,`:62`). The proposed flow:

1. The install publishes a **contact card** (its msn identity + reachable
   address) into the network registry when, and only when, connectivity exists.
2. Contracts referencing that install are mirrored into the local MOS as
   `origin='foreign'` rows and shown via the existing **Linked Contract** panel
   (`…/v2_portal_network_workspace.js:207`).
3. All exchange flows through the `NetworkRootReadModelPort` seam
   (`MyCiteV2/packages/ports/network_root_read_model/contracts.py:148`) so the
   transport (HTTP today, something else later) stays an adapter detail.

Full design lives in
[`90-network-contract-architecture.md`](90-network-contract-architecture.md).

### Offline-first considerations

- The core request path (open DB → render surface → mutate documents) already
  has **zero network dependency**; only outbound email/AWS peripherals and the
  network registry need connectivity, and those are isolated behind adapters.
- Network sync is *opt-in and deferred*: the install works fully offline and
  reconciles contact cards / `foreign` contracts when a connection returns.
- WAL journaling is already on (`_sqlite.py:144`), which suits a single-process
  desktop writer with concurrent readers.

---

## Data shapes / interfaces

### What `V2PortalHostConfig` already abstracts

The host config (`MyCiteV2/instances/_shared/portal_host/app.py:578`) is a
frozen dataclass with these fields a desktop bootstrap would set in-process
instead of via env:

| Field | Server today | Desktop bootstrap (proposed) |
|---|---|---|
| `portal_instance_id` | e.g. `fnd` | the install's instance id |
| `private_dir` | the instance's private dir | app-private data dir |
| `public_dir` / `data_dir` / `webapps_root` | server tree | bundled / app-data dirs |
| `portal_domain` | live domain | a synthetic local domain |
| `authority_db_file` | `…/mos_authority.sqlite3` | per-install local MOS path |
| `portal_audit_storage_file` | optional file | optional local file |
| `tool_exposure_policy` | from `private/config.json` | bundled default policy |

`from_env()` (`…/app.py:619`) reads these from environment for the server; the
desktop shell would instead **construct the dataclass directly** and pass it to
`create_app(config=...)` — no env required, because of the
`config or from_env()` fallback at `…/app.py:1604`.

> Note: `__post_init__` (`…/app.py:590`) currently *validates that
> `public_dir`/`private_dir`/`data_dir`/`webapps_root` exist*. A desktop
> bootstrap must create those directories before constructing the config (see
> Migration path, step 2).

### What a desktop bootstrap would set

A new (proposed) bootstrap harness, e.g.
`instances/_shared/portal_host/desktop_bootstrap.py`, would:

1. Resolve an app-data root for the OS user.
2. Ensure the required dirs exist (to satisfy `__post_init__` validation).
3. Build `V2PortalHostConfig(...)` with `authority_db_file` pointing at the
   local MOS file.
4. Call `create_app(config)` and run it on a loopback port.
5. Hand that URL to the WebView shell.

No port or adapter changes are required for steps 1–4 — they already accept a
file path and compose without a server.

---

## Migration path (phased)

> Proposed sequencing. Earlier phases are read-only / confirmatory; nothing here
> changes runtime behavior for the live server install.

1. **Confirm no server-only assumptions in the core request path.** Audit
   `create_app()` and the surfaces it mounts for any hard dependency on env,
   absolute server paths, or network calls *on the datum/render/mutate path*.
   The ports `forbidden_dependencies.md` contract already guarantees the core is
   clean; this phase verifies the *host* composition is too. Output: a checklist
   of any env/absolute-path coupling to parametrize.
2. **Desktop bootstrap harness.** Add `desktop_bootstrap.py` (above) that
   constructs `V2PortalHostConfig` in-process, creates the required dirs, and
   boots `create_app(config)` on loopback against a fresh local MOS. Acceptance:
   launching it twice reuses the same local DB; deleting the DB and relaunching
   re-materializes the schema (relying on `_sqlite.py:138`).
3. **Package the WebView shell.** Wrap the loopback host in the chosen shell
   (pywebview first). Produce a signed, runnable artifact per OS. No core/ports
   changes.
4. **Wire the network/registry layer.** Implement the contact-card publish +
   `foreign`-contract mirror behind the `NetworkRootReadModelPort` seam so
   desktop installs can join the network when online. This is the only phase
   that touches the network design and is co-owned with
   [`90-network-contract-architecture.md`](90-network-contract-architecture.md).

See [`99-roadmap.md`](99-roadmap.md) for how these phases slot into the broader
program.

---

## Open design questions

1. **Which shell technology?** pywebview (reuse Python) vs Tauri (smallest
   binary + native auto-update) vs Electron (most portable). Recommendation:
   pywebview first; revisit Tauri if size / signing / auto-update dominate.
2. **Auto-update.** How are new portal builds (the static JS + Python host)
   delivered and applied without disturbing the local MOS? Tauri has this
   built-in; pywebview/Electron need an updater.
3. **Key storage on desktop.** Where do AWS/SES credentials and any signing keys
   live on a desktop install — OS keychain vs encrypted file — given there is no
   IAM instance role? Many cloud peripherals may simply be **disabled** on
   desktop and gated behind connectivity.
4. **Sync between desktop installs via contracts.** What is the conflict model
   when two installs mutate `foreign`-mirrored documents? Is the contract the
   sole authority for the shared slice, with each install authoritative only for
   its `origin='local'` rows? This is the crux of
   [`90-network-contract-architecture.md`](90-network-contract-architecture.md).
5. **Directory-existence validation.** `__post_init__` requires dirs to
   pre-exist; should the desktop path relax this, or should the bootstrap always
   create them first (current proposal favors the latter to keep the server
   contract intact)?
6. **Loopback security.** Binding `create_app()` to `127.0.0.1` on an ephemeral
   port, plus an origin/token check, so no other local process can drive the
   host.

---

## Acceptance

This design-spec is satisfied when:

- [ ] Every **Current reality** claim is traceable to the cited `path:line`
      (SQLite per-instance authority, self-materializing schema, per-path
      adapter cache, `config or from_env()` host, ports `forbidden_dependencies`,
      `origin`/`msn_id` seam).
- [ ] The desktop packaging approach is described as a **proposal** with at least
      one concrete recommended shell and the trade-offs of alternatives.
- [ ] The fields a desktop bootstrap must set on `V2PortalHostConfig` are
      enumerated, including the `__post_init__` directory-existence caveat.
- [ ] The migration path is phased so that no early phase changes live-server
      behavior, and the network phase is explicitly deferred to
      [`90-network-contract-architecture.md`](90-network-contract-architecture.md).
- [ ] Open questions name the real unknowns (shell tech, auto-update, key
      storage, cross-install sync) rather than implementation trivia.

---

*Forward references:*
[`20-l2-surface-persistence.md`](20-l2-surface-persistence.md) ·
[`90-network-contract-architecture.md`](90-network-contract-architecture.md) ·
[`99-roadmap.md`](99-roadmap.md)
