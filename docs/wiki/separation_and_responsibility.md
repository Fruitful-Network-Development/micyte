# Separation And Responsibility

## Purpose

Explain how MiCyte fits with the host-infrastructure layer, the served-assets
tree, and the mutable per-instance state root of a deployment, so documentation
and implementation changes can land in the right place.

## Core Rule

`mycite-core` is the authority and mediation kernel.

It owns:

- portal authority and capability semantics
- runtime/tool contracts
- cross-domain mediation logic
- SQL-backed authority posture
- narrow audited write seams when explicitly approved

It does not own:

- host ingress or container topology
- Keycloak deployment posture
- Docker/compose operational truth
- hosted frontend assets as a source corpus
- mutable live state as an authored repo surface

## Related Repos And Roots

### `srv-infra`

Owns host/runtime topology and deployment operations:

- NGINX
- `systemd`
- Docker and compose posture
- Keycloak, oauth2-proxy, Redis, and intentional host containers
- deploy/smoke/promote workflows

### the webapps deployment tree

Owns hosted frontend assets plus analytics corpora.

`mycite-core` may inspect narrowly documented read paths there, but hosted asset
authoring still belongs to the webapps deployment tree.

### Mutable instance state

A deployment keeps mutable live instance state outside git.

Tool/profile/config/runtime bubbles there are runtime truth, not repo-authored
development documents.

## Peripheral Surfaces

### AWS

Current posture is already close to the target model:

- read-only visibility seam
- narrow internal write seam
- no broad provider-admin ownership inside core

### FND-EBI

FND-EBI should be treated as a peripheral service surface, not as core business
authority.

That means:

- keep profile/analytics visibility explicit
- avoid treating host filesystem layout as implicit application canon
- document the seam as a peer peripheral surface, similar in discipline to AWS

### Keycloak

Keycloak is a host/runtime concern unless and until `mycite-core` exposes a
clear bounded mediation surface for it.

### Docker

Docker is infrastructure posture, not application semantics.

If runtime health or availability is needed inside portal tooling, expose it
through bounded read seams rather than by collapsing infra ownership into core.

## Current Documentation Rule

- contracts define norms
- wiki pages explain assignment
- standards define authoring rules

This keeps the corpus coherent while reducing drift.
