from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

class ComposeOfficeDocumentIn(BaseModel):
    original_filename: str = Field(min_length=1, max_length=512)
    folder: str = ""
    precedent_id: uuid.UUID | None = None
    # When ``precedent_id`` is omitted: ``letter`` resolves to the reserved ``BLANK_LETTER`` precedent;
    # ``document`` keeps a minimal empty .docx. If omitted, the server infers from ``original_filename``
    # (``Letter — …`` vs ``Document — …`` as produced by the web UI).
    compose_office_role: Literal["letter", "document"] | None = None
    # Contact for precedent code merge; one of these may be supplied
    case_contact_id: uuid.UUID | None = None   # CaseContact row id
    global_contact_id: uuid.UUID | None = None  # global Contact row id
    # When True, fill [TITLE]…[TRADING_NAME_4] from up to four Client matter contacts (by date added).
    # When False and case_contact_id is a Client, only that client’s slot is filled (see docx_util.build_merge_fields).
    # [CONTACT_*] codes always reflect the contact chosen in compose when one is supplied, including alongside merge-all.
    precedent_merge_all_clients: bool = False

class CaseEmailDraftM365In(BaseModel):
    """Create an Outlook draft via Microsoft Graph (same merge inputs as compose-office, plus case file attachments)."""

    folder: str = ""
    precedent_id: uuid.UUID | None = None
    case_contact_id: uuid.UUID | None = None
    global_contact_id: uuid.UUID | None = None
    precedent_merge_all_clients: bool = False
    compose_office_role: Literal["letter", "document"] | None = None
    attachment_file_ids: list[uuid.UUID] = Field(default_factory=list)

class CaseEmailDraftM365AttachmentOut(BaseModel):
    file_id: uuid.UUID
    filename: str

class CaseEmailDraftM365Out(BaseModel):
    to: str = ""
    subject: str = ""
    body: str = ""
    open_url: str
    """OWA compose deeplink for the Graph draft (or prefill compose when there are no attachments)."""
    graph_message_id: str | None = None
    draft_compose_web_link: str | None = None
    """Graph draft in Drafts (attachments on message; may open as preview until Edit)."""
    compose_prefill_url: str | None = None
    attachment_count: int = 0
    compose_handoff_token: str | None = None
    attachment_files: list[CaseEmailDraftM365AttachmentOut] = Field(default_factory=list)

class CaseEmailMailtoOut(BaseModel):
    to: str
    subject: str
    body: str
    attachment_count: int
    note: str = (
        "Standard mailto links cannot attach case files — add attachments manually in your mail program."
    )

class CaseEmailComposeHandoffOut(BaseModel):
    """JWT handoff for Thunderbird (or other mail clients) to open compose with merge + attachments."""

    handoff_token: str
    case_id: uuid.UUID
    expires_in_seconds: int
    thunderbird_hint: str = (
        "In Thunderbird, open Canary → Compose from matter (or paste the handoff if prompted). "
        "The compose window will include the merged body and case attachments."
    )

class MailPluginComposeAttachmentOut(BaseModel):
    file_id: uuid.UUID
    filename: str
    mime_type: str
    content_base64: str

class MailPluginComposeHandoffOut(BaseModel):
    case_id: uuid.UUID
    to: str
    subject: str
    body: str
    attachments: list[MailPluginComposeAttachmentOut] = Field(default_factory=list)

class EmailIntegrationSettingsOut(BaseModel):
    integration_mode: Literal["mailto", "microsoft_graph"]
    graph_tenant_id: str | None
    graph_client_id: str | None
    graph_client_secret_configured: bool
    outlook_web_mail_base: str | None
    alerts_enabled: bool
    alert_transport: Literal["auto", "graph", "smtp"]
    graph_send_mailbox: str | None
    graph_send_from_name: str | None
    graph_alert_ready: bool
    smtp_alert_ready: bool
    effective_alert_transport: Literal["graph", "smtp"] | None

class EmailIntegrationSettingsUpdate(BaseModel):
    integration_mode: Literal["mailto", "microsoft_graph"] | None = None
    graph_tenant_id: str | None = Field(default=None, max_length=2000)
    graph_client_id: str | None = Field(default=None, max_length=2000)
    graph_client_secret: str | None = Field(default=None, max_length=2000)
    outlook_web_mail_base: str | None = Field(default=None, max_length=2000)
    alerts_enabled: bool | None = None
    alert_transport: Literal["auto", "graph", "smtp"] | None = None
    graph_send_mailbox: str | None = Field(default=None, max_length=320)
    graph_send_from_name: str | None = Field(default=None, max_length=200)

class FirmAlertTestIn(BaseModel):
    to_email: EmailStr

class SmtpNotificationSettingsOut(BaseModel):
    enabled: bool
    host: str | None
    port: int
    use_tls: bool
    username: str | None
    password_configured: bool
    from_email: str | None
    from_name: str | None

class SmtpNotificationSettingsUpdate(BaseModel):
    enabled: bool | None = None
    host: str | None = Field(default=None, max_length=300)
    port: int | None = Field(default=None, ge=1, le=65535)
    use_tls: bool | None = None
    username: str | None = Field(default=None, max_length=320)
    password: str | None = Field(default=None, max_length=500)
    from_email: str | None = Field(default=None, max_length=320)
    from_name: str | None = Field(default=None, max_length=200)

class SmtpNotificationTestIn(BaseModel):
    to_email: EmailStr
