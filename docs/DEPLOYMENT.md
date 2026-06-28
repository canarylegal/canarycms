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
cp .env.example .env
```

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

# Optional: disable GUI “Update now” on first install
CANARY_COMPOSE_UPDATE_ENABLED=0
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

- [ ] `DATA_ENCRYPTION_KEY` set; re-encrypt script run if migrating existing data
- [ ] `MASTER_ADMIN_LOGIN`, `MASTER_ADMIN_PASSWORD`, and `MASTER_ADMIN_TOTP_SECRET` stored securely (not in git)
- [ ] All staff users have permission categories
- [ ] Mandatory 2FA enabled when ready
- [ ] WAF / rate rules on login endpoints
- [ ] `ONLYOFFICE_CALLBACK_REQUIRE_JWT=1` for production (ONLYOFFICE 9.x sends signed callbacks)
- [ ] Backups for Postgres volume (`db-data`) and `./data/files`
- [ ] Do **not** expose Postgres or backend ports to the public internet
- [ ] **Outlook add-in** deployed (if the firm uses Microsoft 365) — see §8.1
- [ ] **Thunderbird add-on** signed `.xpi` distributed (if the firm uses Thunderbird) — see §8.2

---

## 8. Mail client add-ons (Outlook & Thunderbird)

Canary connects to users’ mail clients through two optional add-ons. Both use the **same Canary site URL** and staff login as the web app (`POST /api/auth/login` → Bearer JWT on `/api`). Neither replaces the mail client — they file mail to matters and support compose-from-matter workflows.

| | **Outlook add-in** | **Thunderbird add-on** |
|---|-------------------|------------------------|
| **Shipped with** | Frontend Docker image (nginx serves `/outlook-addin/…`) | Signed `.xpi` + update manifest on **canarylegalsoftware.co.uk/thunderbird/** |
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

### 8.2 Thunderbird add-on

The Thunderbird add-on provides **file to matter**, **compose with merge + attachments**, and a **Canary** tag on **incoming** mail. Sent mail is filed on send but is **not** tagged in Thunderbird.

#### Important: signed release only for production

Release Thunderbird **removes unsigned add-ons on restart**. **Load Temporary Add-on** (Debug Add-ons) is for development only — do **not** rely on it for firm rollout.

Production installs require a **Mozilla-signed `.xpi`** (unlisted on the Thunderbird Add-ons store is fine — it does not appear publicly, but Mozilla still signs it).

#### For firm IT — install on workstations

1. Download **`canary-thunderbird-{version}.xpi`** from **`https://canarylegalsoftware.co.uk/thunderbird/`** (or your vendor).
2. On each PC (or via your software deployment tool):
   - **Tools** → **Add-ons and Themes** → gear menu → **Install Add-on From File…**
   - Select the signed `.xpi`.
3. Confirm **Canary — file to matter** appears and **survives a Thunderbird restart**.
4. Each user: toolbar **Canary** → **Server & sign-in** → enter **`https://canary.yourfirm.co.uk`** (the **firm** Canary host, not canarylegalsoftware.co.uk).

**Updates:** Thunderbird checks **`https://canarylegalsoftware.co.uk/thunderbird/updates.json`** about daily and installs newer signed builds automatically (after users have a build that includes `update_url` in the manifest).

#### Enterprise pre-install (Betterbird / Thunderbird)

Firm-managed desktops should use **official Betterbird** (not Flatpak) and a system **`policies.json`**:

| OS | Path |
|----|------|
| Linux | `/etc/thunderbird/policies/policies.json` |
| Windows | `C:\Program Files\Betterbird\distribution\policies.json` |

Template (force-install Canary add-on, block other add-ons, primary password, firm calendar categories): [deploy/betterbird/policies.json](../deploy/betterbird/policies.json) and [deploy/betterbird/README.md](../deploy/betterbird/README.md).

On the Canary server, set **`CANARY_CALENDAR_LABEL_SPECS`** in `.env` so in-app calendar labels match Betterbird category names (see `.env.example`). Canary writes `CATEGORIES` into CalDAV events so Betterbird can colour them.

Manual `.xpi` install remains valid for ad-hoc machines; the canonical download URL is **`https://canarylegalsoftware.co.uk/thunderbird/`**.

#### For maintainers — build, sign, and publish

Signing is **not** part of the Docker stack. Maintainers build from the Canary CMS repository (`thunderbird-addin/`):

```bash
cd thunderbird-addin
npm ci
export ATN_API_KEY='…'       # from https://addons.thunderbird.net/developers/addon/api/key/
export ATN_API_SECRET='…'
npm run release              # lint → package → sign → publish-hosting
```

Output:

- **`dist/canary-thunderbird-{version}.xpi`** — signed add-on
- **`hosting/`** — upload to **`public_html/thunderbird/`** on canarylegalsoftware.co.uk (WordPress: static folder, not a WP page — see `thunderbird-addin/hosting/README.md`)

**One-time setup:** developer account at [addons.thunderbird.net/developers](https://addons.thunderbird.net/developers/); add-on ID is fixed as `canary-file@canarylegal.co.uk` in `manifest.json`. Bump `version` before each new release. The manifest `update_url` points at the central host (all firms share one update channel).

**Manual fallback (no API):** `npm run package`, upload the zip to the ATN developer hub as **unlisted**, download the signed `.xpi`.

**GitHub Actions (optional):** tag `thunderbird-v*` on the repo triggers lint, package, sign (with `ATN_API_KEY` / `ATN_API_SECRET` secrets), and a GitHub Release artifact.

Full detail: [thunderbird-addin/README.md](../thunderbird-addin/README.md).

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
| ONLYOFFICE callback JWT | `ONLYOFFICE_CALLBACK_REQUIRE_JWT=1` in `.env` (default in `.env.example`; requires Document Server 8+ / 9.x) |

---

Adjust hostnames, paths, and ports for your environment. Mail add-on maintainer detail also lives in [frontend/public/outlook-addin/README.md](../frontend/public/outlook-addin/README.md) and [thunderbird-addin/README.md](../thunderbird-addin/README.md).
