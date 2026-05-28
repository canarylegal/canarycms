# Canary — Thunderbird add-on

MailExtension (Manifest V2) to **file mail to a matter**, **compose with merge + attachments**, and apply the **Canary** message tag on **incoming** mail (Apply / File to matter). **Sent** replies are saved to the matter on send but are **not** tagged in Thunderbird.

The Outlook add-in lives at `../frontend/public/outlook-addin/`.

## Source folder vs `frontend/public/thunderbird-addin/`

There are two copies of this add-on in the repo:

| Path | Role |
|------|------|
| **`thunderbird-addin/`** (this folder, repo root) | **Source of truth** — edit here. |
| **`frontend/public/thunderbird-addin/`** | **Synced copy** for the web frontend Docker build. Updated when you run `npm run build` in `frontend/` (via `scripts/sync-and-verify-thunderbird-addin.mjs`). |

They should be identical after sync. From `frontend/` run:

```bash
node scripts/sync-and-verify-thunderbird-addin.mjs
```

## User flow (compose)

1. Sign in once via toolbar **Server & sign-in** (same Canary site URL as the web app).
2. Open or focus a compose window → click **Canary** on the compose toolbar.
3. Pick matter (or **None**), contact, precedent, folder, attachments → **Apply to message**.
4. On a **reply**, the incoming message is filed and tagged immediately.
5. **Send** — the sent message is filed to the matter as its own `.eml` (no Thunderbird tag on sent mail).

## Load temporarily (development)

**Tools** → **Add-ons and Themes** → **Debug Add-ons** → **Load Temporary Add-on…** → this folder’s `manifest.json`.

Temporary add-ons are removed when Thunderbird restarts. Use this while developing.

## Install permanently

Release Thunderbird only keeps **signed** add-ons after restart. Unsigned temporary loads do not persist.

### Option A — Install a signed `.xpi` (typical for a firm)

1. Package the add-on (from repo root):

   ```bash
   cd thunderbird-addin
   zip -r ../canary-thunderbird.xpi * -x '*.nextcloud*'
   ```

2. **Get the `.xpi` signed by Mozilla** (required for normal Thunderbird):
   - Create a developer account at [Thunderbird Add-ons](https://addons.thunderbird.net/developers/).
   - Submit `canary-thunderbird.xpi` as an **unlisted** add-on (not public on the store, but Mozilla signs it).
   - Download the signed `.xpi` from the developer hub.

3. Install the **signed** file in Thunderbird:
   - **Add-ons and Themes** → gear menu → **Install Add-on From File…** → choose the signed `.xpi`.

The add-on then survives restart and updates only when you install a newer signed `.xpi`.

### Option B — Enterprise deployment

Place the **signed** `.xpi` in Thunderbird’s [enterprise distribution](https://wiki.mozilla.org/Thunderbird/Enterprise) `extensions` folder via `distribution.ini` / policies so it is pre-installed for all users. Your IT team would host the signed XPI internally.

### Option C — Keep using temporary load

Fine for solo development; reload the temporary add-on after each Thunderbird restart.

## API

Uses configurable origin + `/api` (Bearer JWT). Main routes:

- `POST /api/mail-plugin/cases/{case_id}/compose-bundle`
- `PUT|DELETE /api/mail-plugin/pending-send`
- `POST /api/cases/{case_id}/files` (multipart; `folder`, `parent_file_id`, `compose_*` form fields)

## Reference

- [Thunderbird WebExtension APIs](https://webextension-api.thunderbird.net/) — `messages`, `compose`, `composeAction`, `menus`.
- [Add-on signing](https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/)
