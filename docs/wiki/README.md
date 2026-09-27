# Wiki Docs

> Status: index
>
> The index of pages is [`00-overview-and-glossary.md`](00-overview-and-glossary.md).
> This file says what the wiki family is FOR. It deliberately does not list the pages:
> it used to, and the list said "Current pages: separation_and_responsibility.md" —
> one of seventeen — because a list spelled twice is free to drift from itself.
> `test_wiki_is_combed.py` now holds both halves of that: the overview and the
> directory must cover each other exactly, and this file must not restate them.

## Purpose

`docs/wiki/` holds explanatory orientation material.

These docs help readers understand:

- cross-repo separation
- responsibility assignment
- how documentation families fit together

They are not the place for normative contracts or execution backlogs.

## Canonical Use

Use wiki docs when a reader needs a stable explanation before they dive into
contracts or code-adjacent package docs.

Start at [`00-overview-and-glossary.md`](00-overview-and-glossary.md), which
indexes every page and carries the glossary.

## Every Page Declares Its Status

A page says what kind of claim it is making, in a `> Status:` line under the title:

| Status | The claim | Rots when |
|---|---|---|
| `as-built` | the code looks like this **today** | anything it describes is refactored |
| `design-spec` | this is the intended shape, not necessarily the built one | the design is superseded |
| `how-to` | follow these steps and they will work | a step's script or route is retired |
| `index` | this page is a map of other pages | a page is added or removed |
| `stale` | **known wrong in a named way**, kept for what is still true | it is rewritten |

`as-built` and `how-to` are the two that rot silently, because both assert something
about code that is free to move underneath them. That is why the gate exists.

## Relationship To Other Doc Families

- [`docs/contracts/`](../contracts/) is normative
- [`docs/standards/`](../standards/) defines authoring rules
- `fnd_app/**/README.md` and related package docs are code-adjacent bounded-scope docs

This list named five families until 2026-08-23, and three of them did not exist:
`docs/plans/` and `docs/audits/` are not in this repo, and `docs/personal_notes/`
was deleted in the 2026-07-17 public/private split (`d30c6e55`) — while
`docs/standards/`, which does exist, went unmentioned. Execution backlogs and
evidence live under the agentic tree now, not under `docs/`.

If a wiki page starts making normative claims, promote that content into a
contract and leave the wiki page as orientation and cross-reference.
