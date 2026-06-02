"""VAT helpers for fee scales and quotes."""

from __future__ import annotations

from app.models import FeeScaleVatTreatment


def vat_pence_for_net(net_pence: int, vat_rate_bps: int) -> int:
    return round(net_pence * vat_rate_bps / 10000)


def item_vat_pence(
    amount_pence: int | None,
    treatment: FeeScaleVatTreatment,
    vat_rate_bps: int,
) -> int | None:
    if amount_pence is None or treatment != FeeScaleVatTreatment.plus_vat:
        return None
    return vat_pence_for_net(amount_pence, vat_rate_bps)
