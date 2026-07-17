# Audit Log Port

Authority: [../../../../docs/plans/v2-authority_stack.md](../../../../docs/plans/v2-authority_stack.md)

`packages/ports/audit_log/` owns the MVP audit-log seam only.

Implemented in this phase:

- append contract for one already-normalized audit record
- read contract for one previously persisted audit record by opaque identifier
- adapter-neutral audit-log port protocol

Not implemented in this phase:

- local-audit semantic rules
- redaction policy
- filesystem layout or naming policy
- runtime composition behavior
- query, filtering, or indexing APIs
