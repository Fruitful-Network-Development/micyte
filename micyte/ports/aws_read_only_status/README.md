# AWS Read-Only Status Port

Authority: [../../../../docs/plans/v2-authority_stack.md](../../../../docs/plans/v2-authority_stack.md)

`packages/ports/aws_read_only_status/` defines the narrow read-only seam for the first AWS operational visibility slice.

Implemented in this slice:

- one explicit request contract for tenant-scoped AWS operational status reads
- one explicit source-payload result contract
- one read-only protocol with no write behavior

Not implemented in this slice:

- provisioning or profile-update writes
- raw provider object pass-through
- secret-bearing payload fields
- broader provider-admin or multi-provider seams
