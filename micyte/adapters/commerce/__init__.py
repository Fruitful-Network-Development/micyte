"""Commerce adapters — MiCyte-side fillings of ``micyte.ports.commerce_offering``.

Provider-NEUTRAL only: the catalog and the availability quote are the datum world's.
A payment provider enters on the FND side (``fnd_app/packages/peripherals/commerce``)
as a :class:`ReservationLedger` over the order-intake journal, consuming this port —
never the other way around, per the MiCyte<->FND boundary.
"""

from .offering_adapter import DatumOfferingAdapter

__all__ = ["DatumOfferingAdapter"]
