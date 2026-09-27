# 91 — Channels

> Status: as-built
>
> [← Overview](00-overview-and-glossary.md)

## The third member of the component taxonomy

Three kinds of component, told apart by **who engages them**:

| component | engaged by | writes? |
|---|---|---|
| a **tool** ([`micyte/tools/`](../../micyte/tools/)) | the operator, against their own data | via the datum path |
| a **routine** ([`micyte/automation/`](../../micyte/automation/)) | nobody — it runs unattended | yes, that is its job |
| a **channel** ([`micyte/channels/`](../../micyte/channels/)) | **the outside world** | **no** |

A channel is a session surface the outside engages — **open** (any caller) or **closed**
(contract-holding instances) — terminating at a sandbox this instance hosts for it.

The register enforces the taxonomy **both ways**: a tool or routine landing in the channel
register is refused, and the mirror refusals live in `micyte.tools.register` and
`micyte.automation.register`. A component cannot be two of these by being registered twice.

## A channel is panel-shaped, and that is deliberate

A channel implements `build_panel_payload` — the same call shape as a tool — so the
operator views their own channel through the same overlay the palette already opens.

**The internal rendering and the public session serve one payload from one builder**, so
the two cannot drift. The alternative — a public renderer beside an operator preview — is
how a channel comes to look correct to the person who runs it and wrong to everyone else.

## What a channel is NOT

- **Not routed.** It carries no `route` and no surface id. Engagement happens from the
  interface search and the rail's channel section, never a bookmark.
- **Not a writer.** A channel declares no writes, and the open session routes are GET-only
  *by construction*. The reason is identity: an anonymous request resolves to the operator
  identity, so "no write path exists" is the only safe posture. A channel that could write
  would be writing as the operator on a stranger's request.

## The standing trap: growing the Protocol

The channel Protocol is `runtime_checkable` and `register` isinstance-checks it. So **a
new attribute added to the Protocol later un-registers every channel that lacks it** —
silently, because failing an isinstance check is not an error, it is a `False`.

Grow the contract with `getattr` defaults, never with new Protocol members. The same trap
and the same rule apply to tools: see `micyte/tools/_contract.py`.

## The two channels today

**`agnet`** ([`micyte/channels/agnet.py`](../../micyte/channels/agnet.py)) — a market.
Tabs are `supply`, `demand`, `taxonomy`, `profiles`, and the taxonomy tab is built **only
when it is asked for**: 4,096 nodes is a quarter of a megabyte and the viewer refetches the
whole session on every day pick, so every other request returns `{"loaded": false}` rather than an empty
section that reads like an empty tree.

Two things it derives rather than declares, both worth copying:

- A taxon is marked `traded` because a **product resolves to it** — never because the
  taxonomy document says so. The marks are a fact about the market's catalogue, which is
  why the tree belongs to a channel rather than to a website.
- The profiles tab splits entities into **instances** and **records**: an entity either
  has an instance to reach for its own information, or it is a profile the registrar keeps
  about it. Reachability is derived from contracts, never probed — a session builder that
  opened sockets would make rendering a page depend on the network.

**`grantor`** ([`micyte/channels/grantor.py`](../../micyte/channels/grantor.py)) — the
paid-service surface: which services an alias has, and the key that enables a port. See
[`92-ports-as-four-layers.md`](92-ports-as-four-layers.md).

## See also

- [`90-network-contract-architecture.md`](90-network-contract-architecture.md) — contracts, keys, the registry
- [`92-ports-as-four-layers.md`](92-ports-as-four-layers.md) — what an enabled service connects to
