# Portal Authority Port

Authority: [../../../../docs/plans/master_plan_mos.md](../../../../docs/plans/master_plan_mos.md)

`packages/ports/portal_authority/` owns the bounded portal-grants and tool-exposure
read seam for the MOS SQL core cutover.

Implemented in this phase:

- portal-scope capability grants
- ownership posture metadata
- tool exposure/configuration policy payloads
- adapter-neutral read protocol for runtime composition

Not implemented in this phase:

- grant mutation workflows
- identity hashing or hyphae semantics
- directive-context widening
- runtime shell composition rules
