# MiCyte

A datum operating environment: a local MOS database, and an address on a shared
network.

MiCyte stores what a farm actually has to track — fields, plantings, contracts,
inventory, the people it sells to — as structured records on a machine you
control. There is no account to create and no server to depend on. The database
is a file on your disk.

Records are addressed, not filed. Each carries a canonical name that says who
owns it, which part of the farm it belongs to, and the exact version you are
looking at:

```
lv.<msn_id>.<sandbox>.<name>.<version>
```

Because the version is a content hash, a record cannot be quietly edited out from
under a reference to it — the property that lets two installs exchange data
without trusting each other's spreadsheets.

## The network

An `msn_id` is a path, and each segment is only meaningful inside the one before
it — the way `uk` and `com` organise different worlds beneath them. You do not
read the segments; you resolve them. A single registry answers "what is at this
address" and "what address is this install," the way DNS answers what is at a
name. What it never receives is your records. Listing puts an install on the map;
it does not move the data off your machine.

## Status

**0.1.0 — alpha.** MiCyte installs as a **library**: the MOS database and its
tools, importable as `micyte`. There is no installer, no desktop app, and no
`micyte` command yet; the design for running it as a local app is written down
(`docs/wiki/95-desktop-app-local-db.md`) and not yet built. An install cannot
report itself to a registry yet either — addresses resolve, but only inside a
deployment.

You can read every line of what would run on your machine. That is the point.

## Install

```
pip install micyte
```

Not on PyPI yet — install the wheel from the
[latest release](https://github.com/Fruitful-Network-Development/micyte/releases).
Requires Python 3.13. Two dependencies, both load-bearing: `pyyaml` (the document
transport format) and `shapely` (the geometry engine behind plot packing).

```python
import micyte
```

## What this repository is

This is **MiCyte**, the standalone software. Fruitful Network Development runs a
grantee-services application on top of it; that application is a downstream
consumer and lives elsewhere. The dependency runs one way — an application may
depend on MiCyte; MiCyte depends on no application.

## Docs

- [`docs/wiki/00-overview-and-glossary.md`](docs/wiki/00-overview-and-glossary.md) — the vocabulary (hyphae, filament, sandbox, MOS) in one place.
- [`docs/contracts/datum_document_naming_taxonomy.md`](docs/contracts/datum_document_naming_taxonomy.md) — what an address means, and why the version hash is part of the name.
- [`docs/wiki/90-network-contract-architecture.md`](docs/wiki/90-network-contract-architecture.md) — how two installs agree to exchange anything at all.
- [`docs/wiki/95-desktop-app-local-db.md`](docs/wiki/95-desktop-app-local-db.md) — the design for running MiCyte on your own machine.

## License

AGPL-3.0-or-later. See [`LICENSE`](LICENSE). Built by
[Fruitful Network Development](https://fruitfulnetworkdevelopment.com) in
Northeast Ohio.
