"""Deployment toggles (env-only; defaults preserve upstream behaviour)."""

from __future__ import annotations

import os

from app.onlyoffice_ds_version import onlyoffice_ds_major


def _truthy_env(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def open_pdf_in_onlyoffice() -> bool:
    """When true, case PDFs use ONLYOFFICE instead of the browser blob viewer."""
    return _truthy_env("CANARY_OPEN_PDF_IN_ONLYOFFICE")


def onlyoffice_callback_require_jwt() -> bool:
    """When true, reject unsigned ONLYOFFICE Document Server save callbacks."""
    return _truthy_env("ONLYOFFICE_CALLBACK_REQUIRE_JWT")


def onlyoffice_editor_customization(*, file_type: str) -> dict[str, bool | str]:
    """Editor customization block for ONLYOFFICE JWT / DocsAPI config."""
    custom: dict[str, bool | str] = {
        "forcesave": True,
        "unit": "cm",
        "compatibleFeatures": True,
    }
    # PDF editor omits autosave by default (strict co-editing). Without it, host CommandService
    # forcesave sees no pending changes and Canary storage is not updated until OO toolbar Save.
    if file_type == "pdf":
        custom["autosave"] = True
    return custom


def onlyoffice_pdf_editor_types() -> tuple[str, str]:
    """``(documentType, fileType)`` for PDFs.

    - DS 7.x: ``word`` + ``pdf`` (annotation viewer; saves as copy only).
    - DS 8.0+: ``pdf`` + ``pdf`` (native editor; in-place save via callback from 9.0.3+).
    """
    mode = (os.getenv("CANARY_ONLYOFFICE_PDF_DOCUMENT_TYPE") or "auto").strip().lower()
    if mode == "word":
        return ("word", "pdf")
    if mode == "pdf":
        return ("pdf", "pdf")
    major = onlyoffice_ds_major()
    if major >= 8:
        return ("pdf", "pdf")
    return ("word", "pdf")
