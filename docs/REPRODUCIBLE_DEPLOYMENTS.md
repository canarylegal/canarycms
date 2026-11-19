# Reproducible upgrades

`scripts/deploy.py` upgrades an **existing** Docker Compose installation from a clean Git commit. It keeps the existing database, document storage, environment and optional-package mounts. It never runs `down` or deletes volumes.

## Prepare

Commit the source changes first. Keep deployment state outside the checkout. Run as the same trusted account that manages Docker.

If the installation uses several Compose files, first resolve the exact working configuration into a private file:

```sh
umask 077
docker compose -f docker-compose.yml -f YOUR_OVERLAY.yml --profile prod config --format json > /srv/canary-deployment/current.json
```

The resolved configuration **contains secrets**. Do not commit it, publish it as a CI artifact, or put it in a web-served directory.

```sh
python3 scripts/deploy.py --state-dir /srv/canary-deployment/releases prepare \
  --source /srv/canary-source \
  --config /srv/canary-deployment/current.json \
  --url https://canary.example.com
```

Preparation records the source SHA, project, current container/image IDs, data mounts and previous public build SHA. It refuses dirty source, missing services, changed storage paths, and unsupported external database configurations. It changes no running services. Inspect the printed release directory and its private manifest before applying.

## Apply and check

```sh
python3 scripts/deploy.py --state-dir /srv/canary-deployment/releases apply /srv/canary-deployment/releases/RELEASE
python3 scripts/deploy.py --state-dir /srv/canary-deployment/releases status /srv/canary-deployment/releases/RELEASE
```

The updater:

1. Builds backend and frontend from the recorded checkout while the previous app stays available.
2. Records immutable image IDs and embeds the source SHA in the backend image.
3. Stops application containers and their network companions for a maintenance window.
4. Creates a PostgreSQL custom-format backup and a document-storage tar archive; verifies readability and records SHA-256 checksums.
5. Recreates only the application and its network companions. Database and storage volumes remain intact.
6. Waits for container health, checks the same data mounts, checks the public API's build SHA and the frontend HTML shell.

The backend's normal startup command performs migrations. A health failure triggers code rollback **only if the database schema still matches the pre-upgrade schema**. Backup failure restarts the old containers. A release can be applied only once so its backups cannot be overwritten by a retry.

Use the successful release's `compose.json` for subsequent service operations, and as `--config` for the next release. Do not return to an old checkout's build configuration. Keep the original configuration inputs under private operational change control.

## Rollback

```sh
python3 scripts/deploy.py --state-dir /srv/canary-deployment/releases rollback /srv/canary-deployment/releases/RELEASE
```

Code rollback restores the previous image IDs and verifies the previous public build SHA. It deliberately does not restore the database, so writes made after deployment are retained. The schema guard prevents applying old code to a changed schema.

If migrations changed the schema, coordinate a maintenance restore instead:

- Stop the app and every writer. Preserve an additional backup of the current database and files before any restore.
- Restore `database.dump` into a **new, empty** PostgreSQL database with `pg_restore --exit-on-error --no-owner`; inspect its contents before switching the app to it.
- Restore `files.tar` into a **new, empty** file-storage directory and verify it. Use the database and file backup from the same release.
- Create a private configuration using `previous.json`'s image IDs and the restored storage, start it, then verify login, matter access and document opening.
- Retain the old database and storage until the recovery has been checked. Never blindly overwrite them or run `down -v` on an installation.

Practice that full recovery in a disposable environment before relying on it for a live installation. The automated code-rollback check is not proof that every historical migration can be reversed.

## Scope and limitations

This first updater supports one running container per service, a Compose-managed PostgreSQL service named `db`, a backend using `POSTGRES_*` rather than an explicit `DATABASE_URL`, and persistent `/data/files`. It handles services sharing the backend/frontend network namespace (such as tunnel sidecars). It does not upgrade infrastructure images, change optional package versions, or restore external services. Keep old images and backups until the release is accepted; image pruning can make rollback unavailable.

Run `make test-deploy` for safeguard tests and `make test-core-workflows` for isolated browser/API validation before preparing a release.

Release replay and rollback use recorded immutable image IDs. Rebuilding the same source later is not yet bit-for-bit reproducible: upstream base tags, OS packages and transitive Python dependencies can change. Preserve the built images; full digest and dependency locking is a follow-up.
