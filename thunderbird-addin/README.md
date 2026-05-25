# Canary — Thunderbird add-on

MailExtension (Manifest V2) to **file mail to a matter**, **compose with merge + attachments**, and apply the **Canary** message tag. The Outlook add-in lives at `../frontend/public/outlook-addin/`; this folder is synced to `frontend/public/thunderbird-addin/` on `npm run build`.

## v1.1.0

- **Compose (primary):** `compose_action` toolbar → matter, contact, precedent, parent e-mail, folder, attach from Canary → **Apply to message** (`POST /api/mail-plugin/cases/{id}/compose-bundle`). **None** = no filing or tag on send.
- **Send capture:** `compose.onAfterSend` uploads `.eml` with `folder`, `parent_file_id`, and compose metadata on the upload audit event.
- **Filing (lightweight):** Right-click a message → **File to Canary matter…**; message-display / toolbar popup for search + file + tag.
- **Linked matter:** `POST /api/mail-plugin/linked-case` (Message-ID and/or IMAP refs).

## User flow (compose)

1. Sign in once via toolbar **Server & sign-in** (same Canary site URL as the web app).
2. Open or focus a compose window → click **Canary** on the compose toolbar.
3. Pick matter (or **None**), contact, precedent, optional parent e-mail and folder, tick attachments → **Apply to message**.
4. Send; the message is filed to the matter and tagged when a matter was selected.

## Load temporarily (development)

1. **Tools** → **Add-ons and Themes** → **Debug Add-ons** → **Load Temporary Add-on…** → this folder’s `manifest.json`.
2. Reload after edits.

## API

Uses configurable origin + `/api` (Bearer JWT). Main routes:

- `POST /api/mail-plugin/cases/{case_id}/compose-bundle`
- `PUT|DELETE /api/mail-plugin/pending-send`
- `POST /api/cases/{case_id}/files` (multipart; `folder`, `parent_file_id`, `compose_*` form fields)

Legacy `GET /api/mail-plugin/compose-handoff/{token}` remains for old handoff tokens only.

## Reference

- [Thunderbird WebExtension APIs](https://webextension-api.thunderbird.net/) — `messages`, `compose`, `composeAction`, `menus`.
