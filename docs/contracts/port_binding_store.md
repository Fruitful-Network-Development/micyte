# The binding store — `private/config.json`

## Status

Canonical (2026-09-17, TASK-2026-09-16-002 P5). Pinned by
`fnd_app/tests/unit/test_config_schema.py`, which holds the e2e harness's config and FND's
live one to `fnd_app/instances/_shared/runtime/private_config_schema.py`.

## Purpose

An instance's `private/config.json` is where its port bindings, grants, namespace claims,
install ledger and hosting posture live — the four layers of `docs/wiki/92-ports-as-four-layers.md`
(type / extension / binding / grant) made durable, plus what the instance has installed
and how it is hosted. The portal parses it at boot. It had no stated shape: on 2026-09-17
FND's held fifteen keys, thirty-odd hand-stamped `.bak` copies sat beside it, and
seventeen scripts each backed it up their own way.

## Keys

| key | holds |
|---|---|
| `msn_id` | the instance's msn |
| `private_key_ref` | `vault://` reference to the signing key (`instance_keys.py`) |
| `installed_packages` | `package_id -> {version, source, archetypes?, installs?}` — the ledger `check_updates` reads; `archetypes` are the library hashes the version was installed against |
| `tool_exposure` | `tool_id -> {enabled}`; absent means enabled (exposure is not authorization) |
| `port_bindings` | one entry per binding: `binding_id`, `port_id`, `adapter_id`, `msn_id`, `sandbox_ids`, `calls` (`{operation, service}` from the extension's declared functions, never typed), `label` |
| `datum_write_grants` | `{actor_id, actions}` — every actor ships denied |
| `external_call_grants` | `{actor_id, binding_ids}` |
| `sandbox_namespaces` | `msn -> {sandbox -> namespace}` — the namespace claims an app install records |
| `hosted` | `hosting_type`, `member_exposed`, `pages`, and `door` (the hosted sign-in) |
| `aliases`, `contracts`, `references`, `request_log`, `resources`, `tools_configuration` | lists the channel, contract, publication and tools programs keep |

A key this table does not name is reported by the validator, not ignored: an unknown key
in the file the host parses at boot is a fact somebody should hear before the boot.

## Rules

* **One writer discipline.** Read-modify-write of the whole file, written through a temp
  file and `os.replace` (`package_install_runtime._write_exposure` is the model): a bare
  `write_text` truncates first, and a crash between truncate and flush empties the file
  the host boots from.
* **One backup namer.** A script that changes this file backs it up through
  `fnd_app/scripts/_authority_backup.stamped_backup_path` (`config.json`, slug of the act),
  which disambiguates a same-second stamp. Seventeen scripts predate the rule and name
  their backups by hand — debt named in the fix report, retired as each is next touched.
* **Validate before writing.** `private_config_schema.validate(config)` returns every
  problem as a sentence; a writer that would leave the file invalid refuses.
* Grants are not bindings: a binding says an adapter MAY be called; a grant says WHO may
  call it (`92-ports-as-four-layers.md` §4). Neither is written by installing a package.
