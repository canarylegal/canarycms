# Canary — Outlook add-in (“File to Case”)

There is **one manifest**: `manifest.xml`. Use it for sideload, M365 admin upload, and the public URL `https://YOUR_HOST/outlook-addin/manifest.xml`.

Office add-in manifests **must** use absolute `https://…` URLs. Committed `manifest.xml` uses the placeholder **`https://YOUR_CANARY_PUBLIC_URL`**. Docker builds rewrite **`dist/outlook-addin/manifest.xml`** from **`CANARY_PUBLIC_URL`** in `.env` before nginx serves it.

### M365 admin upload (Integrated apps)

1. Deploy the frontend (so `/outlook-addin/manifest.xml` on your host matches `CANARY_PUBLIC_URL`).
2. Upload either:
   - **Manifest URL:** `https://YOUR_HOST/outlook-addin/manifest.xml`, or
   - **From device:** `frontend/public/outlook-addin/manifest.xml` (same file — must match the host you deploy to).
3. Turn **On** and assign users.

### If upload fails with “already installed elsewhere”

Outlook ties an add-in identity to **`<Id>`** and the **manifest URLs**. Installing the **same `<Id>`** with a **different** `SourceLocation` host often fails. Remove the older Canary add-in from **My add-ins → Custom add-ins**, then upload again.

### If upload fails with “XML Schema Validation Error”

Microsoft’s XSD expects:

- Outer `VersionOverrides` with `xsi:type="VersionOverridesV1_0"` (do **not** use only `Version="1.0"`).
- Inner `VersionOverrides` with `xmlns="http://schemas.microsoft.com/office/mailappversionoverrides/1.1"` and `xsi:type="VersionOverridesV1_1"` when using **`SupportsPinning`** on the task pane.
- `Group` must use `<Label resid="…"/>` only — not a `label="…"` attribute on `Group`.

After changing the manifest, validate with Microsoft’s tooling if needed, e.g. `npx office-addin-manifest validate manifest.xml`.

### Ship checklist (CI / deploy)

1. From `frontend/`, run `npm run build`.
2. Deploy the built `dist/` (Docker `frontend` image copies `dist` to nginx).
3. Confirm these URLs over **HTTPS**:
   - `/outlook-addin/manifest.xml`
   - `/outlook-addin/taskpane.html`
   - `/outlook-addin/auth-callback.html`
   - `/icons/icon64.png`, `icon128.png`, `icon16.png`, `icon32.png`, `icon80.png`

This add-in gives Outlook on the web and Outlook desktop:

1. **File to Case** (read mode) — save the **currently open message** into a Canary matter.
2. **Compose from matter** (compose mode) — merge a precedent, set recipient, and attach case files via `POST /api/mail-plugin/cases/{id}/compose-bundle` **without Microsoft Graph**.

### File to Case (read)

1. Upload a parent **`.eml`** (a **synthetic** RFC822 built from Outlook item fields + body).
2. Upload each **file attachment** as a **child** of that parent via `parent_file_id`.

### Compose from matter (no Graph)

1. Open or start a **compose** message in Outlook.
2. Ribbon → **Compose from matter** → **Connect to Canary…**, pick matter, precedent, recipient, and case files.
3. **Apply to message** — merge, attachments, pending-send, and (when supported) the **Canary** category on the draft.
4. **Send** — `OnMessageSend` saves a synthetic `.eml` (+ attachments) to the linked matter via pending-send.

**Important:** Compose send filing requires **`OnMessageSend`** in `manifest.xml` (v1.0.10+). You must click **Apply to message** before sending so pending-send is set for the matter.

It calls the same backend routes as the main app: `POST /api/auth/plugin/authorize`, `POST /api/auth/plugin/token`, `GET /api/cases`, `POST /api/cases/{case_id}/files`, `POST /api/mail-plugin/cases/{case_id}/compose-bundle`.

Sign-in opens `/connect/mail-plugin` in an Office dialog so passkeys and authenticator apps work (inline password login is not used).

## Central deployment (preferred)

**Feasibility:** Yes — Microsoft 365 lets administrators deploy Outlook add-ins **to the whole tenant** (or to specific users/groups) by uploading this manifest, without each person sideloading manually.

**Who does it:** Someone with permission in the [Microsoft 365 admin center](https://admin.microsoft.com/) (roles such as **Global Administrator** or **Azure AD Application Administrator**, depending on your tenant’s setup).

**Where to start:** Microsoft’s guide [Deploy add-ins in the admin center](https://learn.microsoft.com/microsoft-365/admin/manage/manage-deployment-of-add-ins) describes **Centralized Deployment** / **Integrated apps**.

## Sideload (dev / single-user)

**Get Add-ins** → **My add-ins** → **Custom add-ins** → add from file — search Microsoft’s docs for [sideload Outlook add-ins](https://learn.microsoft.com/search/?terms=sideload%20outlook%20add-in).

Use `frontend/public/outlook-addin/manifest.xml` or download from `https://YOUR_HOST/outlook-addin/manifest.xml`.

### Admin center shows the add-in as **Off** (grey icon)

In **Microsoft 365 admin center → Settings → Integrated apps**, **Off** means the deployment is **not enabled for users**. Turn **On**, assign users, wait a few minutes, sign out and back into OWA.

### Add-in installed but nothing appears in Outlook (OWA)

**Blank white task pane**

Outlook’s iframe never loaded `taskpane.html`. Check every URL in the sideloaded manifest points at your live Canary host. Sanity-check `https://YOUR_HOST/outlook-addin/taskpane.html` in a normal browser tab — you should see the sign-in form. Open an **email** first, then launch from **Apps** or the message toolbar.

**Server checks**

| URL | Expect |
|-----|--------|
| `…/outlook-addin/manifest.xml` | HTTP **200**, `Content-Type: text/xml` |
| `…/outlook-addin/taskpane.html` | HTTP **200** |
| `…/icons/icon16.png`, `icon32.png`, `icon80.png` | HTTP **200**, PNG |

**Where to look in Outlook**

1. **Open a message** — not the inbox list.
2. **Apps** (grid) or message toolbar **Canary** group → **File to Case** / **Compose from matter**.

## Sign-in and 2FA

The sign-in dialog includes an optional **2FA / TOTP code** field (`totp_code` on `POST /api/auth/login`).

## Limitations (v1)

- **Synthetic .eml**: Built from Outlook’s JavaScript API, not raw MIME from Microsoft’s servers.
- **Cloud / linked attachments** (OneDrive references) are skipped until Graph-based download is added.

## API base URL

The add-in assumes the API is on the **same origin** as the UI, at `/api`.

## Security

Treat the stored JWT like the main web app’s token; use **HTTPS** only.
