# 93 — The Marketplace

> Status: as-built
>
> [← Overview](00-overview-and-glossary.md)

What a package is, where the catalogue's truth lives, and how micyte.com shows it
without holding a second copy. For what a package may DO once installed, read
[`92-ports-as-four-layers.md`](92-ports-as-four-layers.md): installing is layer 2 of
four, and the two that decide whether anything may act are separate writes.

## A package is declared, not derived

It would be possible to synthesise one package per registered tool. That would be
worse. `handyman_erp` is three tools and four documents that only make sense
together, and a catalogue offering them separately would let an operator install a
jobs table with no contact list to book against. **A package is a decision about what
ships together, so it is written down** —
[`micyte/tools/_packages.py`](../../micyte/tools/_packages.py).

What a package *requires* and *writes* is NOT written down there. `_package()`
derives both from the tools it names, via `requirements_for` and `declared_writes` in
[`micyte/tools/_registry.py`](../../micyte/tools/_registry.py). A package carrying its
own copy of what its tools require would be a second statement of the same fact, free
to drift from the first.

Two kinds, and the difference is declared rather than inferred:

| | ships | declares | constructor |
|---|---|---|---|
| **package** | tools, and the documents they need | — | `_package()` |
| **extension** | nothing | the port it fills (`PortFill`) | `_extension()` |

"Ships no tools" is therefore something an extension SAYS, not something a reader
concludes from an empty tuple. The two tabs on micyte.com are that same split.

## Installing grants nothing

The single most important property, and the one a marketplace gets wrong:

> An adapter that arrives able to act because it was merely installed is the shape of
> a supply-chain problem.

An install does exactly two things
([`package_install_runtime.py`](../../fnd_app/instances/_shared/runtime/package_install_runtime.py)):

1. writes `tool_exposure`, so the instance SHOWS the tool — a presentation control
   whose documented default is open, because *exposure is not authorization*;
2. provisions what the tool declared it needs — the `sources` rows it reads and the
   blank documents it holds.

It touches no grant. What a tool may write is decided by
`micyte.ports.datum_write_policy`, which denies on an empty grant set. **Uninstalling
never deletes data**: it sets exposure false. A marketplace that could delete a job
log by being clicked twice is one nobody should install anything from.

Provisioning is load-bearing, not decorative: a core tool is offered only when the
instance holds the documents its `requires` declares, so an install that writes
`tool_exposure` and stops yields a tool that never appears and never errors.
`unmet_requirements()` computes that missing set, and the same function backs both the
install and the preview — so a preview cannot promise an install the runtime refuses.

## Where the catalogue's truth lives, and how the website gets it

`_packages.py` names micyte.com the **authority** that publishes packages; the module
itself is the LOCAL source, the catalogue of what the build in front of you already
contains. A package from there installs and runs. That distinction is the seam a
network fetch fills later: an `official` source implementing `ToolPackageSource`
returns packages fetched from micyte.com, and the requirement preview, the install and
the ledger are unchanged, because they already work from the port's types rather than
from where they came from.

The website does **not** import any of this. Deploying a client website may not
require this repo to be present, importable or healthy — the site/portal isolation
boundary, enforced by `deploy_sites.sh` in the webapps repo. So the catalogue is
*published*, the same seam the map and calendar already use:

```
micyte/tools/_packages.py                     the declaration
  └─ fnd_app/scripts/export_micyte_package_catalog.py   --write
       └─ micyte.com/frontend/assets/micyte-packages.manifest.json
            └─ gen_marketplace.py            (in the webapps repo)
                 └─ resources.html                (between GEN markers)
```

Nothing about a package is typed twice along that chain: not its name, version,
summary, tool list, or the number of documents it provisions. Add or retire a package
in `_packages.py`, re-run the exporter, re-run the generator. A pre-commit hook in that repo
runs the generator's `--check`, so a stale page cannot be committed.

`provisions` reaches the page as a COUNT, never the document names. The number answers
what a reader is asking — *how much does this touch?* — and naming them would publish
the shape of an instance's storage to anyone who loads the page.

## The page renders without JavaScript

The marketplace is HTML, in the bytes nginx serves, not a list the browser fetches.
That is a requirement, not a preference: before it was rebuilt, `/resources` gave a
reader without JavaScript 529 characters of its 5,591 — one empty well and a noscript
note — because its tabs were `<button>`s and its panels carried a static `hidden`.

The pattern, which the rest of the site now follows:

- Tabs are **links to sections that are visible by default**. With no script the page
  is a table of contents over its whole content.
- The markup does not claim tab semantics. JavaScript adds `role="tablist"`, the
  selection state and the hiding when it runs, because announcing controls that
  nothing implements is worse than announcing none.
- Panels are **discovered** from the markup (`data-panel`), never hand-listed in the
  script — a hand-written map is a second list of the same sections, and a tab added
  without remembering to update it shows a pressed button that changes nothing.

The same rule sends the map's readers somewhere real: `/explore` genuinely needs a
script, so <https://micyte.com/directory> renders the registry's 179 entities as a
plain page, generated from the same feed the map reads. (That page lives in the
webapps repo, not this one — see
[`separation_and_responsibility.md`](separation_and_responsibility.md).)

## What is not built yet

- **A network source.** `LocalPackageSource` is the only implementation; nothing
  fetches from micyte.com. The port exists so that it can, without the ledger,
  preview or install changing.
- **Side-loading a package file offline**, and the update contract an offline
  instance would check against. Deliberately not built; see
  [`99-roadmap.md`](99-roadmap.md).
- **Accounts.** `/login` says so rather than presenting a form that goes nowhere.
