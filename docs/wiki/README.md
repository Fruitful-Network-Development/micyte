# Wiki Docs

## Purpose

`docs/wiki/` holds explanatory orientation material.

These docs help readers understand:

- cross-repo separation
- responsibility assignment
- how documentation families fit together

They are not the place for normative contracts or execution backlogs.

## Canonical Use

Use wiki docs when a reader needs a stable explanation before they dive into
contracts, plans, or code-adjacent package docs.

Current pages:

- [`separation_and_responsibility.md`](separation_and_responsibility.md)

## Relationship To Other Doc Families

- `docs/contracts/` is normative
- `docs/plans/` is execution and backlog
- `docs/audits/` is evidence and review
- `docs/personal_notes/` is preserved source material
- `MyCiteV2/**/README.md` and related package docs are code-adjacent bounded-scope docs

If a wiki page starts making normative claims, promote that content into a
contract and leave the wiki page as orientation and cross-reference.
