# Agent YAML Schema Standard (v1)

## Purpose

Define a machine-parseable schema for guided agent tasks with explicit ownership, dependencies, outputs, acceptance criteria, and evidence mapping.

## Canonical Contract Links

- portal shell contract: `docs/contracts/portal_shell_contract.md`
- route model: `docs/contracts/route_model.md`
- surface catalog: `docs/contracts/surface_catalog.md`
- vocabulary glossary: `docs/contracts/portal_vocabulary_glossary.md`

## Required Structure

```yaml
schema_version: "1.0"
kind: "agent_task"

task:
  id: "<string>"
  title: "<string>"
  summary: "<string>"
  owner:
    role: "<string>"
    team: "<string-or-null>"
  status: "planned|in_progress|blocked|done"
  priority: "p0|p1|p2|p3"
  lifecycle: "active|compatibility|deprecated|archived"
  tags: ["<string>"]
  relates_to:
    contracts:
      - doc: "docs/contracts/<file>.md"
        section: "<section-or-anchor>"
  dependencies:
    hard: ["<task-id>"]
    soft: ["<task-id>"]
  inputs:
    - path: "<repo-relative-path>"
      type: "markdown|yaml|json|log|image"
  outputs:
    - path: "<repo-relative-path>"
      type: "markdown|yaml|json|log|image"
      required: true

acceptance:
  criteria:
    - id: "AC-<n>"
      statement: "<testable assertion>"
      validation:
        gate: "schema|contracts|terminology|evidence|custom"
        method: "<executable-check-or-procedure>"
      evidence_ids: ["EV-<n>"]

evidence:
  root: "docs/audits/evidence"
  artifacts:
    - id: "EV-<n>"
      path: "<repo-relative-path>"
      type: "markdown|yaml|json|log|image"
      producer: "agent|validator|human"
      immutable: true

validation_gates:
  - id: "VG-1"
    name: "schema_validation"
    required: true
  - id: "VG-2"
    name: "contract_link_validation"
    required: true
  - id: "VG-3"
    name: "acceptance_to_evidence_mapping"
    required: true
```

## Validation Rules

1. `task.id` is globally unique.
2. `acceptance.criteria[].id` is unique within the task file.
3. Each acceptance criterion has at least one `evidence_ids` entry.
4. Every evidence ID referenced by acceptance criteria exists in `evidence.artifacts`.
5. Every contract reference path exists and points under `docs/contracts/`.
6. Hard dependency graph is acyclic.

