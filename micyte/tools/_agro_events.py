"""Single source of truth for the agro_erp lcl event_classification node addresses.

The event_classification branch (lcl ``1-3-2``) types every record entry by its event. These
addresses were re-declared as bare string literals across contracts_tool / record_synopsis /
append_record_event_type — a drift hazard the moment the taxonomy moves again. Import them from
here so the viewers, the inventory synopsis, and the migration stamp the same nodes.
"""

from __future__ import annotations

EVENT_CLASSIFICATION = "1-3-2"
EVENT_PROCUREMENT = "1-3-2-1"   # supply-record use (invoices)
EVENT_DIVESTMENT = "1-3-2-2"    # sales-record use
EVENT_INVESTMENT = "1-3-2-3"    # contract 'planting' use (contracts)
EVENT_YIELD = "1-3-2-4"         # harvest timestamp use
