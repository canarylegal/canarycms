"""Pydantic schemas for Casera searches integration."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CaseraIntegrationSettingsOut(BaseModel):
    enabled: bool
    sandbox: bool
    client_id: str | None = None
    developer_key: str | None = None
    access_token_configured: bool = False
    refresh_token_configured: bool = False
    developer_secret_configured: bool = False
    webhook_secret_configured: bool = False
    webhook_path_token: str | None = None
    webhook_url: str | None = None
    api_base_uri: str | None = None
    access_token_expires_at: datetime | None = None
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
    developer_key: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    developer_secret: str | None = None
    webhook_secret: str | None = None
    webhook_path_token: str | None = None
    api_base_uri: str | None = None
    post_anticipated_disbursement: bool | None = None
    anticipated_ledger_account: Literal["office", "client"] | None = None
    add_to_completion_statement: bool | None = None
    email_on_result_ready: bool | None = None


class CaseraLiveConnectStartOut(BaseModel):
    code: str
    consent_url: str
    expires_at: str | None = None
    redirect_uri: str | None = None


class CaseraLiveExchangeIn(BaseModel):
    exchange_code: str = Field(min_length=4, max_length=500)


class CaseraLiveExchangeOut(BaseModel):
    client_id: str | None = None
    integration_id: str | None = None
    sandbox: bool = False
    configured: bool = False


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
    # Geometry is accepted by Casera but Canary does not embed their map widget;
    # leave these null unless a future integration supplies them.
    centroid: list[float] | None = None
    polygons: list[list[list[float]]] | None = None
    hectares: float | None = None
    perimeter: float | None = None
    # Casera FK ids (not display names). Catalogue search is not on integration scopes.
    local_authority: str | None = None
    water_authority: str | None = None
    drainage_authority: str | None = None
    # Casera file ids from title-plan upload (POST /files → conveyancing-details.files).
    plan_file_ids: list[str] = Field(default_factory=list)


class CaseraPrefillOut(BaseModel):
    conveyancing: CaseraConveyancingDetailsIn
    from_property: bool = False
    suggested_reference: str = ""
    casera_reference: str | None = None


class CaseraPlanUploadIn(BaseModel):
    """One local title-plan file (base64) for Casera conveyancing-details."""

    content_base64: str = Field(min_length=1)
    file_name: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=120)


class CaseraCreateOrderIn(BaseModel):
    category: str = "Conveyancing"
    conveyancing_type: str = "Residential"
    conveyancing: CaseraConveyancingDetailsIn | None = None
    # Casera caseRef — used when first linking this matter; ignored once linked.
    reference: str | None = Field(default=None, max_length=200)
    # Title plan(s) (JPG/PNG/PDF) uploaded to Casera before conveyancing-details.
    # Prefer multi-file fields; singular fields remain for older clients.
    plan_uploads: list[CaseraPlanUploadIn] = Field(default_factory=list)
    plan_canary_file_ids: list[uuid.UUID] = Field(default_factory=list)
    plan_file_base64: str | None = None
    plan_file_name: str | None = Field(default=None, max_length=255)
    plan_file_content_type: str | None = Field(default=None, max_length=120)
    plan_canary_file_id: uuid.UUID | None = None


class CaseraAvailableProductOut(BaseModel):
    id: str
    name: str
    price_pence: int | None = None
    subcategory: str | None = None
    description: str | None = None
    group: str | None = None
    product_form_id: int | None = None
    estimated_return_days: int | None = None
    # Casera ``mitigatesRisks`` — used with basket selection for risk mitigation UI.
    mitigates_risks: list[str] = Field(default_factory=list)
    is_favourite: bool = False
    requires_quote: bool = False
    supplier_name: str | None = None
    supplier_logo_url: str | None = None
    # Product card / sample / supplier info (Casera static files or external URLs).
    card_file_url: str | None = None
    sample_file_url: str | None = None
    # Casera static-file ids (auth-gated; open via Canary proxy, not direct URL).
    card_file_id: str | None = None
    card_file_name: str | None = None
    sample_file_id: str | None = None
    sample_file_name: str | None = None
    information_url: str | None = None
    features: list[str] = Field(default_factory=list)


class CaseraAmlPersonIn(BaseModel):
    """Person details for AML / Verify365 products (Casera entity + aml-details)."""

    first_name: str = Field(min_length=1, max_length=200)
    other_names: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone_number: str | None = Field(default=None, max_length=40)
    date_of_birth: str | None = Field(default=None, max_length=32)
    address_line1: str | None = Field(default=None, max_length=300)
    address_line2: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=200)
    county: str | None = Field(default=None, max_length=200)
    postcode: str | None = Field(default=None, max_length=32)


class CaseraCompanyIn(BaseModel):
    """Company details for Company Search products (Casera company entity + bind)."""

    name: str | None = Field(default=None, max_length=300)
    numbers: list[str] = Field(default_factory=list)

    @field_validator("numbers")
    @classmethod
    def _require_numbers(cls, value: list[str]) -> list[str]:
        out = [str(x).strip() for x in (value or []) if str(x).strip()]
        if not out:
            raise ValueError("At least one company number is required")
        if len(out) > 50:
            raise ValueError("Too many company numbers")
        for n in out:
            if len(n) > 64:
                raise ValueError("Company number is too long")
        return out


class CaseraBankAccountIn(BaseModel):
    """Bank account details for Confirmly / Bank Account Check products."""

    company_name: str = Field(min_length=1, max_length=300)
    sort_code: str = Field(min_length=6, max_length=8)
    account_number: str = Field(min_length=7, max_length=8)
    # Casera portal fills this from law-firm search; Canary generates one when omitted.
    transient_id: str | None = Field(default=None, max_length=120)

    @field_validator("sort_code")
    @classmethod
    def _sort_code(cls, value: str) -> str:
        digits = "".join(ch for ch in (value or "") if ch.isdigit())
        if len(digits) != 6:
            raise ValueError("Sort code must be exactly 6 digits")
        return digits

    @field_validator("account_number")
    @classmethod
    def _account_number(cls, value: str) -> str:
        digits = "".join(ch for ch in (value or "") if ch.isdigit())
        if len(digits) not in (7, 8):
            raise ValueError("Account number must be 7 or 8 digits")
        return digits


class CaseraAvailablePackOut(BaseModel):
    id: str
    name: str
    price_pence: int | None = None
    product_ids: list[str] = Field(default_factory=list)
    # Display names for pack constituents (same order as product_ids when known).
    product_names: list[str] = Field(default_factory=list)
    requires_quote: bool = False
    tbc: bool = False


class CaseraSetFavouriteIn(BaseModel):
    favourite: bool = True


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
    aml_person: CaseraAmlPersonIn | None = None
    company: CaseraCompanyIn | None = None
    bank_account: CaseraBankAccountIn | None = None


class CaseraSearchFileSummary(BaseModel):
    """Attached to FileSummary for documents list status subline."""

    order_product_id: uuid.UUID
    product_name: str
    state: str
    due_at: datetime | None = None
    status_label: str
