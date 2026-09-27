"""Cryptographic PORTS — the shapes verification and sealing take, not their impls.

micyte's dependency list is ``pyyaml`` + ``shapely``. So this package declares what
a signature check and a sealed channel *are*, and an FND-side peripheral supplies
the ``cryptography``-backed implementation. A lone-laptop install that never engages
a closed channel pays nothing for either.

* :mod:`micyte.core.crypto.signature` — request signature verification port.
* :mod:`micyte.core.crypto.channel` — cipher / sealed-channel shape.

The package namespace stays empty on purpose: importing ``micyte.core.crypto`` must
not drag a port in. Import the module you want.

This line read "Inert package scaffold." for months after the modules beside it were
built and imported by live code, and the wiki censused the package by reading it
(``docs/wiki/99-roadmap.md``, Track 3). If the package grows again, grow this with it.
"""
