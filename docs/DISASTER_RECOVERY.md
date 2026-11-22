# Database and document recovery

## Scope

`scripts/recovery_drill.py` restores a **paired** `database.dump` and `files.tar` from a deployment release into a new, isolated Compose project. It does not stop, reconfigure, migrate, restore over, or attach to an existing deployment. It is a rehearsal tool, not a production cutover command.

Required inputs:

- The release directory containing `database.dump`, `files.tar`, `checksums.json` and `previous.json`. The latter contains the original encryption key and must remain private.
- Backend/frontend images compatible with the backup schema. Normally use the previous image IDs recorded with that backup. An explicitly tested candidate is also possible when its schema is compatible; this drill does not run migrations automatically.
- The matching commercial/firm package snapshot if the installation used one. The current tool supports the commercial package mounted at `/commercial` and its module below that path. Other optional mounts need a reviewed recovery configuration.
- Docker, Compose, Python 3.12+ on the operator host, sufficient free disk space, and the pinned PostgreSQL/ONLYOFFICE images available locally.

A database dump, file archive and decryption key must be preserved together. The updater captures the pair while application entry points are stopped; its checksums prove byte integrity, not business completeness. Scheduled operations backups also capture `/radicale-data` and `/commercial` when mounted on the backend; older deployment backups do not. External mail/Graph state, external databases and external file stores remain outside the restore scope. See [scheduled operations](OPERATIONS.md).

## 1. Prepare without touching live services

Use a private working directory outside the source checkout. Retain all original backup files. If necessary, load retained Docker image archives or build the locked source before starting the isolated restore. Do not mount live file directories, live database volumes, the Docker socket, or live optional-package directories into the recovered services.

```sh
python3 scripts/recovery_drill.py \
  --release /srv/canary-deployment/releases/BACKUP_RELEASE \
  --state /srv/canary-recovery/NEW_DRILL \
  --backend-image sha256:BACKUP_COMPATIBLE_BACKEND_IMAGE \
  --frontend-image sha256:BACKUP_COMPATIBLE_FRONTEND_IMAGE \
  --commercial-source /srv/release-artifacts/MATCHING_COMMERCIAL_SNAPSHOT
```

Omit `--commercial-source` for backups without that package or with a captured `commercial.tar`. The supplied directory is **copied** into private drill storage. Its original `/commercial/module` path is retained; the original directory is never mounted into recovery containers.

The tool refuses existing state directories, unsafe tar entries, checksum mismatches, and an existing target volume. It generates a new `canaryrestore-*` project with new database/file volumes, no published ports, no host/container namespace sharing and an `internal: true` network. The data-encryption key and a decryption-only `DATA_LEGACY_JWT_SECRET` are carried over from the original environment; the latter preserves old ciphertext without accepting old sessions. Database, JWT, recovery-master and document-server secrets are regenerated. Live SMTP/Graph/tunnel settings are not inherited. Background jobs and update checks are disabled in the clone.

## 2. Restore and verify stored data

The tool performs these steps and writes a private `restore.log`:

1. Verify both backup SHA-256 hashes and copy the artifacts into the drill directory.
2. Start only the new database, then restore with `pg_restore --exit-on-error --single-transaction --no-owner --no-privileges` into the empty `canary_recovery` database.
3. Restore the document archive into the new file volume. Compare **every restored file** against a SHA-256 manifest derived from the archive.
4. Record core table counts, migration revision, a fingerprint of every ledger row, account balances and missing document references in `inventory-before.json`. Missing referenced files stop the drill.
5. Start the compatible app and ONLYOFFICE images without automatic migrations; wait for health and confirm the internal network.

A healthy container is not enough. Use `--verify --cleanup` for automated authenticated read/document-hash/ledger checks and automatic removal of the isolated project, or continue below for the fuller browser editing checks.

## 3. Verify the recovered app

The browser must run in a container attached only to the drill's internal network, using `http://frontend`. Do not expose the clone publicly or reuse a live sign-in session.

For this installation, `backend/scripts/prepare_recovery_login.py` creates a temporary administrator **only** when the database is `canary_recovery` and background jobs are disabled. It selects the existing synthetic “Deployment verification” matter and DOCX restored from the backup. If a different installation has no such fixture, select an appropriate disposable document in the clone before adapting the helper; never alter live data to make a recovery test pass.

With `DRILL` set to the new state directory and `PROJECT` read from its `recovery.json`:

```sh
umask 077
mkdir -p "$DRILL/verification"
docker compose -p "$PROJECT" -f "$DRILL/compose.json" exec -T backend python \
  < backend/scripts/prepare_recovery_login.py > "$DRILL/verification/credentials.json"
cp "$DRILL/inventory-before.json" "$DRILL/verification/inventory-before.json"
# Use the locally built frontend/Dockerfile.e2e image; it contains Playwright and Python.
docker run --rm --network "${PROJECT}_default" --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$DRILL/verification:/checks" \
  -v "$(pwd)/scripts/verify_recovery.cjs:/verify.cjs:ro" \
  PINNED_BROWSER_RUNNER_IMAGE node /verify.cjs
```

The verification script checks sign-in, commercial-module activation, every restored ledger account's API balance against the SQL inventory, the original document download hash, matter/document opening, actual ONLYOFFICE editing and save, downloaded edited content, and logout. Results and screenshots stay in the private drill directory.

After testing, run `backend/scripts/recovery_inventory.py` again inside the recovery backend. Compare its ledger fingerprint, account balances, schema revision and core counts with the pre-start inventory. The test adds one temporary user and edits one cloned document; those are expected changes. Ledger rows and balances must not change. Check that outbound networking fails and that no recovery container has published ports or membership in a live network. Inspect the original live containers' IDs, image IDs, start times and restart counts against a pre-drill snapshot.

Disable the temporary account, increment its authentication token version, replace its password and delete the credentials file. Do not include credentials, database dumps, private resolved configuration or unredacted financial inventories in CI artifacts or a public PR.

## 4. Stop and retain evidence

```sh
docker compose -p "$PROJECT" -f "$DRILL/compose.json" stop
```

This keeps the isolated volumes for inspection. To delete a completed rehearsal, first verify the project name is the recorded `canaryrestore-*` project, then use that exact configuration with `down --volumes`. Never run that cleanup against the live Compose project. Keep a non-sensitive report, the private integrity manifests, image IDs, timings and restore log according to the backup retention policy.

## Actual incident cutover

A successful rehearsal proves this backup/image/package combination can be recovered. Production cutover remains a separate operation: stop all writers, preserve a further backup of the damaged/current state, restore into new volumes, verify data and authenticated workflows, then deliberately switch the production configuration and ingress. Retain the old data and a rollback configuration until acceptance. Do not blindly overwrite a database or file tree.

Record backup age as the recovery-point exposure. Record restore time, app-ready time and verification time separately. Cached-image lab timings exclude downloading/building images, operator diagnosis, ingress changes and business acceptance; they are not a guaranteed outage duration.

## 19 November 2026 drill

Using the paired pre-PR-3 deployment backup and newly pinned candidate images:

- 365 archived files restored with identical hashes; no missing file references.
- Restored core data: 122 matters, 343 document records, 3 users, 212 ledger accounts and 1,239 ledger entries.
- All 212 API account balances across 106 matters matched the SQL baseline, including 203 non-zero balances. The ledger-row fingerprint and schema revision remained unchanged after verification.
- Sign-in, commercial-module activation, restored document download hash, opening, editing, save, download-content verification and logout passed; no browser runtime errors.
- With images already built/cached: data restore and inventory took 7.25 seconds; services were healthy at 19.44 seconds; browser verification took a further 6.03 seconds.
- No published recovery ports; external egress blocked. All seven live containers retained their IDs, images, start times and restart counts.

The commercial source was supplied separately because the existing backup pair did not include that bind-mounted code. Its copy was hashed in the private recovery record. Preserve this additional artifact for a real host-loss recovery. External fonts/integrations were unavailable by design on the isolated network.

## Complete bundle acceptance

Use the maintained operations backup with `archive_images: true` and encrypted export for disaster recovery. Deployment rollback snapshots remain narrower and must not be mistaken for complete bundles. `--require-complete` rejects missing configuration/inventory/image manifest and required calendar/package archives, then imports the exact backend/frontend/database/document-server images from `images.tar`. Explicit image overrides must match the manifest; an external optional-package source is not accepted in complete mode. No registry pull is necessary. Each archive is verified before data is restored into fresh volumes.

```sh
umask 077
python3 scripts/recovery_drill.py --release /private/verified-bundle \
  --state /private/new-rehearsal --require-complete --verify --cleanup
```

Only use a trusted private bundle: hashes detect accidental corruption, not an attacker replacing both the data and manifest. The exported encrypted bundle must be decrypted using its separately retained passphrase and its integrity checked before use. Keep originals, and use new empty state directories. See OPERATIONS.md for key custody, cold-host acceptance and recovery objectives. Retired shell commands perform no backup or restore.

The read-only inventory now verifies stored document and retained recovery checksums, attachment relationships and original encrypted values. Unknown historical checksums are reported; they are not backfilled by a rehearsal. A failed secret authentication or known checksum mismatch prevents verification even if a new administrator can sign in. No provider calls are made. Calendar restoration validates archived bytes but does not activate a calendar service or external sync; separate cutover acceptance remains necessary.

Image identity is checked across Docker storage backends: OCI manifest/index IDs are resolved through the verified archive to their image-config digest when the target daemon uses the classic image store. A missing or ambiguous platform is rejected rather than selecting a mutable tag. Recovery on another CPU architecture requires a separately prepared compatible bundle; it is not silently emulated.
