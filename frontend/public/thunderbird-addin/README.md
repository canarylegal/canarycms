# Canary — Thunderbird add-on

MailExtension (Manifest V2) to **file mail to a matter**, **compose with merge + attachments**, and apply the **Canary** message tag on **incoming** mail (Apply / File to matter). **Sent** replies are saved to the matter on send but are **not** tagged in Thunderbird.

The Outlook add-in lives at `../frontend/public/outlook-addin/`.

## Source folder vs `frontend/public/thunderbird-addin/`

There are two copies of the add-on runtime in the repo:

| Path | Role |
|------|------|
| **`thunderbird-addin/`** (this folder, repo root) | **Source of truth** — edit here. Includes release tooling (`package.json`, `scripts/`). |
| **`frontend/public/thunderbird-addin/`** | **Synced runtime copy** for the web frontend Docker build (no release tooling). Updated when you run `npm run build` in `frontend/`. |

Sync from `frontend/`:

```bash
node scripts/sync-and-verify-thunderbird-addin.mjs
```

---

## User flow (compose)

1. Set your Canary site URL, then **Connect to Canary…** (opens sign-in in your **default browser** — passkeys and authenticator apps supported). When authorisation finishes, return to Thunderbird.
2. Open or focus a compose window → click **Canary** on the compose toolbar.
3. Pick matter (or **None**), contact, precedent, folder, attachments → **Apply to message**.
4. On a **reply**, the incoming message is filed and tagged immediately.
5. **Send** — the sent message is filed to the matter as its own `.eml` (no Thunderbird tag on sent mail).

---

## Load temporarily (development only)

**Tools** → **Add-ons and Themes** → **Debug Add-ons** → **Load Temporary Add-on…** → this folder’s `manifest.json`.

Temporary add-ons are **removed when Thunderbird restarts**. Use this while developing — **not** for firm rollout.

---

## Install permanently (recommended for firms)

Release Thunderbird only keeps **signed** add-ons after restart. Unsigned temporary loads do not persist.

### Firm IT — install a signed `.xpi`

1. Download **`canary-thunderbird-{version}.xpi`** from [canarylegalsoftware.co.uk/thunderbird/](https://canarylegalsoftware.co.uk/thunderbird/) (or your vendor).
2. In Thunderbird: **Add-ons and Themes** → gear menu → **Install Add-on From File…** → choose the `.xpi`.
3. Confirm the add-on appears as **Canary — file to matter** and survives a Thunderbird restart.
4. Each user opens **Server & sign-in** once and enters **their firm’s** Canary URL (e.g. `https://canary.yourfirm.example` — not the download host).

**Updates:** builds signed with `update_url` in the manifest auto-update from `https://canarylegalsoftware.co.uk/thunderbird/updates.json` (Thunderbird checks about daily). First install after enabling auto-update may still be manual if users only have an older build without `update_url`.

### Central hosting (all firms)

Signed releases and the update manifest are published to **`https://canarylegalsoftware.co.uk/thunderbird/`** (vendor domain — same `.xpi` for every firm). See **`hosting/README.md`** for WordPress upload steps.

After `npm run sign`:

```bash
npm run publish-hosting   # → hosting/updates.json + hosting/canary-thunderbird-{version}.xpi
```

Upload the contents of **`hosting/`** to `public_html/thunderbird/` on the WordPress server.

### Enterprise pre-install (optional)

IT can pre-install the **signed** `.xpi` using Thunderbird [enterprise distribution](https://wiki.mozilla.org/Thunderbird/Enterprise) (`distribution.ini` / policies). Host the signed XPI on an internal HTTPS URL your workstations trust.

---

## Sign a release (maintainers)

Automated packaging and signing use [web-ext](https://extensionworkshop.com/documentation/develop/web-ext-command-reference/) against **Thunderbird Add-ons (ATN)**, not Firefox AMO.

### One-time ATN setup

1. Create a developer account at [addons.thunderbird.net/developers](https://addons.thunderbird.net/developers/).
2. Generate API credentials at [Developer hub → API key](https://addons.thunderbird.net/developers/addon/api/key/).
3. The add-on ID is fixed in `manifest.json`: **`canary-file@canarylegal.co.uk`**. The first successful sign creates the ATN listing (unlisted — not on the public store).

Store credentials securely (password manager or CI secrets). Never commit them.

### Local release

From this directory:

```bash
npm ci
npm run lint          # optional but recommended
npm run package       # unsigned zip → dist/canary-thunderbird-{version}.zip
npm run sign          # signed .xpi → dist/  (requires API credentials)
```

Or one step after credentials are exported:

```bash
export ATN_API_KEY='your-jwt-issuer'
export ATN_API_SECRET='your-jwt-secret'
npm run release              # lint → package → sign → publish-hosting
```

`npm run sign` reads `ATN_API_KEY` / `ATN_API_SECRET` (or `WEB_EXT_API_KEY` / `WEB_EXT_API_SECRET`). Optional override: `ATN_AMO_BASE_URL` (default `https://addons.thunderbird.net/api/v4`).

**Output:**

- `dist/canary-thunderbird-{version}.zip` (unsigned package)
- `dist/canary-thunderbird-{version}.xpi` (signed)
- `hosting/` — upload to **canarylegalsoftware.co.uk/thunderbird/** (see `hosting/README.md`)

**Version bumps:** edit `version` in `manifest.json` before each release ATN accepts as a new version. The manifest includes `applications.gecko.update_url`; re-sign after changing it.

### GitHub Actions (optional)

Workflow **Thunderbird add-in release** (`.github/workflows/thunderbird-addin-release.yml`):

| Trigger | Behaviour |
|---------|-----------|
| Tag `thunderbird-v*` (e.g. `thunderbird-v1.5.0`) | Lint, package, sign (if secrets set), upload artifact, attach to GitHub Release |
| Manual **workflow_dispatch** | Lint + package always; sign when **Sign with ATN** is checked and secrets exist |

Repository secrets (Settings → Secrets → Actions):

| Secret | Value |
|--------|--------|
| `ATN_API_KEY` | JWT issuer from ATN developer hub |
| `ATN_API_SECRET` | JWT secret from ATN developer hub |

CI on every push/PR runs **lint + package** only (no signing, no secrets required).

### Manual fallback (no API access)

1. `npm run package`
2. Upload `dist/canary-thunderbird-{version}.zip` at [addons.thunderbird.net/developers](https://addons.thunderbird.net/developers/) as an **unlisted** add-on.
3. Download the signed `.xpi` from the developer hub and distribute it.

---

## API

Uses configurable origin + `/api` (Bearer JWT). Main routes:

- `POST /api/mail-plugin/cases/{case_id}/compose-bundle`
- `PUT|DELETE /api/mail-plugin/pending-send`
- `POST /api/cases/{case_id}/files` (multipart; `folder`, `parent_file_id`, `compose_*` form fields)

---

## Reference

- [Thunderbird WebExtension APIs](https://webextension-api.thunderbird.net/) — `messages`, `compose`, `composeAction`, `menus`.
- [Add-on signing overview](https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/)
- [web-ext sign](https://extensionworkshop.com/documentation/develop/web-ext-command-reference/#web-ext-sign)
