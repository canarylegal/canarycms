# Canary CMS — deployment guide

Assumes you already own a domain (e.g. `canary.yourfirm.co.uk`) and a Linux server with Docker. Canary’s production stack is Docker Compose: an nginx frontend (port 8080 by default) proxies `/api`, WebDAV, ONLYOFFICE, and CalDAV to internal services.

---

## 1. Prerequisites

- Linux host with Docker and Docker Compose
- DNS control for your domain
- TLS termination (Cloudflare proxy, or host nginx + Let’s Encrypt)
- Ports open on the server **only** as needed (typically 443 from the internet; Postgres/backend ports can stay localhost-only)

---

## 2. DNS

Point your hostname at the server (or Cloudflare):

| Type | Name | Value |
|------|------|--------|
| A (or CNAME) | `canary` (or `@`) | Your server IP, or Cloudflare proxy |

Example: `https://canary.yourfirm.co.uk` → your server.

If using **Cloudflare** (orange cloud / “Proxied”): TLS and WAF live at Cloudflare; origin can listen on HTTP (8080) on a private/firewalled port.

---

## 3. Install Canary on the server

```bash
git clone https://github.com/canarylegal/canarycms.git /opt/canarycms
cd /opt/canarycms
# Prefer a release tag for production (see CHANGELOG.md / GitHub Releases)
git checkout v1.0.0   # or latest vX.Y.Z
cp .env.example .env
```

**Do not** start Compose until you replace every `CHANGE_ME_*` secret in `.env`. Backend startup rejects those placeholders.

Generate secrets (run each command once; paste results into `.env`):

```bash
# JWT signing (sessions) — 64 hex chars is fine
openssl rand -hex 32

# Data encryption (stored IMAP/portal/CalDAV secrets)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Other required secrets
openssl rand -hex 32   # ONLYOFFICE_JWT_SECRET
openssl rand -hex 32   # ONLYOFFICE_SECURE_LINK_SECRET
openssl rand -hex 16   # MASTER_ADMIN_LOGIN (save securely — break-glass recovery login id)
openssl rand -hex 32   # MASTER_ADMIN_PASSWORD (save securely)
python3 -c "import pyotp; print(pyotp.random_base32())"   # MASTER_ADMIN_TOTP_SECRET (authenticator app)
openssl rand -hex 16   # POSTGRES_PASSWORD
```

Edit `.env` — minimum for a public site:

```bash
COMPOSE_PROFILES=prod
COMPOSE_PROJECT_NAME=canary

CANARY_PUBLIC_URL=https://canary.yourfirm.co.uk
CANARY_CORS_ORIGINS=https://canary.yourfirm.co.uk
# Leave private-HTTP CORS off in production; list any Tailscale Origin explicitly in CANARY_CORS_ORIGINS instead.
# CANARY_CORS_ALLOW_PRIVATE_HTTP=1
ONLYOFFICE_DS_PUBLIC_URL=https://canary.yourfirm.co.uk/office-ds
CANARY_CALDAV_PUBLIC_URL=https://canary.yourfirm.co.uk
ONLYOFFICE_CALLBACK_REQUIRE_JWT=1

WEBAUTHN_RP_ID=canary.yourfirm.co.uk
WEBAUTHN_RP_NAME=Canary

# Trust your reverse proxy for HTTPS and client IP (Cloudflare/nginx/cloudflared on loopback)
CANARY_BEHIND_REVERSE_PROXY=1
CANARY_PROXY_TRUSTED_HOSTS=127.0.0.1,172.16.0.0/12,::1

# Prod nginx: loopback (cloudflared) + Tailscale admin — replace with `tailscale ip -4` on each host
FRONTEND_PORT_PUBLISH=127.0.0.1:8080:80
FRONTEND_TAILSCALE_PORT_PUBLISH=100.x.x.x:8080:80
BACKEND_PORT_PUBLISH=127.0.0.1:8004:8000

# Optional: public GitHub for Admin → Deploy “behind?” checks (no token; no in-app update).
# Default latest-release compares to the newest GitHub Release tip (fits tag-pinned installs).
# Use CANARY_GITHUB_DEPLOY_REF=main only if you intentionally track floating main.
CANARY_GITHUB_DEPLOY_OWNER=canarylegal
CANARY_GITHUB_DEPLOY_REPO=canarycms
CANARY_GITHUB_DEPLOY_REF=latest-release
```

Build and start:

```bash
GIT_COMMIT=$(git rev-parse HEAD) docker compose --profile prod build
docker compose --profile prod up -d
docker compose ps
curl -sS http://127.0.0.1:8080/api/health
```

Wait until `canary-backend` is **healthy** (migrations run automatically on startup).

After first deploy on an existing database with encrypted secrets, run once inside the backend container:

```bash
docker compose exec backend python scripts/reencrypt_data_secrets.py
```

### Updating an existing install

Admin → Deploy (and the optional post-login prompt) only **notify** when GitHub is ahead of this build. There is no in-app “Update now”, and the backend does **not** mount `docker.sock`.

The former GUI Compose updater code is **intentionally retained** in the repo (fail-closed stubs + implementation under `backend/app/local_compose_update.py` and `backend/app/compose_deploy_job.py`) so audits do not treat it as unmarked dead code and so any future re-enablement requires an explicit security review. It is not a supported production path.

**Prefer a known release**, not an unreviewed `main` tip:

```bash
cd /path/to/canarycms
git fetch --tags origin
git checkout vX.Y.Z   # or: git checkout <full-commit-sha>
GIT_COMMIT=$(git rev-parse HEAD) docker compose --profile prod build
docker compose --profile prod up -d
```

Fast-forward without a tag (still pin the SHA you verified):

```bash
git pull --ff-only
GIT_COMMIT=$(git rev-parse HEAD) docker compose --profile prod build
docker compose --profile prod up -d
```

Bake `GIT_COMMIT` so Admin → Deploy can compare correctly. With the default
`CANARY_GITHUB_DEPLOY_REF=latest-release`, a host on `v1.0.0` stays quiet until a newer
GitHub Release is published (it will **not** nag for every commit on `main`).

---

## 4. Reverse proxy (origin)

Traffic should reach the **frontend** container (nginx), not the backend directly.

**Option A — origin nginx** forwarding to `127.0.0.1:8080`:

```nginx
# /etc/nginx/sites-available/canary (example)
server {
    listen 443 ssl http2;
    server_name canary.yourfirm.co.uk;
    # ssl_certificate ... (Let’s Encrypt or Cloudflare origin cert)

    client_max_body_size 500m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
    }
}
```

**Option B — Cloudflare only:** proxy `canary.yourfirm.co.uk` to your origin IP:8080 (or through a tunnel). Set SSL mode to **Full (strict)** if you use an origin certificate.

---

## 5. Create the first firm admin account

Set `MASTER_ADMIN_LOGIN`, `MASTER_ADMIN_PASSWORD`, and `MASTER_ADMIN_TOTP_SECRET` in `.env` (long random hex strings are fine for login/password; the login id need not be a real e-mail address). The backend **will not start** without these values. Enrol the TOTP secret in an authenticator app (issuer `TOTP_ISSUER`, account name = your master login id).

1. Sign in at `https://canary.yourfirm.co.uk` using the master recovery login id, password, and authenticator code.
2. You will see the **Recovery console** only (users and security policy — no case access).
3. Create a firm administrator under **Users** (role `admin` or a permission category with **Admin**).
4. Sign out and sign in as that firm admin for day-to-day use. Reserve the master login for recovery.

**Break-glass recovery (server-side only):** edit `.env` and restart the backend to bypass or reset master 2FA:

- Set `MASTER_ADMIN_REQUIRE_2FA=false` to sign in with password only (temporary).
- Replace `MASTER_ADMIN_TOTP_SECRET` with a new base32 secret and re-enrol your authenticator app.
- Replace `MASTER_ADMIN_PASSWORD` to rotate the master password.

**Post-login setup (firm admin):**

1. **Admin → Permission categories** — review “Standard fee earner” (created by migration) or add categories for your roles
2. **Admin → Users** — new staff **must** have a permission category (role `user`)
3. **Admin → Firm settings** — firm name, optional mandatory 2FA before go-live
4. **Admin → E-mail** — SMTP/Graph for password reset and alerts

---

## 6. Web Application Firewall (WAF)

A **WAF** filters HTTP traffic **before** it hits your server. Canary’s in-app login rate limits protect auth inside the application; a WAF adds network-edge protection.

### If you use Cloudflare (recommended for a public site)

1. Add the site to Cloudflare; set DNS to **Proxied** (orange cloud).
2. **SSL/TLS → Overview:** Full (strict).
3. **Security → Settings:** enable **Bot Fight Mode** (or Super Bot Fight on paid plans).
4. **Security → WAF → Custom rules** — add rules like:

| Rule name | Expression | Action |
|-----------|------------|--------|
| Rate limit login | `(http.request.uri.path eq "/api/auth/login" and http.request.method eq "POST")` | Rate limit — 10 requests / 1 minute / IP → Block |
| Rate limit forgot password | `(http.request.uri.path eq "/api/auth/forgot-password" and http.request.method eq "POST")` | Rate limit — 5 requests / 5 minutes / IP → Block |
| Block common probes | `(http.request.uri.path contains "/wp-admin" or http.request.uri.path contains "/.env")` | Block |

5. **Security → WAF → Managed rules:** turn on **Cloudflare Managed Ruleset**.
6. Optional: rate-limit `/api/*` — e.g. 100 req/min per IP (tune for normal use).

Cloudflare sees the visitor’s IP; Canary receives it via `X-Forwarded-For` when `CANARY_BEHIND_REVERSE_PROXY=1`.

### If you use nginx only (no Cloudflare)

- Use **fail2ban** or nginx `limit_req` on `/api/auth/login` and `/api/auth/forgot-password`
- Keep Postgres and backend bound to `127.0.0.1`
- Firewall the host: allow 443 (and SSH from admin IPs only)

WAF and in-app rate limits **complement** each other.

---

## 7. Go-live checklist

### Secrets & identity (Compose will not start without these)
- [ ] `JWT_SECRET` generated (`openssl rand -hex 32`) — not a `CHANGE_ME_*` placeholder
- [ ] `DATA_ENCRYPTION_KEY` generated (Fernet) — not a placeholder; re-encrypt script run if migrating existing data
- [ ] `POSTGRES_PASSWORD` generated and recorded offline
- [ ] `ONLYOFFICE_JWT_SECRET` and `ONLYOFFICE_SECURE_LINK_SECRET` generated
- [ ] `MASTER_ADMIN_LOGIN`, `MASTER_ADMIN_PASSWORD`, and `MASTER_ADMIN_TOTP_SECRET` generated and stored securely (not in git)
- [ ] `MASTER_ADMIN_REQUIRE_2FA=true` with a valid authenticator enrolment (or temporary `false` only for break-glass)

### Public URLs & auth
- [ ] `CANARY_PUBLIC_URL`, `CANARY_CORS_ORIGINS`, `ONLYOFFICE_DS_PUBLIC_URL`, `CANARY_CALDAV_PUBLIC_URL` are the live HTTPS origins
- [ ] `WEBAUTHN_RP_ID` matches the hostname staff open (no port)
- [ ] `ONLYOFFICE_CALLBACK_REQUIRE_JWT=1` (Compose default; ONLYOFFICE 9.x sends signed callbacks — set `0` only for legacy DS)
- [ ] Behind TLS terminator: `CANARY_BEHIND_REVERSE_PROXY=1` and tight `CANARY_PROXY_TRUSTED_HOSTS`

### Access control & ops
- [ ] Checkout pinned to a release tag (`vX.Y.Z`), not floating `main`
- [ ] `CANARY_GITHUB_DEPLOY_REF=latest-release` (default) so Admin → Deploy tracks Releases, not `main`
- [ ] `GIT_COMMIT=$(git rev-parse HEAD)` baked into the backend image at build time
- [ ] All staff users have permission categories
- [ ] Mandatory 2FA enabled for staff when ready
- [ ] WAF / rate rules on login endpoints
- [ ] Postgres and backend publish ports stay on `127.0.0.1` (not the public internet)
- [ ] **Backups:** Postgres volume (`db-data`) and `./data/files` on a schedule
- [ ] **Restore drill:** document how to restore Postgres (`docker compose … exec` / volume restore) and files from the latest backup; run once before go-live
- [ ] **Outlook add-in** deployed (if the firm uses Microsoft 365) — see §8.1
- [ ] **Thunderbird add-on** signed `.xpi` distributed (if the firm uses Thunderbird) — see §8.2

---

## 8. Mail client add-ons (Outlook & Thunderbird)

Canary connects to users’ mail clients through two optional add-ons. Both use the **same Canary site URL** and staff login as the web app (`POST /api/auth/login` → Bearer JWT on `/api`). Neither replaces the mail client — they file mail to matters and support compose-from-matter workflows.

| | **Outlook add-in** | **Thunderbird add-on** |
|---|-------------------|------------------------|
| **Shipped with** | Frontend Docker image (nginx serves `/outlook-addin/…`) | Separate [canary-thunderbird repository](https://github.com/canarylegal/canary-thunderbird); GitHub Release publication pending |
| **Typical deploy** | Microsoft 365 admin center (tenant-wide) | Manual install once, then auto-update from vendor host |
| **User sign-in** | Task pane in Outlook | Toolbar **Server & sign-in** once per profile |
| **Graph on server** | Optional but recommended (drafts, categories) | Not used |

Ensure `CANARY_PUBLIC_URL` in `.env` is the **exact HTTPS origin** staff will use (no trailing slash). Wrong values break add-in URLs and Thunderbird server configuration.

---

### 8.1 Outlook add-in

The Outlook add-in provides **File to Case** (read mode) and **Compose from matter** (compose mode) in Outlook on the web and Outlook desktop.

#### Prerequisites

- Canary frontend deployed with **`CANARY_PUBLIC_URL`** set correctly before `docker compose build` (the build rewrites `manifest.xml` URLs to match).
- **HTTPS** on the public hostname (Office will not load add-in pages over plain HTTP).
- For **Compose from matter** send filing and category behaviour: server-side **Microsoft Graph** configured (§8.3 below) is recommended, though the add-in login itself does not use Graph.

#### Deploy with the main stack

The add-in is included in the frontend build. After deploy, confirm these URLs return **HTTP 200** over HTTPS:

| URL | Expect |
|-----|--------|
| `https://canary.yourfirm.co.uk/outlook-addin/manifest.xml` | XML manifest, `Content-Type: text/xml` |
| `https://canary.yourfirm.co.uk/outlook-addin/taskpane.html` | Sign-in / task UI |
| `https://canary.yourfirm.co.uk/outlook-addin/auth-callback.html` | OAuth-style callback for add-in connect |
| `https://canary.yourfirm.co.uk/icons/icon16.png` (and 32, 64, 80, 128) | PNG icons |

If you change `CANARY_PUBLIC_URL`, rebuild and redeploy the **frontend** image:

```bash
cd /opt/canarycms
git pull
GIT_COMMIT=$(git rev-parse HEAD) docker compose --profile prod build frontend
docker compose --profile prod up -d
```

#### Centralized deployment (recommended for firms)

**Who:** Microsoft 365 administrator (Global Administrator or equivalent).

**Where:** [Microsoft 365 admin center](https://admin.microsoft.com/) → **Settings** → **Integrated apps** → **Upload custom apps** (Centralized Deployment).

**Steps:**

1. Deploy Canary so the live manifest matches your hostname (see above).
2. Upload using **one** of:
   - **Manifest URL:** `https://canary.yourfirm.co.uk/outlook-addin/manifest.xml`, or
   - **From device:** the built `manifest.xml` from your server (must use the **same** host as production).
3. Turn the deployment **On** and **assign users or groups**.
4. Wait a few minutes; users may need to sign out and back into Outlook on the web.

**Pilot / single user:** Outlook → **Get Add-ins** → **My add-ins** → **Custom add-ins** → add from file or URL (same manifest as above).

#### User workflow

1. Open an **email message** (not the inbox list alone).
2. Launch **File to Case** or **Compose from matter** from the message toolbar or **Apps** grid.
3. Sign in with Canary staff credentials (optional **2FA / TOTP** field if enabled on the account).
4. **File to Case:** saves a synthetic `.eml` (+ attachments) to the chosen matter.
5. **Compose from matter:** pick matter, precedent, recipient, attachments → **Apply to message** → send (requires **Apply** before send so pending-send is registered).

#### Troubleshooting (Outlook)

| Symptom | Likely cause |
|---------|----------------|
| Admin center shows add-in **Off** | Enable deployment and assign users in Integrated apps. |
| Blank white task pane | Manifest URLs wrong or frontend not reachable; open `taskpane.html` in a normal browser tab. |
| “Already installed elsewhere” | Same add-in `<Id>` with a **different** host — remove old Canary add-in from **My add-ins → Custom add-ins**, redeploy. |
| Upload XML validation error | Use the repo’s current `manifest.xml` schema; validate with `npx office-addin-manifest validate manifest.xml` if needed. |
| Compose send does not file to matter | User must click **Apply to message** before send; manifest must include `OnMessageSend` (v1.0.10+). |

#### Outlook updates

After add-in code or manifest changes: bump `<Version>` in `manifest.xml`, rebuild frontend, redeploy, and refresh the M365 deployment if Microsoft prompts for an updated manifest.

---

#### Outlook source ownership and hosting bundle

The source, manifest template, build tools and tests are maintained in [canary-outlook](https://github.com/canarylegal/canary-outlook). CMS consumes the reviewed, checksum-pinned bundle under `frontend/vendor/canary-outlook/`. `npm run build` stages it before Vite and renders the manifest and Office allowlist afterward using the existing `CANARY_PUBLIC_URL`; `npm run dev` also stages the bundle.

Do not edit generated `frontend/public/outlook-addin/` files. Update all three vendor bundle files from a clean standalone build in a reviewed CMS change. No network download occurs during staging. Required icons are compared with the shared CMS icons before writing, so branding differences fail visibly.

Hosting remains on the existing CMS origin at `/outlook-addin/*`, `/icons/*` and `/.well-known/microsoft-officeaddins-allowed.json`. Authentication callbacks, nginx configuration, server APIs and manifest identity are unchanged. This source separation does not deploy or register an add-in with Microsoft.

### 8.2 Thunderbird add-on

The Thunderbird add-on provides **file to matter**, **compose with merge + attachments**, and a **Canary** tag on **incoming** mail. Sent mail is filed on send but is **not** tagged in Thunderbird.

#### Installation and updates

The extension source, tests and build tools are maintained separately in [canary-thunderbird](https://github.com/canarylegal/canary-thunderbird). The CMS build does not bundle or publish extension files.

Use a reviewed versioned XPI from that repository. GitHub Release publication is still pending; its configured automatic-update feed is not live yet. When releases are published, download from [GitHub Releases](https://github.com/canarylegal/canary-thunderbird/releases).

In Thunderbird 128 or later, open Add-ons and Themes, choose the gear menu, then Install Add-on From File. Select the XPI and connect to your firm's HTTPS Canary site using the Canary toolbar. Existing installations need a one-time manual installation to switch to the GitHub update channel; keep existing settings by installing over the old version rather than uninstalling.

The GitHub-channel manifest points at `https://github.com/canarylegal/canary-thunderbird/releases/latest/download/updates.json`. Each published feed points at a versioned XPI with its SHA-256 digest. Firms may manage updates under their own policy; the [Betterbird policy template](../deploy/betterbird/policies.json) remains an administrator-maintained integration example.

#### Maintainer boundary

Build and test the extension in its own repository (`npm test`, `npm run build`). No ATN submission, signing, extension release workflow or extension deployment runs from Canary CMS. GitHub Actions and background jobs remain disabled for this separation; no release is published.

Keep authentication/token endpoints, filing and compose APIs, OAuth callback pages and the web-bridge client in CMS. Validate changes to these contracts against the extension. Do not restore a second source copy under frontend/public.

#### User workflow (Thunderbird)

1. **Server & sign-in** once (Canary URL + staff credentials).
2. **Read mail:** message actions → file / apply Canary tag to incoming mail linked to a matter.
3. **Compose:** compose toolbar **Canary** → matter, contact, precedent, folder, attachments → **Apply to message** → send (reply filing happens on send).

#### Troubleshooting (Thunderbird)

| Symptom | Likely cause |
|---------|----------------|
| Add-on gone after restart | Was loaded as **temporary** unsigned add-on — install a **signed** `.xpi`. |
| Cannot sign in | Wrong server URL; check HTTPS and that `/api/health` works from a browser. |
| API errors | User lacks matter access; token expired — sign in again via **Server & sign-in**. |

---

### 8.3 Microsoft Graph (Outlook server-side, optional)

Graph is **optional** for basic Canary use but recommended when using Outlook **compose drafts**, **master category** seeding, or Graph fallback for the Canary category.

**Entra app registration** (application permissions, admin consent):

| Permission | Purpose |
|------------|---------|
| `Mail.ReadWrite` | Create/update messages (drafts, category fallback) |
| `MailboxSettings.ReadWrite` | Ensure Outlook master category list includes Canary |

**Backend `.env`:**

```bash
CANARY_MS_GRAPH_TENANT_ID=<Directory (tenant) ID>
CANARY_MS_GRAPH_CLIENT_ID=<Application (client) ID>
CANARY_MS_GRAPH_CLIENT_SECRET=<client secret>
# Optional:
CANARY_OUTLOOK_CATEGORY_NAME=Canary
CANARY_OUTLOOK_WEB_MAIL_BASE=https://outlook.office.com/mail
```

Restart the backend after changes. Canary user email should match the M365 mailbox UPN/SMTP used for Graph flows.

**Smoke test:** deploy Outlook add-in → open a message → **File to Case** → confirm filing; if Graph is configured, test **Compose from matter** and category behaviour.

---

## 9. Security features (reference)

| Feature | Env / location |
|---------|----------------|
| Encryption key split | `DATA_ENCRYPTION_KEY` vs `JWT_SECRET` |
| Staff login lockout | 5 failures / 15 min (default); see `STAFF_LOGIN_*` in `.env.example` |
| Permission categories | Required for staff users; “Standard fee earner” seeded by migration |
| ONLYOFFICE callback JWT | Required by default (`ONLYOFFICE_CALLBACK_REQUIRE_JWT=1` in Compose / `.env.example`). Set `0` only for legacy Document Server that cannot sign callbacks. |

---

Adjust hostnames, paths, and ports for your environment. Mail add-on maintainer detail also lives in [Canary Outlook](https://github.com/canarylegal/canary-outlook) and [Canary Thunderbird](https://github.com/canarylegal/canary-thunderbird).
