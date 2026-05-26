# Canary — Outlook add-in (“File to Case”)

**Default deployment URL (manifest):** [https://testing.canarylegalsoftware.co.uk](https://testing.canarylegalsoftware.co.uk/) — task pane and login live under `/outlook-addin/`.

**Dev deployment:** use **`manifest.dev.xml`** for `https://dev.canarylegalsoftware.co.uk` (distinct add-in **`<Id>`** from testing/local). For other named hosts, copy that file and replace the origin + generate a new GUID in `<Id>`.

Office add-in manifests **must** use absolute `https://…` URLs in the XML; there is no supported “one file for every host” upload without generating a manifest per origin (or a build step that substitutes the origin).

### If upload fails with “already installed elsewhere”

Outlook ties an add-in identity to **`<Id>`** and the **manifest URLs**. Installing the **same `<Id>`** with a **different** `SourceLocation` host often fails. Fix by either:

1. **Remove** the older Canary add-in (testing / other host) from **My add-ins → Custom add-ins**, then upload the new manifest; or  
2. Use a manifest that already has a **new GUID** in `<Id>` (as in `manifest.dev.xml` vs `manifest.xml`).

### If upload fails with “XML Schema Validation Error”

Microsoft’s XSD expects:

- Outer `VersionOverrides` with `xsi:type="VersionOverridesV1_0"` (do **not** use only `Version="1.0"`).
- Inner `VersionOverrides` with `xmlns="http://schemas.microsoft.com/office/mailappversionoverrides/1.1"` and `xsi:type="VersionOverridesV1_1"` when using **`SupportsPinning`** on the task pane.
- `Group` must use `<Label resid="…"/>` only — not a `label="…"` attribute on `Group`.

After changing the manifest, validate with Microsoft’s tooling if needed, e.g. `npx office-addin-manifest validate manifest.xml`.

### Ship checklist (CI / deploy)

1. From `frontend/`, run `npm run build`. If you use `scripts/verify-outlook-addin.mjs`, it expects `dist/outlook-addin/` to include `manifest.xml`, `manifest.local.xml`, and `manifest.dev.xml`.
2. Deploy the built `dist/` (Docker `frontend` image already copies `dist` to nginx).
3. Confirm these URLs over **HTTPS** (or HTTP for local only):
   - `/outlook-addin/taskpane.html`
   - `/outlook-addin/canary-login.html`
   - `/favicon.png`
4. Give IT **`manifest.xml`** for **central deployment** to Microsoft 365 (not `manifest.local.xml`).

### Local sideload (developers)

Use **`manifest.local.xml`** with **Vite** on `https://localhost:5173` (Outlook allows HTTPS localhost for sideloading in many setups; use the dev tools your org documents). It has a different add-in `<Id>` so it does not collide with the testing host manifest.

This add-in gives Outlook on the web and Outlook desktop:

1. **File to Case** (read mode) — save the **currently open message** into a Canary matter.
2. **Compose from matter** (compose mode, v1.0.8+) — merge a precedent, set recipient, and attach case files via `POST /api/mail-plugin/cases/{id}/compose-bundle` **without Microsoft Graph**.

### File to Case (read)

1. Upload a parent **`.eml`** (a **synthetic** RFC822 built from Outlook item fields + body).
2. Upload each **file attachment** as a **child** of that parent via `parent_file_id`.

### Compose from matter (no Graph)

1. Open or start a **compose** message in Outlook.
2. Ribbon → **Compose from matter** → sign in, pick matter, precedent, recipient, and case files.
3. **Apply to message** — uses Office.js `addFileAttachmentFromBase64Async` (same bytes as the Thunderbird add-in).
4. On send, **OnMessageSend** files the message to the linked matter (via pending-send).

It calls the same backend routes as the main app: `POST /api/auth/login`, `GET /api/cases`, `POST /api/cases/{case_id}/files`, `POST /api/mail-plugin/cases/{case_id}/compose-bundle`.

## Central deployment (preferred)

**Feasibility:** Yes — Microsoft 365 lets administrators deploy Outlook add-ins **to the whole tenant** (or to specific users/groups) by uploading this manifest, without each person sideloading manually.

**Who does it:** Someone with permission in the [Microsoft 365 admin center](https://admin.microsoft.com/) (roles such as **Global Administrator** or **Azure AD Application Administrator**, depending on your tenant’s setup).

**Where to start:** Microsoft’s guide [Deploy add-ins in the admin center](https://learn.microsoft.com/microsoft-365/admin/manage/manage-deployment-of-add-ins) describes **Centralized Deployment** / **Integrated apps**. You upload `manifest.xml` and assign which users or groups receive the add-in.

**Checklist before asking IT to deploy:**

- The site serves HTTPS and these URLs return **200** in a browser:
  - `https://testing.canarylegalsoftware.co.uk/outlook-addin/taskpane.html`
  - `https://testing.canarylegalsoftware.co.uk/outlook-addin/compose-pane.html`
  - `https://testing.canarylegalsoftware.co.uk/outlook-addin/attach-picker.html`
  - `https://testing.canarylegalsoftware.co.uk/outlook-addin/canary-login.html`
  - `icons/icon64.png` (manifest ``IconUrl``), `icon128.png` (``HighResolutionIconUrl``), plus `icon16` / `icon32` / `icon80` for the ribbon (generated from `public/favicon.png` via `scripts/generate-outlook-icons.py`)
- The API is reachable from the same host at `/api` (same pattern as the main Canary web app).

If your production host differs from testing, edit **every** URL in `manifest.xml` to match that origin (no trailing slash), then redeploy the frontend build.

## Sideload (dev / single-user)

For quick tests without admin deployment: **Get Add-ins** → **My add-ins** → **Custom add-ins** → add from file — exact steps change over time; search Microsoft’s docs for [sideload Outlook add-ins](https://learn.microsoft.com/search/?terms=sideload%20outlook%20add-in).

## Sign-in and 2FA

Canary does not force 2FA globally, but users who **have turned on 2FA** on their account can still use the add-in: the sign-in dialog includes an optional **2FA / TOTP code** field, which maps to `totp_code` on `POST /api/auth/login` (same as the main web app). Users leave it blank when 2FA is off.

## Limitations (v1)

- **Synthetic .eml**: The add-in builds the message from Outlook’s JavaScript API rather than downloading the **exact raw MIME** from Microsoft’s servers. For byte-for-byte parity with an IMAP export, a future version could use **Microsoft Graph** (see below).
- **IMAP “filed” badges** in Roundcube use `source_imap_mbox` / `source_imap_uid`. This add-in does not set those. Outlook-side “already filed” badges would need a separate design (e.g. keyed by internet message id).
- **Cloud / linked attachments** (OneDrive references) are skipped until Graph-based download is added.

## What “Azure AD / Microsoft Graph” meant (plain English)

You don’t need to configure this for the current add-in.

- **Microsoft Graph** is Microsoft’s **HTTPS API** for mail, calendar, and files in Microsoft 365. A future enhancement could call Graph to fetch the **full raw email** (RFC822) for an open message, which matches what Roundcube gets over IMAP.
- **Azure AD** (now often called **Entra ID**) is Microsoft’s **identity** system. Apps that call Graph usually register in Azure and ask an admin for consent. That’s separate from signing in to Canary with email + password + optional TOTP in the add-in dialog.

So: **today’s plugin** = sign in to **Canary** only. **Graph/Azure** = optional later step if you want Microsoft-hosted raw MIME and richer attachment handling.

## API base URL

The add-in assumes the API is on the **same origin** as the UI, at `/api`. If the API is on another host, extend `taskpane.js` / `canary-login.html` (e.g. a small `config.json`).

## Security

Treat the stored JWT like the main web app’s token: roaming settings follow the mailbox; use **HTTPS** only and follow your org’s device policies.
