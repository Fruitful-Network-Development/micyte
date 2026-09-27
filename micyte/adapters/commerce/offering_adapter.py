"""The first ``CommerceOfferingPort`` adapter — store-backed, provider-neutral, unbound.

TASK-2026-08-14-002 Phase 4. The binding docs named a module at
``fnd_app.packages.peripherals.commerce.paypal`` that never existed; what an adapter for
this port honestly IS turned out to be provider-neutral, because the port is the
OUTBOUND-READ seam — the catalog and the availability quote — and no payment provider
appears in either. That is also why it lives on the MiCyte side (``micyte/adapters``):
it composes the store and the ``_offering`` read model, both MOS implementations the
FND side may not reach. PayPal enters on the FND side
(``fnd_app/packages/peripherals/commerce``) as a :class:`ReservationLedger` over the
order-intake journal (the port's own "Phase 6" note), and as the egress the app's port
DECLARATION names (``paypal: order.create / order.capture``), judged by
``external_call_policy`` when an operator binds and grants it.

The adapter adds NO judgement of its own. The catalog and the quote are
``micyte.tools._offering``'s — the one read model already behind the offering table, the
synopsis and this port projection, so a storefront and the operator's own pane cannot
disagree. What this class supplies is the store plumbing the wheel-side read model
deliberately does not carry.

Ships with ``ledger=None``: availability RAISES (``require_reservation_ledger``) rather
than quoting against an assumed zero — the refusal the port exists for. A deployment
installs a ledger by constructing the adapter with one.
"""

from __future__ import annotations

from typing import Any

from micyte.core.instance_scope import use_instance
from micyte.ports.commerce_offering import (
    AvailabilityQuote,
    AvailabilityRequest,
    CommerceOfferingPort,
    OfferingCatalog,
    ReservationLedger,
)
from micyte.tools._offering import availability


class DatumOfferingAdapter:
    """``CommerceOfferingPort`` over a supplied datum STORE.

    The store is INJECTED, never constructed here: an adapter that opened its own
    connection would be one a test could not hand a fixture, and the HOST already
    holds the store the binding's instance uses.

    ``msn_id`` is required: a sandbox is addressed by ``(msn_id, sandbox)``, and an
    adapter that resolved names alone would read whichever instance's ``system`` the
    index yielded — the ambiguity the addressing rule exists to refuse. A binding names
    its sandboxes; the host constructs one adapter per bound instance.
    """

    def __init__(
        self,
        store: Any,
        *,
        msn_id: str,
        tenant_id: str = "fnd",
        ledger: ReservationLedger | None = None,
    ) -> None:
        self._store = store
        self._msn_id = str(msn_id or "").strip()
        if not self._msn_id:
            raise ValueError(
                "an offering adapter is constructed for one instance; msn_id is required")
        self._tenant_id = tenant_id
        self._ledger = ledger

    def _documents(self, sandbox_id: str) -> list[Any]:
        with use_instance(self._msn_id):
            return list(self._store.read_documents_by_sandbox(
                tenant_id=self._tenant_id, sandbox=str(sandbox_id or "").strip()))

    def read_offering_catalog(self, sandbox_id: str) -> OfferingCatalog:
        # The MODERN offer rows (Farmers phase): the `offering` document's `offer`
        # archetype rows, through the same builder the Offering table uses.
        from micyte.core import archetypes as arc
        from micyte.tools import _node_names as nn
        from micyte.tools._viewscope import read_document
        from micyte.tools.job_manager import _document_named
        from micyte.tools.ledger_books import OFFER_ARCHETYPE, OFFER_DOC, offer_catalog, offer_rows

        sandbox = str(sandbox_id or "").strip()
        from micyte.core.instance_scope import use_instance

        with use_instance(self._msn_id):
            library = self._store.read_documents_by_sandbox(
                tenant_id=self._tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
            registry = arc.registry_for(library)
            doc_id = _document_named(
                self._store, tenant_id=self._tenant_id, sandbox=sandbox, name=OFFER_DOC)
            if not doc_id:
                return OfferingCatalog(sandbox_id=sandbox, items=())
            names = nn.name_index_for(
                self._store, tenant_id=self._tenant_id, sandbox=sandbox, registry=registry)
            document = read_document(
                self._store, tenant_id=self._tenant_id, document_id=doc_id)
        return offer_catalog(
            offer_rows(document, sandbox=sandbox,
                       archetype=registry.get(OFFER_ARCHETYPE), names=names),
            sandbox=sandbox)

    def quote_availability(self, request: AvailabilityRequest) -> AvailabilityQuote:
        return availability(
            self._documents(request.sandbox_id),
            request.sandbox_id,
            request.product_node,
            ledger=self._ledger,
        )


# The Protocol is runtime_checkable, so this is a real check rather than a comment.
assert isinstance(
    DatumOfferingAdapter(object(), msn_id="0"), CommerceOfferingPort)

__all__ = ["DatumOfferingAdapter"]
