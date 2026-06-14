import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401
from app.build_metadata import effective_build_commit
from app.canary_public_url import get_canary_public_base
from app.calendar_notification_job import start_calendar_notification_job
from app.event_tracked_task_job import start_event_tracked_task_job
from app.webdav_cors_middleware import WebdavPublicCORSMiddleware
from app.routers import (
    admin_audit,
    admin_deploy,
    admin_storage,
    admin_billing,
    admin_email_integration,
    admin_firm_settings,
    admin_finance,
    admin_merge_codes,
    admin_matter_contact_types,
    admin_permission_categories,
    admin_standard_tasks,
    admin_sub_menu_events,
    admin_users,
    auth,
    case_access,
    case_contacts,
    case_events,
    case_finance,
    case_sources,
    case_invoices,
    case_ledger,
    case_notes,
    case_portal,
    case_property,
    case_tasks,
    cases,
    contact_portal,
    fee_scales,
    task_menu,
    contacts,
    files,
    matter_contact_types,
    matter_types,
    me_calendar_events,
    me_calendars,
    onlyoffice,
    mail_plugin,
    outlook_plugin,
    portal,
    precedents,
    reports,
    reconciliations,
    quote_portal,
    users,
    webauthn,
    webdav,
)


from app.master_admin import validate_master_admin_config_at_startup

validate_master_admin_config_at_startup()


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging

    from app.db import SessionLocal
    from app.matter_type_bootstrap import sync_matter_types_from_seed
    from app.merge_code_catalog_sync import sync_merge_code_catalog
    from app.permission_category_bootstrap import ensure_builtin_permission_categories
    from app.precedent_bootstrap import apply_precedent_seed_if_empty

    _log = logging.getLogger("uvicorn.error")
    db = SessionLocal()
    try:
        sync_matter_types_from_seed(db)
    except Exception as e:
        db.rollback()
        _log.warning("Matter type seed skipped: %s", e)
    try:
        ensure_builtin_permission_categories(db)
    except Exception as e:
        db.rollback()
        _log.warning("Permission category bootstrap skipped: %s", e)
    try:
        apply_precedent_seed_if_empty(db)
    except Exception as e:
        db.rollback()
        _log.warning("Precedent seed skipped: %s", e)
    finally:
        db.close()

    db_merge = SessionLocal()
    try:
        sync_merge_code_catalog(db_merge)
    except Exception as e:
        db_merge.rollback()
        _log.warning("Merge code catalog sync skipped: %s", e)
    finally:
        db_merge.close()

    start_event_tracked_task_job()
    start_calendar_notification_job()
    import time

    from app.compose_deploy_job import compose_job_disk_says_running, reconcile_compose_job_state

    for _ in range(4):
        try:
            reconcile_compose_job_state()
        except Exception as e:
            _log.warning("compose job reconcile on startup skipped: %s", e)
            break
        if not compose_job_disk_says_running():
            break
        time.sleep(2.5)
    yield


def _extra_cors_origins() -> list[str]:
    raw = os.getenv("CANARY_CORS_ORIGINS", "").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _cors_allow_origins() -> list[str]:
    base = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        # Default docker-compose production frontend (nginx on host :8080).
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]
    pub = get_canary_public_base()
    extras = _extra_cors_origins()
    merged: list[str] = []
    seen: set[str] = set()
    for o in base + ([pub] if pub else []) + extras:
        if o not in seen:
            seen.add(o)
            merged.append(o)
    return merged


# LAN / Tailscale HTTP origins (private IPv4). Public HTTPS domains use CANARY_PUBLIC_URL /
# CANARY_CORS_ORIGINS and/or CANARY_CORS_ORIGIN_REGEX.
_LAN_HTTP_ORIGIN_REGEX = (
    r"^http://(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|"
    r"100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3})(:\d+)?$"
)


def _cors_allow_origin_regex() -> str:
    extra = os.getenv("CANARY_CORS_ORIGIN_REGEX", "").strip()
    if extra:
        return f"(?:{_LAN_HTTP_ORIGIN_REGEX})|(?:{extra})"
    return _LAN_HTTP_ORIGIN_REGEX


def _install_proxy_headers_middleware(application: FastAPI) -> None:
    """Trust X-Forwarded-* from Docker/internal proxies (see CANARY_PROXY_TRUSTED_HOSTS)."""
    raw = os.getenv("CANARY_BEHIND_REVERSE_PROXY", "").strip().lower()
    if raw not in ("1", "true", "yes"):
        return
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    hosts_raw = os.getenv("CANARY_PROXY_TRUSTED_HOSTS", "").strip()
    trusted: list[str] | str
    if not hosts_raw or hosts_raw == "*":
        trusted = "*"
    else:
        trusted = hosts_raw
    application.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted)


app = FastAPI(title="Case Management Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_origin_regex=_cors_allow_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# After CORS: append WebDAV-specific headers (token auth; no cookies). Helps ONLYOFFICE Desktop
# embedded views that enforce CORS on PROPFIND/GET.
app.add_middleware(WebdavPublicCORSMiddleware)
_install_proxy_headers_middleware(app)

app.include_router(auth.router)
app.include_router(webauthn.router)
app.include_router(admin_users.router)
app.include_router(admin_firm_settings.router)
app.include_router(admin_merge_codes.router)
app.include_router(admin_matter_contact_types.router)
app.include_router(admin_permission_categories.router)
app.include_router(admin_audit.router)
app.include_router(admin_deploy.router)
app.include_router(admin_storage.router)
app.include_router(matter_contact_types.router)
app.include_router(matter_types.router)
app.include_router(cases.router)
app.include_router(case_property.router)
app.include_router(precedents.router)
app.include_router(fee_scales.router)
app.include_router(contacts.router)
app.include_router(contact_portal.router)
app.include_router(case_access.router)
app.include_router(case_contacts.router)
app.include_router(case_portal.router)
app.include_router(case_notes.router)
app.include_router(case_tasks.router)
app.include_router(task_menu.router)
app.include_router(case_ledger.router)
app.include_router(case_invoices.router)
app.include_router(case_finance.router)
app.include_router(case_sources.router)
app.include_router(case_events.router)
app.include_router(admin_finance.router)
app.include_router(admin_billing.router)
app.include_router(admin_email_integration.router)
app.include_router(admin_standard_tasks.router)
app.include_router(admin_sub_menu_events.router)
app.include_router(files.router)
app.include_router(outlook_plugin.router)
app.include_router(mail_plugin.router)
app.include_router(onlyoffice.router)
app.include_router(webdav.router)
app.include_router(users.router)
app.include_router(me_calendar_events.router)
app.include_router(me_calendars.router)
app.include_router(reports.router)
app.include_router(reconciliations.router)
app.include_router(quote_portal.router)
app.include_router(portal.router)

@app.get("/health")
def health():
    commit = effective_build_commit()
    return {"status": "ok", "build_commit": commit or None}
