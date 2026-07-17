# Documentation Style Guide

## Purpose

Define a consistent documentation information architecture so normative content is canonical, non-duplicative, and auditable.

## Scope

Applies to active documents in `docs/contracts`, `docs/audits`, and `docs/plans`.

## Lifecycle Metadata

Every active audit/plan document should include a metadata block near the top:

- `Doc type`: `contract`, `audit`, `plan`, or `notes`
- `Normativity`: `canonical`, `supporting`, or `historical`
- `Lifecycle`: `active`, `compatibility`, `deprecated`, or `archived`
- `Last reviewed`: ISO date (`YYYY-MM-DD`)

## Required Sections (Audits/Plans)

Active `audit` and `plan` documents must include:

1. `## Purpose`
2. `## Scope`
3. `## Canonical Contract Links`

Recommended additional sections:

- `## Rationale`
- `## Risks`
- `## Validation / Evidence`
- `## Exit Criteria`

## Canonical Contract Links

Normative claims (`must`, `required`, `canonical`) must link to canonical contracts rather than duplicating contract text.

Minimum link block:

```markdown
## Canonical Contract Links
- portal shell contract: `docs/contracts/portal_shell_contract.md`
- route model: `docs/contracts/route_model.md`
- surface catalog: `docs/contracts/surface_catalog.md`
- vocabulary glossary: `docs/contracts/portal_vocabulary_glossary.md`
```

## Redundancy Rules

- Do not duplicate contract semantics in audits/plans.
- Reference contract section headings for normative behavior.
- Keep implementation guidance in plans and verification/evidence in audits.

## Terminology Rules

- Prefer canonical terms from `docs/contracts/portal_vocabulary_glossary.md`.
- Legacy aliases must be explicitly marked as compatibility-only.
- Deprecated terms should include a replacement term in the same section.

