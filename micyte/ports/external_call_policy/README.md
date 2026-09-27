# External call policy

The sibling of [`../datum_write_policy/`](../datum_write_policy/), for the other
direction. That one governs what a caller may write into this instance's documents;
this governs what it may say to somebody else's service.

## Why they are two policies and not one

They share an actor namespace on purpose — `operator:<instance>`, `grantee:<msn>`,
`automation:<routine>`, `port:<binding>` mean the same thing to both — but a grant to
edit a farm's offering is not a grant to charge a card. Merging them would mean the
narrowest useful statement an operator could write ("this binding may read the
provider's catalog and nothing else") had no way to be written at all.

## Why the permission is here and the calling is not

`micyte/pyproject.toml` is exactly `pyyaml` + `shapely`. No HTTP client, no OAuth
library and no payment SDK may enter the platform for an opt-in feature, so the call
itself belongs to the host, beside the credentials it needs. What belongs here is the
question — the same split as `require_cipher`, where micyte declares the shape and the
deployment supplies the cipher.

## The rules

- **Deny on an empty grant set.** There is no `grants=None` meaning unrestricted. A
  permission system that opens when its configuration is missing has the posture of one
  that is off.
- **`ANY` is a grant value.** A *request* carrying one is refused outright, or an
  unscoped call would satisfy every narrowed grant it met.
- **Operations are named, not implied by the service.** `order.capture` is grantable
  separately from `order.create` because the first moves money.
- **A denial is raised, never returned as an empty result.** Two of the first call sites
  this governs already swallow errors into `[]` and `None`, and an empty webhook list
  reads as "none are configured" — which is the answer that gets a second one created.

## Where it is enforced

`fnd_app/instances/_shared/runtime/external_call_authorization.py` resolves the actor
and its grants; `test_external_call_policy_is_enforced.py` asserts no outbound call
site slips past it.
