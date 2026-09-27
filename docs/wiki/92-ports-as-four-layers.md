# 92 — Ports as Four Layers

> Status: as-built
>
> [← Overview](00-overview-and-glossary.md)

## The operator's model

Four separate facts, each owned by a different module. Reading them in order is the whole
page:

| # | layer | the question it answers | where |
|---|---|---|---|
| 1 | **TYPE** | which seams *can* exist | [`micyte/ports/port_catalog/contracts.py`](../../micyte/ports/port_catalog/contracts.py) |
| 2 | **EXTENSION** | what is installed that could fill one | [`micyte/ports/tool_package/contracts.py`](../../micyte/ports/tool_package/contracts.py) (`PortFill`) |
| 3 | **BINDING** | which one *this instance chose* | [`micyte/ports/port_binding/contracts.py`](../../micyte/ports/port_binding/contracts.py) |
| 4 | **GRANT** | whether it *may act* | [`micyte/ports/external_call_policy/`](../../micyte/ports/external_call_policy/) |

The layers are separate because the mistakes they prevent are different. Collapsing 3 and
4 in particular is the one to resist — see below.

## 1. TYPE — declared, never derived

`PORT_TYPES` is written down. Deriving it by walking `micyte/ports/*` would put
`datum_write_policy` and `port_binding` in a list of things an operator can bind an adapter
to, and those are not that: **they are the policies a binding is judged BY.**

`NOT_BINDABLE` names every port module deliberately absent, and `test_port_catalog` asserts
the two sets cover the directory **exactly** — so a new port module cannot be quietly
missing from both. That is the egress sweep's rule, *never exclude silently*, applied to a
register instead of to a call site.

Before the register existed, `port_id` was a free string: a typo produced a fully-formed
binding for a seam nothing reads — visible on the Ports surface, permanently inert, and
indistinguishable from a feature that simply does not work.

**Operations come FROM the contracts.** Every `operations` tuple is imported, never
spelled. An operation grain restated in the register would be a second statement of what
the port already says, free to drift from it.

Some ports name no operations of their own, and that is a real distinction rather than an
omission: `commerce_offering`'s egress grain belongs to whatever payment vendor fills it
(`paypal:order.capture`). `PortType.names_its_operations` is the question a validator asks
instead of guessing from emptiness.

## 2. EXTENSION — eligibility is one question with one answer

An extension installs **no tools**, and that is the point: requiring a hub would force
every adapter to ship a screen nobody asked for.

`eligible_fills(port_id, installed)` raises for an unknown port rather than returning
nothing — *"nothing is eligible"* and *"there is no such port"* are different facts, and
only one of them is fixed by installing something.

## 3. BINDING — the declaration IS the request

A binding's `calls` are built **from the extension's declared functions, never from the
form**. A caller who could type the calls could type one the extension does not perform,
and the Ports surface would then show a permitted function that raises at the adapter.

## 4. GRANT — every actor ships denied

This is the one place the two policies deliberately differ.

`datum_write_authorization` *derives* a default: an operator may write every sandbox, a
grantee the sandboxes its own msn owns. That default is a statement about the store, and it
is safe because those documents already belong to those actors.

**There is no equivalent fact about the outside world.** Nothing in this instance's catalog
says which PayPal account an operator may charge, and no reading of the store implies a
right to call somebody else's service. So every actor ships denied and becomes able to call
out only when a human writes `external_call_grants` into `private/config.json`.

The practical consequence, stated plainly because it will be noticed: on an instance with
no such key, the PayPal admin routes **refuse**. That is the designed resting state, not a
misconfiguration. [`fnd_app/scripts/check_external_call_grants.py`](../../fnd_app/scripts/check_external_call_grants.py)
prints the exact block to add.

### The actor names read backwards

The trap that costs the most time, so it gets its own heading:

- `X-Auth-Request-Grantee` resolves to **`grantee:<msn>`** — and nginx **hard-sets that
  header on every dashboard route**. So the *operator console* resolves to
  `grantee:<OPERATOR_MSN_ID>`.
- **`operator:<instance>`** is what an **unauthenticated** request resolves to — an
  anonymous visitor checking out, a provider POSTing a webhook.

A grant written for the wrong one is valid JSON, loads without complaint, matches nothing,
and looks from the operator's side exactly like the feature not working.
[`external_call_authorization.py`](../../fnd_app/instances/_shared/runtime/external_call_authorization.py)
derives the actor per call site for this reason rather than defaulting to one.

## Why binding and granting are separate writes

`port_bindings` says what a seam is FOR; the grant keys say whether it MAY. Keeping them as
separate writes is what lets the two be reviewed separately — and it is why an operator can
read the Ports surface and see a binding **fully described and entirely refused**, which is
the correct resting state for something nobody has approved.

A form that did both would make describing and permitting one gesture, and *the gesture
people make is the permissive one.*

## Connecting a port from the UI

The Ports surface offers two forms
([`fnd_app/instances/_shared/runtime/port_binding_write_runtime.py`](../../fnd_app/instances/_shared/runtime/port_binding_write_runtime.py)):

- **Connect** — select an extension for a port. Layer 3 only.
- **Use** — the same two writes, gated on the **service key the grantee handed back**
  ([`grantor_keys.py`](../../fnd_app/instances/_shared/runtime/grantor_keys.py)).

The key is a **selector, never a credential**. Both routes sit behind the fail-closed
operator gate, and the key authenticates no inbound request — so a stolen key is useful
only to somebody who already holds the gate and therefore did not need it. What it adds is
**evidence the client participated**: without it an operator can type a grantee msn and
configure a seam over the mail of a client who never asked, and nothing in the resulting
files would record that.

Neither form writes a grant.

## See also

- [`91-channels.md`](91-channels.md) — where a paid service is enabled and a key is minted
- [`90-network-contract-architecture.md`](90-network-contract-architecture.md) — the other kind of key: instance-to-instance contracts
