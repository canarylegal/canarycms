# Canary CMS

Case-management software for law firms — matters, documents, contacts, tasks, calendars, client and office accounts, quotes, and a client portal. Designed to run on infrastructure you control (self-hosted or via a hosting partner).

> **Warning — `main` is unstable and unsupported for production**
>
> The default branch (`main`) is a **development** line. It may change without notice, break migrations or APIs, and is **not** licensed or supported for Production Use (see [LICENSE.txt](LICENSE.txt)).
>
> **Only official GitHub Releases (version tags such as `v2.0.0`) are supported** for live deployments. Pin to a release tag — do not run floating `main` in production. See [Releases](https://github.com/canarylegal/canarycms/releases) and [CHANGELOG.md](CHANGELOG.md).

**Website:** [canarylegalsoftware.co.uk](https://canarylegalsoftware.co.uk)

**Desktop (Linux):** optional Electron shell — source and `.deb` downloads at [canarylegal/canary-desktop](https://github.com/canarylegal/canary-desktop) ([Releases](https://github.com/canarylegal/canary-desktop/releases)).

## Quick start

Requires Docker and Docker Compose on a Linux host. Use a **release tag**, not `main`.

```bash
git clone https://github.com/canarylegal/canarycms.git
cd canarycms
git checkout v2.0.0   # pin to a release — see GitHub Releases / CHANGELOG.md
cp .env.example .env
```

**Before** `docker compose up`, replace every `CHANGE_ME_*` value in `.env` with generated secrets
(`openssl rand -hex …`, Fernet key, master admin TOTP — full commands in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) §3).
Backend startup rejects leftover placeholders from `.env.example`.

```bash
# Edit .env — secrets + public HTTPS URLs (CANARY_PUBLIC_URL, CORS, ONLYOFFICE, CalDAV)
GIT_COMMIT=$(git rev-parse HEAD) docker compose --profile prod build
docker compose --profile prod up -d
```

Production stack: nginx frontend, FastAPI backend, PostgreSQL, ONLYOFFICE Document Server, and optional Radicale (CalDAV). See `.env.example` and `docker-compose.yml` for configuration.

First-time firm administrators are created via the **master recovery** login (configured in `.env`) or by an existing admin under **Admin → Users**.

## Documentation

Operational guides live under **[docs/](docs/)**:

| Guide | Description |
|-------|-------------|
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production setup: DNS, TLS, reverse proxy, WAF, bootstrap, mail add-ons, go-live |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Docker dev: 502 errors, LAN access, firewall |
| [docs/ONLYOFFICE_BROWSER_EDIT.md](docs/ONLYOFFICE_BROWSER_EDIT.md) | In-browser editing (ONLYOFFICE) |
| [docs/WEBDAV_DESKTOP_EDIT.md](docs/WEBDAV_DESKTOP_EDIT.md) | Desktop editing via WebDAV |
| [docs/TESTING.md](docs/TESTING.md) | Unit tests, portal smoke (`make smoke-portal`), CI |

Mail add-on detail: [thunderbird-addin/README.md](thunderbird-addin/README.md), [frontend/public/outlook-addin/README.md](frontend/public/outlook-addin/README.md).

**Architecture (maintainers):** how Canary’s maintained core relates to optional product capabilities and proprietary firm packages is documented **internally** (not in this public repository). Firm-specific content and customisation belong beside Canary, not in public `canarycms`.

## Deploy checklist (after updating)

Prefer a **release tag** over floating `main` (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)).

When you update an existing installation, rebuild **both** the backend and frontend so API and UI stay in sync (stale frontend bundles can show old filters, missing buttons, or broken admin pages).

```bash
git fetch --tags origin
git checkout vX.Y.Z   # or: git pull --ff-only on a reviewed commit
GIT_COMMIT=$(git rev-parse HEAD) docker compose --profile prod build backend frontend
docker compose --profile prod up -d
docker compose --profile prod exec backend alembic upgrade head
```

- Run **database migrations** whenever the pull includes new files under `backend/alembic/versions/`.
- If behaviour still looks wrong after rebuild, hard-refresh the browser (Ctrl+Shift+R) to clear cached JavaScript.
- ONLYOFFICE and other services only need rebuilding when their images or config changed.

## Licence

The **`main`** branch (and other unreleased development lines that include this file) is under the **Canary CMS Development Source Licence** — see [LICENSE.txt](LICENSE.txt). That covers inspection, development, testing, and evaluation only. **Production Use is not permitted** from development branches.

**Stable tagged releases** (for example `v2.0.0`) ship with their own licence file. From v2.0.0 that is the Canary CMS Commercial Source Licence Version 2.0: evaluation remains available; Production Use requires a commercial agreement. Older tags keep the licence distributed with that tag.

Contact: [colin@canarylegalsoftware.co.uk](mailto:colin@canarylegalsoftware.co.uk).

## Contact

Questions about deployment, licensing, or professional hosting: [colin@canarylegalsoftware.co.uk](mailto:colin@canarylegalsoftware.co.uk)
