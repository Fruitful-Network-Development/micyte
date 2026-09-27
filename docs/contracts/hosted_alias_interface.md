# Hosted alias interfaces

## Status

Canonical, as built (channels LIVE since 2026-08-02, alias documents since 2026-08-21;
page written 2026-09-17, TASK-2026-09-16-002 P5). Pinned by
`fnd_app/tests/architecture/test_contract_pages_are_pinned.py`.

## Purpose

A channel is a relationship with two halves: the HOST keeps one roster row per member,
and each MEMBER keeps an alias document whose rows are references to datums it already
holds. This page fixes the names, the addresses and the postures so an instance built
from the public package hosts and joins channels the way FND's does.

## A channel is a base msn-profile value

The host's registrar `channels` document carries one row per channel at `4-1-N`:
`rf.3-1-2` the channel's msn, `rf.3-1-3` its id, `rf.3-1-14` its access — `public` or
`private`. `build_profile` picks it up with no code change; the channel register
(`micyte/channels/`) is the third register beside tools and automation, mutually
exclusive with them, and declares no routes and no writes.

## The alias document

`lv.<member_msn>.system.<channel>-<host_msn>.<hash>` — minted header-first by
`fnd_app/scripts/seed_channel_alias_documents.py`; reference rows are the network
program's later work. A declared-empty alias is a real answer: the profile page's alias
gallery is a data fact, not a hardcode. The pairing rule per channel: a roster keyed by
INSTANCE msn pairs directly; the grantor's roster keys the client's GRANTEE msn, and an
instance msn is not a grantee msn — a client has two addresses.

## Postures

* **Open routes are read-only by construction.** `/__channel/` is GET-only; no write
  route exists under it, because a header-less request resolves to the operator identity
  with an every-sandbox grant, and "no write path exists" cannot be wrong the way
  "authorize then deny" can.
* A closed or disabled channel answers 404, not 403.
* `/portal/api/channels` is the authenticated twin for the operator's own portal.
* **Private** channels are visible on the host's page grayed for the host (the host has
  no alias of its own) and readable by members through their contract; **public**
  channels serve their session payload to anyone.

## Implementations

`micyte/channels/agnet.py` (the network's own channel), `micyte/channels/grantor.py`
(FND's grantor channel: per-grantee service rows, admin/grantee postures, the key block),
`micyte/channels/convention.py` (the cooperation convention the two share).
