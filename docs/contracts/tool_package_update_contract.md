# The tool-package update contract

**Status: as-built for the transport, design-spec for what rides it.** The payload, the
publisher's door, the instance's pull and the ledger's judgment (§ The transport) shipped on
2026-09-25 and are pinned there. What a package FILE is and how it is signed (§ The two open
decisions) are still decisions, written down so that what is built does not foreclose them.
This page opened by denying that any of it existed until 2026-09-29, four days after the
transport went live — a canonical page contradicting the tree it describes, which
`test_contract_pages_are_pinned` now refuses.

---

## The claim

An instance that never talks to the network still **holds a contract** with the FND
instance. Being offline is a fact about connectivity, not about membership: an instance that
has not phoned home is not thereby unmanaged, unlicensed, or stale. So "check for updates"
in Utilities has to be answerable whenever the instance is next reachable — including for an
instance that has been offline since it was installed.

Software updating is painful precisely in deployments like that, which is the reason to
write the shape down before there is code with opinions in it.

## What exists now, and why it is enough to build on

| piece | state |
|---|---|
| `micyte.ports.tool_package` — `ToolPackage`, `ToolRequirement`, `ToolPackageSource` | built |
| `LocalPackageSource` — what this build ships | built |
| `available_packages()` — resolves through the SOURCE protocol, not a hardcoded list | built |
| `tool_exposure.installed_packages[<id>] = {version, source}` — what is installed here | built |
| an `official` source that fetches from micyte.com | **not built** |
| a package file that can be side-loaded | **not built** |

The version record is the load-bearing part and it now exists. Before it, "installed" was
derived from `tool_exposure_enabled`, whose default is open — so an instance that had never
installed anything reported every package installed, at no version. An update check needs to
compare *what is held* against *what is offered*, and there was nothing to compare.

## What the contract carries

Deliberately small, and deliberately **pull-only**:

- the instance's **msn** — which instance is asking;
- for each installed package, its **id and version** — read from `installed_packages`;
- the **build** the instance is running.

That is all. Not what it holds, not who uses it, not what its tools have written.

## Why pull-only

A push channel is a remote-execution channel wearing a different name. If the FND instance
can tell an instance to install something, then compromising the FND instance compromises
every instance that trusts it — which is the supply-chain shape `port_binding` names and
that the marketplace's own docstring already refuses one layer down: *an adapter that
arrives able to act because it was merely installed is the shape of a supply-chain problem.*

Pull also happens to be the only design that works for the case this is about. An instance
that is offline cannot be pushed to. One that asks, when it is ready, can always be answered.

## What must NOT be assumed

- **That an offline instance is stale.** It may be running exactly what it should. Absence of
  a check-in is absence of information, and a UI that reports "out of date" from silence is
  reporting its own ignorance as a fact about somebody's software.
- **That an update can be pushed.** See above.
- **That checking is the same as installing.** The check answers "is there a newer version".
  Installing it stays an operator's decision, gated the same way installing anything is —
  `_datum_write_denied` on `install_package`.
- **That a version is a promise about requirements.** A newer package may declare
  requirements the instance cannot meet (a field its anchor does not define, for instance).
  `unmet_requirements` already answers that per-instance and must be consulted at update
  time, not only at first install.

## The transport (built 2026-09-25, TASK-2026-09-16-002 P3b)

The publisher serves its catalogue as a **hashed, versioned payload** and the instance
**pulls** it; nothing else crosses.

- **The payload** — `micyte/tools/_packages_manifest.py`, schema `micyte.packages.manifest.v1`:
  one entry per package = the package's whole declaration (every field the port's
  `ToolPackage` carries) beside the **declaration digest** — the same digest
  `scripts/lock_packages.py` pins (one definition; the script imports it), so a publisher's
  lock says what an instance will compute over what it pulled. The reader rebuilds the
  port's frozen dataclasses by introspection (a field added to the port later rides
  through; the dataclasses' own validation runs on what arrived), **refuses** an entry that
  does not hash to its digest, and marks what it returns `SOURCE_OFFICIAL`.
- **The publisher's door** — `GET /__mss/public/packages` on the FND portal: the running
  build's catalogue, built on request (the catalogue is in memory; no store is read),
  `ETag` = the build, cached 300 s, open CORS like the offering.
- **The instance's pull** — `fnd_app/instances/_shared/runtime/package_update_transport.py`:
  `pull_official_packages` authorizes FIRST under the instance-network binding, the
  instance service and the operation `packages.pull` (a denial is a denial, never a
  delivery failure), caps the response, validates it through the reader BEFORE caching it
  at `<private>/utilities/packages/official.manifest.json`. `POST /portal/api/v2/packages/pull`
  is the route; the publisher is the network's authority, reached at the endpoint its own
  card publishes; the publisher itself has nothing to pull.
- **The ledger judged against it** — `install_status` / `check_updates` take `source=`;
  every row says `offered_by` and `in_this_build`. The Apps shelf reads the cached official
  source when one was pulled (a render costs no egress) and offers *Update to X* only when
  this build carries X; otherwise it says *X offered by the publisher — update the micyte
  package first*, because the code of a gadget ships with the `micyte` package and a
  version this build lacks is a fact about that package, not about the ledger.

This answers open decision 1 below in the only way the port allowed: **a package "file" is
its declaration**, and the code is the `micyte` release. Decision 2 (signing) stays open;
the digest proves integrity against the publisher's lock, not authorship.

## The two open decisions

Both are genuinely undecided, and neither is blocked by anything built so far.

### 1. What a package FILE is

The operator's ask includes downloading a package from the website and side-loading it into
an offline instance. That needs a file format, and the format question is really two:

- a package that carries only a **manifest** (ids, versions, requirements) is easy and
  nearly useless — the tools it names must already be in the build, so it can enable things
  but never add them;
- a package that carries **code** is the useful one and cannot ship without a signing story.

### 2. The signing story

An instance that will execute code from a file is an instance whose trust boundary is that
file. Before a parser is written, this needs an answer to: who signs, what does the instance
verify against, and what happens when verification fails on an instance with no network to
ask about it.

**Writing the parser first would be building the half that cannot be made safe on its own.**
That is why `available_packages()` wires the seam and stops there: an `official` or
file-backed source drops in beside `LocalPackageSource` and nothing downstream changes,
whenever these two are answered.
