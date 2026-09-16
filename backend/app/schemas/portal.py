from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

class CasePortalFolderAccessGrantOut(BaseModel):
    folder_path: str
    contact_id: uuid.UUID
    contact_name: str

class CasePortalFolderShareContactOut(BaseModel):
    case_contact_id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str
    has_grant: bool
    grant_id: uuid.UUID | None
    portal_access_active: bool = True
    # Matter snapshot e-mail, then global contact card (empty when missing).
    email: str = ""
    matter_contact_type: str = ""
    is_exchange_contact: bool = False

class PortalConfigOut(BaseModel):
    firm_name: str
    portal_title: str
    portal_logo_url: str | None = None
    portal_background_color: str | None = None
    powered_by_label: str = "Powered by Canary Legal Software"
    powered_by_url: str = "https://canarylegalsoftware.co.uk"

class PortalAuthIn(BaseModel):
    access_code: str = Field(min_length=8, max_length=64)

class PortalGrantSummaryOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    case_title: str
    folder_path: str
    folder_label: str
    label: str
    can_download: bool
    can_upload: bool
    new_file_count: int = 0
    last_viewed_at: datetime | None = None

class PortalAuthOut(BaseModel):
    session_token: str
    contact_name: str
    grants: list[PortalGrantSummaryOut]
    focus_case_id: uuid.UUID | None = None
    staff_preview: bool = False
    audience: Literal["client", "exchange"] = "client"

class PortalSessionOut(BaseModel):
    contact_name: str
    grants: list[PortalGrantSummaryOut]
    staff_preview: bool = False
    audience: Literal["client", "exchange"] = "client"
    focus_case_id: uuid.UUID | None = None

class PortalFileOut(BaseModel):
    id: uuid.UUID
    original_filename: str
    mime_type: str
    size_bytes: int
    folder_path: str
    folder_display: str = ""
    created_at: datetime
    updated_at: datetime
    is_new: bool = False

class PortalBrowseOut(BaseModel):
    subfolder: str
    breadcrumb: list[str]
    subfolders: list[str]
    files: list[PortalFileOut]
    pending_approvals: list[PortalQuoteDeliveryViewOut] = []
    pending_docusign_signings: list["PortalDocusignSigningOut"] = []
    pending_canary_signings: list["PortalCanarySignOut"] = []
    pending_portal_forms: list["PortalFormPendingOut"] = []
    new_file_count: int = 0
    last_viewed_at: datetime | None = None

class PortalFormTemplateFieldIn(BaseModel):
    field_key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=500)
    field_type: Literal["section", "text", "textarea", "date", "select", "file"]
    help_text: str | None = Field(default=None, max_length=2000)
    required: bool = False
    sort_order: int = 0
    select_options: list[str] = Field(default_factory=list)

class PortalFormTemplateFieldOut(PortalFormTemplateFieldIn):
    id: uuid.UUID

class PortalFormTemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    reference: str
    description: str | None = None
    matter_head_type_id: uuid.UUID | None = None
    matter_sub_type_id: uuid.UUID | None = None
    scope_summary: str = ""
    field_count: int = 0
    created_at: datetime
    updated_at: datetime

class PortalFormTemplateDetailOut(PortalFormTemplateOut):
    fields: list[PortalFormTemplateFieldOut] = []

class PortalFormTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    reference: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    matter_head_type_id: uuid.UUID | None = None
    matter_sub_type_id: uuid.UUID | None = None
    fields: list[PortalFormTemplateFieldIn] = Field(default_factory=list)

class PortalFormTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    reference: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    matter_head_type_id: uuid.UUID | None = None
    matter_sub_type_id: uuid.UUID | None = None
    fields: list[PortalFormTemplateFieldIn] | None = None

class PortalFormSendIn(BaseModel):
    template_id: uuid.UUID
    contact_id: uuid.UUID

class PortalFormSubmissionOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    template_id: uuid.UUID
    template_name: str
    template_reference: str
    contact_id: uuid.UUID
    contact_name: str
    status: str
    responses: dict = {}
    snapshot_file_id: uuid.UUID | None = None
    snapshot_filename: str = ""
    sent_at: datetime
    completed_at: datetime | None = None
    voided_at: datetime | None = None
    email_sent: bool = False
    email_skip_reason: str | None = None

class PortalFormFieldOut(BaseModel):
    field_key: str
    label: str
    field_type: str
    help_text: str | None = None
    required: bool
    sort_order: int
    select_options: list[str] = []

class PortalFormPendingOut(BaseModel):
    id: uuid.UUID
    template_name: str
    template_reference: str
    status: str
    sent_at: datetime
    case_id: uuid.UUID | None = None
    matter_label: str = ""

class PortalFormDetailOut(PortalFormSubmissionOut):
    description: str | None = None
    fields: list[PortalFormFieldOut] = []

class PortalFormSubmitIn(BaseModel):
    responses: dict = Field(default_factory=dict)

class PortalOtpRequestIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)

class PortalOtpVerifyIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    code: str = Field(min_length=4, max_length=12)

class CasePortalNotifyFilesIn(BaseModel):
    folder_path: str = ""
    filenames: list[str] = Field(min_length=1)

class CasePortalNotifyFilesOut(BaseModel):
    contacts_notified: int
    alerts_skipped_reason: str | None = None

class CasePortalActivityOut(BaseModel):
    id: uuid.UUID
    action: str
    summary: str
    contact_name: str | None
    created_at: datetime

class CasePortalShareStatusOut(BaseModel):
    portal_enabled: bool
    active_grant_count: int
    contact_count: int

class CasePortalStaffUserOut(BaseModel):
    id: uuid.UUID
    display_name: str
    email: str

class CasePortalNotificationSettingsOut(BaseModel):
    staff_user_ids: list[uuid.UUID]
    staff_users: list[CasePortalStaffUserOut] = Field(default_factory=list)

class CasePortalNotificationSettingsIn(BaseModel):
    staff_user_ids: list[uuid.UUID] = Field(default_factory=list)

class CasePortalPreviewContactOut(BaseModel):
    contact_id: uuid.UUID
    contact_name: str
    shared_folder_count: int
    pending_quote_count: int = 0
    pending_form_count: int = 0
    pending_canary_sign_count: int = 0

class CasePortalPreviewIn(BaseModel):
    contact_id: uuid.UUID

class CasePortalPreviewOut(BaseModel):
    exchange_token: str
    contact_name: str
    preview_url: str

class PortalPreviewExchangeIn(BaseModel):
    exchange_token: str = Field(min_length=10, max_length=4096)

class PortalQuoteExchangeIn(BaseModel):
    exchange_token: str = Field(min_length=10, max_length=4096)

class PortalFormExchangeIn(BaseModel):
    exchange_token: str = Field(min_length=10, max_length=4096)

class PortalQuoteDeliveryViewOut(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    grant_id: uuid.UUID | None
    case_id: uuid.UUID | None = None
    case_title: str = ""
    original_filename: str
    mime_type: str = "application/octet-stream"
    size_bytes: int = 0
    folder_display: str = ""
    status: str
    can_respond: bool
    decline_reason: str | None = None
    responded_at: datetime | None = None
    portal_pdf_available: bool = False

class PortalQuoteRespondIn(BaseModel):
    accepted: bool
    decline_reason: str | None = Field(default=None, max_length=2000)

class PortalQuoteExchangeOut(BaseModel):
    session_token: str
    contact_name: str
    grants: list[PortalGrantSummaryOut]
    quote: PortalQuoteDeliveryViewOut

class PortalFormExchangeOut(BaseModel):
    session_token: str
    contact_name: str
    grants: list[PortalGrantSummaryOut]
    form: PortalFormPendingOut

class QuotePortalSendPreflightOut(BaseModel):
    alerts_configured: bool

class SendQuoteViaPortalIn(BaseModel):
    contact_id: uuid.UUID

class PortalQuoteTagUpdate(BaseModel):
    is_portal_quote: bool

class QuotePortalDeliveryOut(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str
    status: str
    sent_at: datetime
    responded_at: datetime | None = None
    decline_reason: str | None = None
    file_version_at_send: int
    email_sent: bool = False
    email_skip_reason: str | None = None
    portal_pdf_generated: bool = False

class PublishComposeIn(BaseModel):
    notify_portal_contacts: bool = False

class ContactPortalNotificationPrefsOut(BaseModel):
    notify_files_added: bool
    notify_folder_shared: bool

class ContactPortalNotificationPrefsIn(BaseModel):
    notify_files_added: bool | None = None
    notify_folder_shared: bool | None = None

class ContactPortalAccessOut(BaseModel):
    enabled: bool
    expires_at: datetime | None
    last_login_at: datetime | None
    locked_until: datetime | None
    has_access: bool
    access_code: str | None = None
    access_record_exists: bool = False
    notify_files_added: bool = True
    notify_folder_shared: bool = True

class ContactPortalAccessCreateOut(BaseModel):
    access_code: str
    enabled: bool
    expires_at: datetime | None
    email_sent: bool = False
    email_skip_reason: str | None = None

class ContactPortalAccessActionIn(BaseModel):
    send_email: bool = False
    """When set (matter contact UI), portal must be enabled on that matter before granting access."""
    case_id: uuid.UUID | None = None

class MatterPortalAccessOut(BaseModel):
    enabled: bool
    expires_at: datetime | None
    last_login_at: datetime | None
    locked_until: datetime | None
    has_access: bool
    access_code: str | None = None
    access_record_exists: bool = False
    notify_folder_shared: bool = True
    case_id: uuid.UUID
    contact_id: uuid.UUID

class MatterPortalAccessCreateOut(BaseModel):
    access_code: str
    enabled: bool
    expires_at: datetime | None = None
    email_sent: bool = False
    email_skip_reason: str | None = None
    case_id: uuid.UUID
    contact_id: uuid.UUID

class MatterPortalAccessActionIn(BaseModel):
    send_email: bool = False

class ContactPortalAccessEmailIn(BaseModel):
    access_code: str = Field(min_length=4, max_length=64)

class ContactPortalAccessUpdateIn(BaseModel):
    enabled: bool | None = None
    expires_at: datetime | None = None

class ContactPortalGrantOut(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    case_id: uuid.UUID
    case_title: str
    folder_path: str
    label: str | None
    can_download: bool
    can_upload: bool
    expires_at: datetime | None
    created_at: datetime
    email_sent: bool = False
    email_skip_reason: str | None = None

class ContactPortalGrantCreateIn(BaseModel):
    case_id: uuid.UUID
    folder_path: str = ""
    label: str | None = Field(default=None, max_length=300)
    can_download: bool = True
    can_upload: bool = True
    expires_at: datetime | None = None
    send_email: bool = False

class ContactPortalGrantUpdateIn(BaseModel):
    folder_path: str | None = None
    label: str | None = Field(default=None, max_length=300)
    can_download: bool | None = None
    can_upload: bool | None = None
    expires_at: datetime | None = None
