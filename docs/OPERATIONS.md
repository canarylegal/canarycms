# Monitoring, scheduled backups and recovery checks

These host jobs are **opt-in**. Building, testing or deploying this code does not install timers or start backups. The release leaves the UI and its double-click/right-click interactions unchanged.

## Health and diagnostics

- `/api/health` remains the lightweight process/build liveness endpoint.
- `/api/health/ready` returns only `ready` (200) or `not_ready` (503), based on a bounded database query and file-storage write/read/free-space check. It does not create a missing storage directory. `CANARY_STORAGE_MIN_FREE_BYTES` defaults to 512 MiB.
- `/api/admin/health` requires an administrator and reports database, storage and ONLYOFFICE independently. An ONLYOFFICE failure degrades document editing without marking the whole application unavailable.
- The host monitor checks the same dependencies, public HTTPS reachability, latest backup success and latest recovery success. Missing, failed, future-dated or stale results fail the check. Public access failure may be caused by VPN, DNS, connectivity or ingress; it is not attributed to an application defect.

API responses carry a server-generated `X-Request-ID`. `ApiError.requestId` retains it without changing UI messages. Backend JSON request logs contain the route template, method, status, duration and request ID; unexpected errors also include exception class and source module/function/line. They omit raw paths, query strings, bodies, credentials, exception messages and local variables. Nginx JSON access logs correlate upstream request IDs without logging URLs. Proxy errors without an upstream response have no backend request ID. Routine nginx error logging is suppressed because it can include token-bearing URLs; critical errors remain. Existing subsystem logs are separate and must still be treated as private.

For investigation, find the response's `X-Request-ID` in browser Network tools and search backend/frontend container logs for that exact value. Correlate with the build commit from `/api/health`. Private job logs and state JSON provide host-side diagnostics; journal summaries contain only job/status/time/error class. No client identifiers or secrets should be pasted into public issue reports.

## Prepare configuration (no activation yet)

Requirements: Python 3.12+, Docker Compose with `start --wait`, GnuPG for encrypted exports, disk capacity for backups plus a complete restored clone. Run jobs as the **same operating-system account** as the deployment script so both share the per-project lock. Independent manual Docker commands and external writers do not honour this lock.

1. Copy `ops/operations.example.json` to a private configuration location. Set `deployment_config` to the exact resolved Compose file for the active release. Update this reference after each deployment; storage identity checks reject mismatched configuration. Keep the configuration, backup root and state root private (0600 files, 0700 directories), outside active mounted data and the source checkout.
2. Choose the local retention count and maximum ages. Defaults retain 14 successful local snapshots and flag backups older than 26 hours or recovery checks older than 35 days.
3. Set `archive_images: true` to retain the backend/frontend images needed after losing the host. This uses extra disk space. Pinned PostgreSQL/ONLYOFFICE images must also be available during recovery; mirror or archive them separately for offline disaster recovery.
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

Each snapshot includes `database.dump`, `files.tar`, private resolved `previous.json` (including the data-encryption key), an inventory of core counts/ledger balances/schema, checksums and a completion record. Configured extra archives are checksummed too. A database reference to a missing file fails the backup. A verified local snapshot is published atomically; the overall success timestamp advances only after any configured export completes. Failures do not prune older snapshots. Service restart is attempted even if stopping or snapshotting fails, and restart failure makes the job fail.

State files are `backup-status.json`, `recovery-status.json` and `health-status.json`. Monitor exits nonzero when any required check fails. The included timers surface this in systemd and the journal; **they do not send notifications**. Connect these exit states/status records to your existing external monitoring/alerting service before relying on unattended operation. A process killed with SIGKILL or a host power failure cannot execute restart/cleanup; treat a lingering `running` result as failure, inspect stopped services, and rerun the job after recovery.

## What the scheduled recovery check proves

The check acquires the same project lock as backup/deployment and selects the latest verified snapshot. If export is configured, it verifies and decrypts the **exported encrypted copy**, checks every included checksum and refuses unsafe archives. It then creates a fresh `canaryrestore-*` project, new volumes, an internal-only network and no published ports. It never mounts live data or inherits live SMTP/Graph/tunnel settings; background jobs are disabled.

It restores the database without migrations, hashes every restored file (and captured calendar file), compares core inventory and ledger fingerprints with the backup, and starts the matching images. A temporary clone-only administrator checks login, identity, a matter when present, up to three document downloads against their stored hashes, every ledger account's API balance, and logout. The temporary account is disabled afterwards. Results explicitly record document/account counts so an empty database is not mistaken for tested document recovery.

The project and volumes are removed on success/failure, including parent-side cleanup after a child timeout. Private evidence remains in the state directory; review and remove old drill directories periodically because they contain sensitive restored artifacts. Decrypted export input is removed after the check. These checks do **not** replace browser editing/save verification or a production cutover rehearsal; use [the fuller recovery procedure](DISASTER_RECOVERY.md) for those.

After host loss, restore the operations code/configuration, encrypted archive, checksum sidecar and passphrase to a new recovery host. Load retained backend/frontend images with `docker image load -i images.tar` after decrypting the bundle privately; provision the pinned infrastructure images. Run the isolated procedure first and inspect results before planning a separate cutover. This release deliberately does not restore over a running deployment.

## Enable schedules only after review

The files in `ops/systemd/` are templates, not installed units. Replace `User=canary` with the deployment operator account, set `CANARY_SOURCE`, `CANARY_OPERATIONS_CONFIG` and `GNUPGHOME` using `ops/operations.env.example`, and install that environment file at `/etc/canary/operations.env` with mode 0600. Install reviewed service/timer files under `/etc/systemd/system`, then reload systemd and explicitly enable the three timers when authorised.

Defaults: daily backup at 01:30, weekly recovery on Sunday at 03:30, monitoring every five minutes. Calendar timers are persistent after downtime. Lock contention fails safely without overlapping deployment/backup/recovery; monitor catches stale/missing successes. SIGTERM/SIGINT triggers cleanup, with a five-minute systemd shutdown allowance. Adjust backup duration and recovery schedule to the installation's size and acceptable downtime; measure actual restoration time rather than assuming the timeout is a recovery guarantee.

## Repeatable tests

`make test-operations` builds a uniquely named disposable stack, seeds synthetic matter/document/ledger data, creates and encrypts a paired backup, stops its own database and ONLYOFFICE to check failure reporting, restores and verifies the encrypted copy, rejects deliberate corruption and removes its own resources. It does not use existing deployment credentials, services or storage. CI runs the same command. Private backup/test directories are deliberately excluded from uploaded CI artifacts.

Host unit tests cover corruption/traversal, retention, shared locking, failed snapshots/stops, missing export targets, encryption round trips, stale results, network failure separation and timeout cleanup. The ordinary frontend/backend/core workflow suites remain required.
