# Monitoring, scheduled backups and recovery checks

These host jobs are **opt-in**. Building, testing or deploying this code does not install timers or start backups. The release leaves the UI and its double-click/right-click interactions unchanged.

## Health and diagnostics

- `/api/health` remains the lightweight process/build liveness endpoint.
- `/api/health/ready` returns only `ready` (200) or `not_ready` (503), based on bounded database checks and a file-storage write/read/free-space check. Database readiness requires the installed Core Alembic heads and essential user, matter and file tables/columns; a reachable empty, outdated or partially stamped database is not ready. These checks do not migrate or repair the schema and are not a complete schema-integrity audit. It does not create a missing storage directory. `CANARY_STORAGE_MIN_FREE_BYTES` defaults to 512 MiB.
- `/api/admin/health` requires an administrator and reports database, storage and ONLYOFFICE independently. An ONLYOFFICE failure degrades document editing without marking the whole application unavailable.
- The host monitor checks the same dependencies, public HTTPS reachability, latest backup success and latest recovery success. Missing, failed, future-dated or stale results fail the check. Public access failure may be caused by VPN, DNS, connectivity or ingress; it is not attributed to an application defect.

API responses carry a server-generated `X-Request-ID`. `ApiError.requestId` retains it without changing UI messages. Backend JSON request logs contain the route template, method, status, duration and request ID; unexpected errors also include exception class and source module/function/line. They omit raw paths, query strings, bodies, credentials, exception messages and local variables. Nginx JSON access logs correlate upstream request IDs without logging URLs. Proxy errors without an upstream response have no backend request ID. Routine nginx error logging is suppressed because it can include token-bearing URLs; critical errors remain. Existing subsystem logs are separate and must still be treated as private.

For investigation, find the response's `X-Request-ID` in browser Network tools and search backend/frontend container logs for that exact value. Correlate with the build commit from `/api/health`. Private job logs and state JSON provide host-side diagnostics; journal summaries contain only job/status/time/error class. No client identifiers or secrets should be pasted into public issue reports.

## Prepare configuration (no activation yet)

Requirements: Python 3.12+, Docker Compose with `start --wait`, GnuPG for encrypted exports, disk capacity for backups plus a complete restored clone. Run jobs as the **same operating-system account** as the deployment script so both share the per-project lock. Independent manual Docker commands and external writers do not honour this lock.

1. Copy `ops/operations.example.json` to a private configuration location. Set `deployment_config` to the exact resolved Compose file for the active release. Update this reference after each deployment; storage identity checks reject mismatched configuration. Keep the configuration, backup root and state root private (0600 files, 0700 directories), outside active mounted data and the source checkout.
2. Choose the local retention count and maximum ages. Defaults retain 14 successful local snapshots and flag backups older than 26 hours or recovery checks older than 35 days.
3. Set `archive_images: true` to produce a complete recovery bundle, including the running backend, frontend, PostgreSQL and ONLYOFFICE image IDs and their image archive. All four roles must be running. This uses extra disk space. The scheduled recovery check requires this complete format; local snapshots without it are not disaster-recovery acceptance evidence.
4. For an encrypted independent copy, configure `export.directory`, `target_id` and `passphrase_file`. Provision that destination separately on independent storage. Place the exact target ID in its `.canary-backup-target` file. The job refuses an absent/mismatched marker rather than creating a destination when a mount is missing. The marker proves destination identity, not physical offsite placement.
5. Generate a strong backup passphrase into a nonempty 0600 file outside the backup directory. Keep a separate protected recovery copy of the passphrase; losing it makes the encrypted backups unusable. Set `GNUPGHOME` to a private dedicated directory. No passphrase appears in command arguments or logs.

Export uses streaming GPG AES-256 encryption and publishes only a completed `.tar.gpg` file plus its SHA-256 sidecar. A failed export fails the job and prevents local rotation. Omit `export` explicitly for local-only backups; that provides no protection from host loss. **Remote exports are retained indefinitely** by this release: configure destination lifecycle/retention separately, preserving enough versions for the recovery objective. Local rotation only removes this tool's verified snapshot directories, never incomplete/unrecognised directories. Incomplete jobs remain for diagnosis and need reviewed cleanup.

## Run and inspect manually before scheduling

```sh
umask 077
python3 scripts/operations.py --config /etc/canary/operations.json backup
python3 scripts/operations.py --config /etc/canary/operations.json recovery-check
python3 scripts/operations.py --config /etc/canary/operations.json monitor
```

A backup briefly stops the configured application entry points/writers, captures PostgreSQL and documents as one consistent set, and restarts the services that were running. Schedule this maintenance window outside working hours. Optional `/commercial` and `/radicale-data` mounts on the backend are captured too; an active optional package that cannot be captured is an error. Other external data stores, mail/Graph state and unrelated mounts are not covered. Symlinks/special files in data archives are rejected rather than restored unsafely.

Each snapshot includes `database.dump`, `files.tar`, private resolved `previous.json` (including the running containers’ environment and data-encryption key), an inventory of core counts/ledger balances/schema, checksums and a completion record. Configured extra archives are checksummed too. A missing file, unsafe storage reference, known-checksum mismatch (including document recovery versions), invalid attachment link or undecryptable stored secret fails the backup. Older rows without checksums are counted explicitly, never silently certified as historically correct. Metadata-only recovery entries without archived bytes are counted as historically unavailable. A verified local snapshot is published atomically; the overall success timestamp advances only after any configured export completes. Failures do not prune older snapshots. Service restart is attempted even if stopping or snapshotting fails, and restart failure makes the job fail.

State files are `backup-status.json`, `recovery-status.json` and `health-status.json`. Monitor exits nonzero when any required check fails. The included timers surface this in systemd and the journal; **they do not send notifications**. Connect these exit states/status records to your existing external monitoring/alerting service before relying on unattended operation. A process killed with SIGKILL or a host power failure cannot execute restart/cleanup; treat a lingering `running` result as failure, inspect stopped services, and rerun the job after recovery.

## What the scheduled recovery check proves

The check acquires the same project lock as backup/deployment and selects the latest verified snapshot. If export is configured, it verifies and decrypts the **exported encrypted copy**, checks every included checksum and refuses unsafe archives. It then creates a fresh `canaryrestore-*` project, new volumes, an internal-only network and no published ports. It never mounts live data or inherits live SMTP/Graph/tunnel settings; background jobs are disabled.

It imports the four captured images by immutable ID from the verified bundle without a registry pull, then restores the database without migrations, hashes every restored file (and captured calendar file), compares core inventory and ledger fingerprints with the backup, and starts the matching images. Original encrypted values (including encrypted TOTP) are authenticated before a new account is created. Recovery regenerates JWT session signing but carries the original legacy JWT secret as `DATA_LEGACY_JWT_SECRET` for decryption only. For old installations without a dedicated data key, the original JWT-derived key is retained as the data key. No credentials are printed or sent to providers. A temporary clone-only administrator checks login, identity, a matter when present, up to three document downloads against their stored hashes, every ledger account's API balance, and logout. The temporary account is disabled afterwards. Results explicitly record document/account counts so an empty database is not mistaken for tested document recovery.

The project and volumes are removed on success/failure, including parent-side cleanup after a child timeout. Private evidence remains in the state directory; review and remove old drill directories periodically because they contain sensitive restored artifacts. Decrypted export input is removed after the check. These checks do **not** replace browser editing/save verification or a production cutover rehearsal; use [the fuller recovery procedure](DISASTER_RECOVERY.md) for those.

After host loss, restore the operations code/configuration, encrypted archive, checksum sidecar and passphrase to a new recovery host. Keep the matching recovery tooling available separately. Privately decrypt and verify the exported bundle with `recovery_input` (or the documented GPG procedure), then run `recovery_drill.py --release <verified-directory> --state <new-private-directory> --require-complete --verify --cleanup`. The tool imports all four required images from the checksum-verified archive, including on an empty Docker daemon. It never reuses original ingress, SMTP settings, live mounts or namespace-sharing configuration. Run the isolated procedure first and inspect results before planning a separate cutover. This release deliberately does not restore over a running deployment.

## Enable schedules only after review

The files in `ops/systemd/` are templates, not installed units. Replace `User=canary` with the deployment operator account, set `CANARY_SOURCE`, `CANARY_OPERATIONS_CONFIG` and `GNUPGHOME` using `ops/operations.env.example`, and install that environment file at `/etc/canary/operations.env` with mode 0600. Install reviewed service/timer files under `/etc/systemd/system`, then reload systemd and explicitly enable the three timers when authorised.

Defaults: daily backup at 01:30, weekly recovery on Sunday at 03:30, monitoring every five minutes. Calendar timers are persistent after downtime. Lock contention fails safely without overlapping deployment/backup/recovery; monitor catches stale/missing successes. SIGTERM/SIGINT triggers cleanup, with a five-minute systemd shutdown allowance. Adjust backup duration and recovery schedule to the installation's size and acceptable downtime; measure actual restoration time rather than assuming the timeout is a recovery guarantee.

## Repeatable tests

`make test-operations` builds a uniquely named disposable stack, seeds synthetic matter/document/ledger data, creates and encrypts a paired backup, stops its own database and ONLYOFFICE to check failure reporting, restores and verifies the encrypted copy, rejects deliberate corruption and removes its own resources. It does not use existing deployment credentials, services or storage. CI runs the same command. Private backup/test directories are deliberately excluded from uploaded CI artifacts.

Host unit tests cover corruption/traversal, retention, shared locking, failed snapshots/stops, missing export targets, encryption round trips, stale results, network failure separation and timeout cleanup. The ordinary frontend/backend/core workflow suites remain required.

## Staff notification delivery

See [Staff notification outbox](STAFF_NOTIFICATION_OUTBOX.md) for on-demand delivery,
audited recovery and restore precautions. This release installs no notification job.

## Container log retention

The base deployment, dev tunnel companions and isolated Core test stack use Docker `json-file` logging with `max-size: "10m"` and `max-file: "5"`: approximately 50 MiB per container, plus record/filesystem overhead. Old container stdout/stderr logs rotate automatically. `docker logs` and request-ID correlation remain available within that retention window. This does not rotate application files, journals, backup/export archives or private recovery evidence; their retention remains a separate operational decision.

These defaults apply when containers are created from the updated Compose definitions. They do not modify running containers. The release helper intentionally preserves the deployment's existing resolved configuration; a code-only release from an old resolved config does not import the new logging defaults. Plan a separate reviewed configuration update and recreation of affected services (including database, document server and tunnel companions), with a maintenance window and verified backup. Preserve all mounts, credentials and service settings, and verify each container's `HostConfig.LogConfig` afterward. Do not edit Docker's live log files. No recreation or deployment is performed by this change.

Run `python3 scripts/test_log_rotation.py --image <local-python-capable-image>` to resolve the base/tunnel/test Compose policies with synthetic values and verify actual rollover in a uniquely named, network-disabled disposable container. The probe emits 60 MiB of synthetic stdout, verifies old records are discarded while the final marker remains, then removes only its own container. It does not start the deployment or enable jobs/Actions.

## Optional external monitoring delivery

The independent [generic monitoring reporter and v1 contract](MONITORING_CONTRACT.md)
can deliver sanitised local monitor results and fresh heartbeats to a compatible
HTTPS receiver. It is disabled by default and is not invoked by the application,
operations commands or deployments. Odin is optional; no receiver credentials or
connectivity are required for Core or its local diagnostics. No delivery schedule
is installed or enabled.

## Recovery acceptance and custody

The retired `backup-canary.sh` and `restore-canary.sh` now exit without touching anything. Use the paired operations workflow; never overwrite a live database or overlay a live file tree.

A complete bundle contains database, documents (including hidden history), original private configuration and encryption material, inventory, mounted calendars and optional package, all four runtime images, and a checksummed versioned recovery manifest. Unsupported external mail/provider state remains outside the bundle. The encrypted export includes every one of these artifacts. A secret stored only on the failed host cannot unlock its export: escrow the export passphrase separately, and rehearse retrieving it.

Before activating any schedule, the operator must choose and record: maximum acceptable data loss (RPO), time to recovered service (RTO), backup frequency/maintenance window, retention on independent storage, recovery-key custodian, and restore-test frequency. Defaults are starting points, not guarantees. Destination markers do not prove independent storage. Verify the destination and key retrieval independently. Schedules and integrations remain opt-in and disabled until explicitly authorized.

For cold-host acceptance, use an empty, separate Docker daemon with registry access unavailable; recover using only the encrypted bundle, separately held export key and matching recovery tooling. Verify original-secret counts, document/history checks, calendar and package hashes, authenticated matter/document/ledger access and removal of isolated resources. Do not remove images from a live daemon to simulate a disaster. Record acquisition, data restore, readiness and verification times separately.

Keep `DATA_LEGACY_JWT_SECRET` private and preserve it through later deployments/backups until all legacy ciphertext has been migrated and verified. The existing re-encryption utility does not cover every optional-provider field; running it alone is not evidence that this recovery key can be discarded.
