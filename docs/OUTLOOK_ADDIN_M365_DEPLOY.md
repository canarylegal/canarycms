# Outlook add-in — M365 work tenant deployment

## Symptom: “Added” in Custom add-ins but nothing on open messages (OWA)

The add-in server and manifest are fine when:

- `https://YOUR_HOST/outlook-addin/manifest.xml` returns **200**
- `npx office-addin-manifest validate` passes
- Icons are exact sizes under `/outlook-addin/icons/`

If the add-in **only** appears under **Get Add-ins → My add-ins → Custom add-ins** and **never** under **Apps** on an open email, Exchange Online is **not activating** user sideloads for that mailbox/tenant. This is common on **Microsoft 365 Business / Enterprise** accounts — not a Canary bug.

References: [Microsoft Q&A — sideloads but not in Apps](https://learn.microsoft.com/en-us/answers/questions/5641957/outlook-add-in-sideloads-successfully-on-outlook-w)

## Required fix: central deployment (IT admin)

1. Sign in to [Microsoft 365 admin center](https://admin.microsoft.com) as Global Administrator or Application Administrator.
2. **Settings → Integrated apps → Upload custom apps**.
3. Choose **Provide link to manifest file**.
4. URL (ribbon + task panes, sideload-safe):
   ```
   https://YOUR_CANARY_PUBLIC_URL/outlook-addin/manifest.xml
   ```
   For send-time filing (`OnMessageSend`), use instead:
   ```
   https://YOUR_CANARY_PUBLIC_URL/outlook-addin/manifest-with-send.xml
   ```
5. Complete the wizard, then set deployment status to **On** and assign users/groups.
6. Wait **15–60 minutes**. Users **sign out of Outlook on the web** and back in.
7. Open an **email message** → **Apps** (grid) or **Canary** on the message toolbar.

Remove any old **user sideload** of the same add-in first (same `<Id>`), or activation can conflict.

## Exchange Online settings (admin)

Run in **Exchange Online PowerShell** (https://admin.exchange.microsoft.com → PowerShell):

```powershell
# Organisation allows Office add-ins
Get-OrganizationConfig | Select AppsForOfficeEnabled
Set-OrganizationConfig -AppsForOfficeEnabled $true

# Per-mailbox (replace user)
Get-CASMailbox user@domain.com | Select AppsForOfficeEnabled
Set-CASMailbox -Identity user@domain.com -AppsForOfficeEnabled $true
```

In **Exchange admin center → Roles → User roles → Default Role Assignment Policy → Manage permissions**, ensure enabled:

- **My Custom Apps**
- **My Marketplace Apps**
- **My ReadWriteMailbox Apps**

## Diagnose sideload vs tenant block

| Test | URL | Meaning |
|------|-----|---------|
| Minimal manifest | `…/outlook-addin/manifest-minimal.xml` | No ribbon; should appear in **Apps** on a message if sideload activation works at all |
| Full manifest | `…/outlook-addin/manifest.xml` | Ribbon buttons + task panes |
| With send events | `…/outlook-addin/manifest-with-send.xml` | Admin deploy only |

Steps:

1. Remove all Canary custom add-ins.
2. Sideload **manifest-minimal.xml** (file or URL).
3. Open a **received email** → **Apps** on the message toolbar.

- **If minimal appears in Apps** → tenant allows sideload; use `manifest.xml` or switch to central deploy for production.
- **If minimal also missing** → tenant blocks user sideload activation → **central deploy is mandatory**.

## User checklist (after admin deploy)

1. Open **Outlook on the web** (not only the “Manage add-ins” popup).
2. Open a **message** (inbox list alone is not enough).
3. **Apps** on the message, or **Canary → File to Case** / **Compose from matter**.
4. First run: **Connect to Canary…** in the task pane.

## Canary URLs to allow

- `https://YOUR_HOST/outlook-addin/*`
- `https://YOUR_HOST/connect/mail-plugin`
- `https://YOUR_HOST/api/*`

No special Azure AD app registration is required for the current auth flow (dialog → Canary login → plugin token).
