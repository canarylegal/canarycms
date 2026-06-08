# Canary CMS

Case-management software for law firms — matters, documents, contacts, tasks, calendars, client and office accounts, quotes, and a client portal. Designed to run on infrastructure you control (self-hosted or via a hosting partner).

**Website:** [canarylegalsoftware.co.uk](https://canarylegalsoftware.co.uk)

## Quick start

Requires Docker and Docker Compose on a Linux host.

```bash
git clone https://github.com/canarylegal/canarycms.git
cd canarycms
cp .env.example .env
# Edit .env — set secrets and public URLs (see comments in .env.example)
docker compose --profile prod up -d
```

Production stack: nginx frontend, FastAPI backend, PostgreSQL, ONLYOFFICE Document Server, and optional Radicale (CalDAV). See `.env.example` and `docker-compose.yml` for configuration.

First-time setup uses `BOOTSTRAP_ADMIN_TOKEN` from `.env` to create the initial administrator account.

## Documentation

Operational guides live under **[docs/](docs/)**:

| Guide | Description |
|-------|-------------|
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production setup: DNS, TLS, reverse proxy, WAF, bootstrap, mail add-ons, go-live |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Docker dev: 502 errors, LAN access, firewall |
| [docs/ONLYOFFICE_BROWSER_EDIT.md](docs/ONLYOFFICE_BROWSER_EDIT.md) | In-browser editing (ONLYOFFICE) |
| [docs/WEBDAV_DESKTOP_EDIT.md](docs/WEBDAV_DESKTOP_EDIT.md) | Desktop editing via WebDAV |

Mail add-on detail: [thunderbird-addin/README.md](thunderbird-addin/README.md), [frontend/public/outlook-addin/README.md](frontend/public/outlook-addin/README.md).

## Deploy checklist (after `git pull`)

When you update an existing installation, rebuild **both** the backend and frontend so API and UI stay in sync (stale frontend bundles can show old filters, missing buttons, or broken admin pages).

```bash
git pull
docker compose --profile prod build backend frontend
docker compose --profile prod up -d
docker compose --profile prod exec backend alembic upgrade head
```

- Run **database migrations** whenever the pull includes new files under `backend/alembic/versions/`.
- If behaviour still looks wrong after rebuild, hard-refresh the browser (Ctrl+Shift+R) to clear cached JavaScript.
- ONLYOFFICE and other services only need rebuilding when their images or config changed.

## Licence

This project is source-available and free for internal self-hosted use by individuals and organisations.

If you want to offer this software as a hosted service, managed service, reseller product, or other commercial external offering, you must obtain a separate commercial licence.

See [LICENSE.txt](LICENSE.txt) for details or contact [colin@canarylegalsoftware.co.uk](mailto:colin@canarylegalsoftware.co.uk).

### What you can do for free

- Self-host internally
- Use inside your company
- Modify for internal needs
- Run unlimited internal instances

### When you need a commercial licence

- Hosting for customers
- Managed service provision
- White-label resale
- Commercial redistribution
- Paid support centred on this software

## Contact

Questions about deployment, licensing, or professional hosting: [colin@canarylegalsoftware.co.uk](mailto:colin@canarylegalsoftware.co.uk)
