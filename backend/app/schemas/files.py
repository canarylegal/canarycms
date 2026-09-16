from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

class FilePinUpdate(BaseModel):
    is_pinned: bool

class OutlookOpenHintsOut(BaseModel):
    """Graph / OWA pointers for opening a filed message in Outlook on the web or desktop."""

    outlook_graph_message_id: str | None = None
    outlook_web_link: str | None = None
    # Preferred one-click OWA read URL (built from item id + user/org mail base).
    owa_read_url: str | None = None
    open_in_owa_supported: bool = False

class OutlookPluginLinkedCaseResolveIn(BaseModel):
    outlook_item_id: str | None = None
    internet_message_id: str | None = None
    conversation_id: str | None = None
    source_imap_mbox: str | None = None
    source_imap_uid: str | None = None

class OutlookPluginPendingSendPutIn(BaseModel):
    """Remember a matter for the next message sent from Outlook with the add-in signed in."""

    case_id: uuid.UUID
    source_file_id: uuid.UUID | None = None
    ttl_seconds: int | None = 86400

class OutlookPluginPendingSendOut(BaseModel):
    active: bool
    case_id: uuid.UUID | None = None
    source_file_id: uuid.UUID | None = None
    expires_at: datetime | None = None

class OutlookPluginPendingComposeHandoffPutIn(BaseModel):
    """Queue a compose handoff for the signed-in user's Outlook add-in to claim and open."""

    handoff_token: str = Field(min_length=10)
    ttl_seconds: int | None = 3600

class OutlookPluginPendingComposeHandoffOut(BaseModel):
    active: bool
    handoff_token: str | None = None
    case_id: uuid.UUID | None = None
    expires_at: datetime | None = None

class OutlookPluginLinkedCaseOut(BaseModel):
    id: uuid.UUID
    case_number: str
    client_name: str | None = None
    matter_description: str

class OutlookPluginLinkedCaseResolveOut(BaseModel):
    linked_case: OutlookPluginLinkedCaseOut | None = None

class MailPluginMessageContextOut(BaseModel):
    """Matter + parent e-mail file for a message already filed in Canary (Thunderbird reply prefill)."""

    found: bool = False
    case_id: uuid.UUID | None = None
    file_id: uuid.UUID | None = None
    folder_path: str = ""
    case_number: str | None = None
    client_name: str | None = None
    matter_description: str | None = None

class OutlookPluginEnsureMasterCategoryIn(BaseModel):
    """Mailbox UPN/SMTP for the signed-in Outlook session (must match Canary user email)."""

    mailbox: str

class OutlookPluginEnsureMasterCategoryOut(BaseModel):
    ok: bool
    status: str
    detail: str | None = None

class OutlookPluginGraphTagCategoryIn(BaseModel):
    """
    ``rest_item_id``: prefer ``mailbox.convertToRestId(item.itemId, v2.0)`` for Graph;
    raw ``itemId`` is often EWS-shaped and breaks the Graph URL if unconverted.
    ``internet_message_id``: optional RFC5322 Message-ID for ``$filter`` fallback when GET by id fails.
    """

    mailbox: str
    rest_item_id: str
    internet_message_id: str | None = None

class OutlookPluginGraphTagCategoryOut(BaseModel):
    ok: bool
    status: str
    detail: str | None = None

class OutlookPluginSendCaptureLogIn(BaseModel):
    """Best-effort diagnostic from OnMessageSend (Classic Outlook send filing)."""

    step: str = Field(max_length=64)
    detail: str | None = Field(default=None, max_length=2000)
    case_id: str | None = Field(default=None, max_length=64)

class OutlookPluginSendCaptureLogOut(BaseModel):
    ok: bool = True

class CaseFolderCreate(BaseModel):
    # Relative folder path inside the case ("" == root).
    # Example: "Contracts" or "Contracts/2019"
    folder_path: str

class CaseFolderRenameUpdate(BaseModel):
    old_folder_path: str
    new_folder_path: str

class CaseFolderDeleteUpdate(BaseModel):
    folder_path: str

class CaseFolderMoveUpdate(BaseModel):
    old_folder_path: str
    new_parent_path: str

class CaseFileRenameUpdate(BaseModel):
    """Rename a case file.

    ``expected_original_filename`` is the name the client observed before renaming (CAS).
    Concurrent renames that both target the same starting name yield one 200 and one 409 (CL-19).
    """

    original_filename: str = Field(min_length=1, max_length=512)
    expected_original_filename: str = Field(min_length=1, max_length=512)

class CommentFileUpdate(BaseModel):
    text: str = Field(min_length=0, max_length=500_000)

class CaseFileMoveUpdate(BaseModel):
    """Target folder path inside the case (empty string = root)."""

    folder_path: str = ""

class FileDesktopCheckoutOut(BaseModel):
    """WebDAV URLs for ONLYOFFICE Desktop (or any WebDAV client). Treat `token` as a password."""

    token: str
    webdav_folder_url: str
    webdav_file_url: str
    filename: str
    expires_at: datetime
    instructions: str
    onlyoffice_cli_hint: str = Field(
        description=(
            "Always empty: ONLYOFFICE Desktop does not open http(s) WebDAV URLs from the CLI (args are local paths only). "
            "Use in-browser ONLYOFFICE or a WebDAV mount."
        ),
    )

class FileEditSessionStatusOut(BaseModel):
    active: bool
    expires_at: datetime | None = None
    webdav_file_url: str | None = None

class OoPersistDownloadIn(BaseModel):
    """ONLYOFFICE ``downloadAs`` export URL for persisting edits to Canary storage."""

    browser_url: str = Field(..., min_length=8, max_length=8000)

class OoExportPdfIn(BaseModel):
    """ONLYOFFICE ``downloadAs('pdf')`` URL for saving a new PDF alongside the source document."""

    browser_url: str = Field(..., min_length=8, max_length=8000)
    filename: str | None = Field(default=None, max_length=512)

class OoExportPdfOut(BaseModel):
    file_id: uuid.UUID
    original_filename: str

class OnlyofficeEditorConfigOut(BaseModel):
    """JWT + plaintext fields for DocsAPI.DocEditor.

    ONLYOFFICE requires the plain config fields (document, editorConfig) to be passed to
    DocsAPI.DocEditor alongside the JWT token. The JWT is a signature of those fields, not
    a replacement — without document.url in the plain config the editor creates a blank iframe.
    """

    document_server_url: str
    token: str
    document_type: str
    # Plain (unsigned) fields that must be passed directly to DocsAPI.DocEditor alongside the JWT.
    document: dict
    editor_config: dict
    # Case compose-office: file stays hidden until Save; editor should treat as needing explicit save/close flow.
    oo_compose_pending: bool = False
    folder_path: str = ""
    original_filename: str = ""
