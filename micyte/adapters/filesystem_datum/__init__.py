"""Filesystem-backed MOS datum store — MiCyte's, not FND's.

Sited apart from ``adapters/filesystem/`` deliberately. That package holds FND
grantee-services leaflet adapters (contact, newsletter, campaign, donation,
analytics, AWS) and re-exports all of them from its ``__init__``. Python executes
a package's ``__init__`` before any submodule, so while this adapter lived there,

    from MyCiteV2.packages.adapters.filesystem import FilesystemSystemDatumStoreAdapter

— the one import MiCyte's SQL datum store needs — pulled FND's entire leaflet
surface into MiCyte at import time (measured: 179 modules, 8 of them leaflet
adapters). MiCyte cannot ship as standalone software while its MOS store imports
FND's mailing-list code, so the odd module out moved rather than the other
fourteen.

The split is by product, not by backing technology: both packages are
filesystem-backed, but this one is MiCyte's and that one is FND's. The boundary is
enforced by tests/architecture/test_micyte_fnd_boundary.py.
"""

from .live_system_datum_store import FilesystemSystemDatumStoreAdapter

__all__ = ["FilesystemSystemDatumStoreAdapter"]
