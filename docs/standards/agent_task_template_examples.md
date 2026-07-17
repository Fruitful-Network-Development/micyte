# Agent Task Template Examples

## Purpose

Provide copy-ready templates for guided task YAML that satisfies the schema in `docs/standards/agent_yaml_schema.md`.

## Example A: Task Metadata

```yaml
schema_version: "1.0"
kind: "agent_task"

task:
  id: "DOC-AUDIT-001"
  title: "Audit active plan documents for canonical contract links"
  summary: "Ensure active plans include required contract links and lifecycle metadata."
  owner:
    role: "doc-author"
    team: "platform-docs"
  status: "planned"
  priority: "p2"
  lifecycle: "active"
  tags: ["docs", "contracts", "audit"]
  relates_to:
    contracts:
      - doc: "docs/contracts/portal_shell_contract.md"
        section: "Shell Request + Envelope"
  dependencies:
    hard: []
    soft: []
  inputs:
    - path: "docs/plans/README.md"
      type: "markdown"
  outputs:
    - path: "docs/audits/reports/documentation_ia_audit_report_2026-04-20.md"
      type: "markdown"
      required: true
```

## Example B: Acceptance + Evidence

```yaml
acceptance:
  criteria:
    - id: "AC-1"
      statement: "All active plan documents include Canonical Contract Links."
      validation:
        gate: "contracts"
        method: "text check for required section header and required contract paths"
      evidence_ids: ["EV-1"]
    - id: "AC-2"
      statement: "Every normative claim in the report links to a contract."
      validation:
        gate: "terminology"
        method: "manual review with checklist"
      evidence_ids: ["EV-2"]

evidence:
  root: "docs/audits/evidence"
  artifacts:
    - id: "EV-1"
      path: "docs/audits/evidence/DOC-AUDIT-001/summary.md"
      type: "markdown"
      producer: "agent"
      immutable: true
    - id: "EV-2"
      path: "docs/audits/evidence/DOC-AUDIT-001/validation.log"
      type: "log"
      producer: "validator"
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

