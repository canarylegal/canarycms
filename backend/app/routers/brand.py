"""Public install brand / vendor chrome (product name for forks)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.brand_config import product_name, vendor_url

router = APIRouter(prefix="/brand", tags=["brand"])


class BrandPublicOut(BaseModel):
    """Env-only product identity. Not firm trading name; not Admin-editable."""

    product_name: str
    vendor_url: str


@router.get("/public", response_model=BrandPublicOut)
def brand_public() -> BrandPublicOut:
    return BrandPublicOut(product_name=product_name(), vendor_url=vendor_url())
