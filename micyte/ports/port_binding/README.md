# Port bindings

## The distinction this exists to hold

A **port** is a contract. [`module_contract.md`](../module_contract.md) says a port owns
"inward-facing interface contracts only" — no adapter code, no host composition — and
[`commerce_offering`](../commerce_offering/) is the worked example: a Protocol, no
implementation, no state, no identity, nothing to configure.

A **binding** is a statement that on *this* instance, that port is filled by *that*
adapter, may write *these* documents, and may make *those* calls.

Keeping them apart is what stops a seam from becoming a service. The moment a port holds
credentials and an actor, it is no longer a declaration of shape — it is a thing that
runs, and the reason `micyte/` can stay `pyyaml` + `shapely` disappears with it.

## A binding is an actor, and it ships denied

`port:<binding_id>`, in the same namespace as `operator:`, `grantee:` and `automation:`,
so one grant list covers every writer on the instance and no adapter can be read as the
person who installed it.

It derives no grant. Nothing in the catalog says which farm a payment adapter belongs to
or whose money it may move, so the only honest source is an operator writing it down. An
adapter that can act because it was merely installed is the shape of a supply-chain
problem.

## The declaration is the request

`writes` and `calls` are not labels. `declared_write_requests` / `declared_call_requests`
build the authorization requests **out of them**, and the Utilities > Ports surface shows
the result of running those through the real `require_datum_write` /
`require_external_call`. The surface is not allowed to compute permission its own way: a
surface that does will one day disagree with the gate, and be believed.

## What is refused

- **No sandboxes.** A binding acting for whichever sandbox it is handed is how a sale
  lands on the wrong farm's books, with nobody watching.
- **`*` as a sandbox.** That is a grant value. A request carrying one would satisfy every
  narrowed grant it met.
- **Neither writes nor calls.** Not a safe default — an unfinished sentence, and a row on
  the operator's surface that means nothing.
- **The same binding id twice.** Two rows disagreeing about what one actor may do, with
  no rule saying which wins.
