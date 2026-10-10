"""Pydantic schemas for Casera searches integration."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from typing import Literal

from pydantic import BaseModel, Field


class CaseraIntegrationSettingsOut(BaseModel):
    enabled: bool
    sandbox: bool
    client_id: str | None = None
    access_token_configured: bool = False
    webhook_secret_configured: bool = False
    webhook_path_token: str | None = None
    webhook_url: str | None = None
    api_base_uri: str | None = None
    # When true, place-order posts each product cost as an anticipated disbursement.
    post_anticipated_disbursement: bool = False
    anticipated_ledger_account: Literal["office", "client"] = "office"
    # When true, place-order ensures a Finance "Searches" category and debit rows for costs.
    add_to_completion_statement: bool = False
    # When true, e-mail matter staff when a search result file lands.
    email_on_result_ready: bool = False
    configured: bool = False


class CaseraIntegrationSettingsUpdate(BaseModel):
    enabled: bool | None = None
    sandbox: bool | None = None
    client_id: str | None = None
    access_token: str | None = None
    webhook_secret: str | None = None
    webhook_path_token: str | None = None
    api_base_uri: str | None = None
    post_anticipated_disbursement: bool | None = None
    anticipated_ledger_account: Literal["office", "client"] | None = None
    add_to_completion_statement: bool | None = None
    email_on_result_ready: bool | None = None


class CaseraOrderProductOut(BaseModel):
    id: uuid.UUID
    casera_product_id: str
    casera_order_product_id: str | None = None
    name: str
    state: str
    price_pence: int
    due_at: datetime | None = None
    file_id: uuid.UUID | None = None
    file_ids: list[uuid.UUID] = Field(default_factory=list)


class CaseraRiskBadgeOut(BaseModel):
    key: str
    label: str
    available: bool = True
    level: str | None = None
    product_ids: list[str] = Field(default_factory=list)
    detail: str | None = None


class CaseraOrderOut(BaseModel):
    id: uuid.UUID
    casera_order_id: str
    category: str
    state: str
    total_pence: int
    due_at: datetime | None = None
    placed_at: datetime | None = None
    created_at: datetime
    products: list[CaseraOrderProductOut] = Field(default_factory=list)
    selected_product_ids: list[str] = Field(default_factory=list)
    selected_pack_ids: list[str] = Field(default_factory=list)


class CaseraSearchesSummaryOut(BaseModel):
    configured: bool
    enabled: bool
    # Install-wide provider for the Searches menu (``none`` | ``casera`` | …).
    provider: str = "none"
    orders: list[CaseraOrderOut] = Field(default_factory=list)
    total_pence: int = 0
    # Suggested Casera caseRef for a new link (matter number).
    suggested_reference: str = ""
    # Existing Casera case reference when this matter is already linked (null = not linked yet).
    casera_reference: str | None = None


class CaseraConveyancingDetailsIn(BaseModel):
    type: str = "Residential"
    new_build: bool = False
    title_numbers: list[str] = Field(default_factory=list)
    building_identifier: str | None = None
    street: str | None = None
    locality: str | None = None
    town_city: str | None = None
    county: str | None = None
    postcode: str | None = None
    uprn: str | None = None
    centroid: list[float] | None = None
    polygons: list[list[list[float]]] | None = None
    hectares: float | None = None
    perimeter: float | None = None
    local_authority: str | None = None
    water_authority: str | None = None
    drainage_authority: str | None = None


class CaseraPrefillOut(BaseModel):
    conveyancing: CaseraConveyancingDetailsIn
    from_property: bool = False
    suggested_reference: str = ""
    casera_reference: str | None = None


class CaseraCreateOrderIn(BaseModel):
    category: str = "Conveyancing"
    conveyancing_type: str = "Residential"
    conveyancing: CaseraConveyancingDetailsIn | None = None
    # Casera caseRef — used when first linking this matter; ignored once linked.
    reference: str | None = Field(default=None, max_length=200)


class CaseraAvailableProductOut(BaseModel):
    id: str
    name: str
    price_pence: int | None = None
    subcategory: str | None = None
    description: str | None = None
    group: str | None = None


class CaseraAvailablePackOut(BaseModel):
    id: str
    name: str
    price_pence: int | None = None
    product_ids: list[str] = Field(default_factory=list)
    # Display names for pack constituents (same order as product_ids when known).
    product_names: list[str] = Field(default_factory=list)


class CaseraCreateOrderOut(BaseModel):
    order: CaseraOrderOut
    products: list[CaseraAvailableProductOut] = Field(default_factory=list)
    packs: list[CaseraAvailablePackOut] = Field(default_factory=list)
    risks: dict[str, Any] = Field(default_factory=dict)
    risk_badges: list[CaseraRiskBadgeOut] = Field(default_factory=list)


class CaseraSetProductsIn(BaseModel):
    products: list[str] = Field(default_factory=list)
    packs: list[str] = Field(default_factory=list)


class CaseraPlaceOrderIn(BaseModel):
    override_funds_warning: bool = False


class CaseraSearchFileSummary(BaseModel):
    """Attached to FileSummary for documents list status subline."""

    order_product_id: uuid.UUID
    product_name: str
    state: str
    due_at: datetime | None = None
    status_label: str
