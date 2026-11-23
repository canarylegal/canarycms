# Optional upload scanning and quarantine

Scanning is disabled by default. No ClamAV dependency, network connection or scan worker is needed in that mode. Historical and disabled-policy uploads remain explicitly `unscanned`; enabling scanning does not retrospectively label them clean.

## Configure

Set these in the deployment `.env` and recreate the backend and optional worker together:

```
CANARY_UPLOAD_SCAN_MODE=required
CANARY_UPLOAD_SCAN_PROVIDER=clamav
CANARY_CLAMAV_HOST=clamav
CANARY_CLAMAV_PORT=3310
CANARY_CLAMAV_MAX_SIGNATURE_AGE_DAYS=7
CANARY_UPLOAD_SCAN_WORKER_ENABLED=1
CANARY_UPLOAD_SCAN_TIMEOUT_SECONDS=30
CANARY_UPLOAD_SCAN_MAX_BYTES=26214400
CANARY_QUARANTINE_ROOT=/data/quarantine
CANARY_QUARANTINE_MAX_BYTES=1073741824
```

For the bundled scanner use `docker compose -f docker-compose.yml -f docker-compose.scanning.yml --profile prod --profile scanning up -d`. This is an installation command, not a command to run against an existing deployment without reviewing its resolved configuration and persistent mounts. The normal Compose file alone does not start ClamAV. An existing private ClamAV service can be used instead; run the same worker against it. The example worker extends the base backend service: installations using firm or Commercial overlays must also mirror their package mounts and environment onto `upload-scanner`. Review the fully resolved Compose configuration before enabling it.

General background jobs and the hosted Commercial service are independent. The scanner worker explicitly disables both. GitHub Actions are not involved. Enabling upload scanning does not authorise enabling unrelated jobs.

The supplied ClamAV image is pinned. Its normal entrypoint runs FreshClam; definitions persist in `clamav-signatures`. Allow signature-update traffic, keep clocks accurate (UTC in the scanner), and keep the scanning port private: clamd does not authenticate its TCP clients. The scanner has no document, quarantine, database or integration-credential mounts. Canary streams bytes to it. The worker necessarily has access to Canary's database and file stores. Budget up to 4 GiB for the scanner container and benchmark the actual workload.

An external scanner must match `deploy/clamav/clamd.conf`: PDF, mail, Office and archive scanning, encrypted-file alerts and limit alerts must be enabled. Configured size limits must match Canary's upload limits. Canary independently checks ZIP member size, nesting, encryption and expanded-byte limits because ClamAV can skip an oversized ZIP member without returning a limit alert. ClamAV detection remains a risk reduction, not proof that every document is harmless.

## Behaviour

Matter uploads from staff, Outlook/Thunderbird and portal shared areas are recorded immediately as `pending`; bytes live in a separate private store. Filenames and scan status can be listed, but content access and editor checkout are blocked. No email parsing, MSG conversion or firm document-upload processing happens before a clean scan. Separate attachments are scanned independently. Embedded attachments are scanned as part of their containing email. The new add-in versions do not tag or cache pending uploads as successfully filed.

Portal form field uploads, precedents, branding/signature uploads and import files use an inline scan before their existing processing. Their request waits for the scanner; rejected or incomplete scans do not publish the upload. WebDAV and OnlyOffice replacements scan before publication; failure preserves the existing version. This initial release deliberately does not queue a replacement and change an editor's save-acknowledgement semantics.

The worker uses a durable PostgreSQL queue with transactional notifications and a one-second fallback check. Row locks prevent competing workers from processing the same upload. It validates the byte hash and current matter/portal permission before publication. Changed permissions block release. MSG conversion runs only after the source passes, and the converted bytes are scanned again.

Promotion writes an immutable candidate and then commits its pointer and clean state. A failed or ambiguous commit retains the quarantine source. Restarting the worker can retry without exposing partially published content. Scanner detections stay blocked; outages, malformed responses, timeouts or stale signatures stay inaccessible and receive up to three attempts with backoff. Administrators can request another scan; there is no force-release action.

Changing the mode to `disabled` never releases existing quarantine. Required mode with the worker disabled accepts uploads into quarantine and displays a configuration warning. Changing the quarantine path requires moving its data and updating the persistent mount while all writers are stopped.

Upload notifications describe receipt of a file, not a clean verdict. Existing optional upload notices may arrive while the document is still pending; content remains blocked. Scan workers do not send notification emails or make provider calls. Graph enrichment of newly scanned emails is not performed by the worker; verified Message-ID metadata is populated locally.

## Administration and recovery

Admin → Storage shows configuration, scanner/signature status and pending, blocked and incomplete uploads (latest 200). Retry rescans; discard permanently removes a quarantined upload after confirmation. Parents with attachments cannot be discarded until their children are removed. Normal document deletion/recovery is intentionally unavailable for pending content to avoid creating a downloadable recovery copy.

Quarantine defaults to a 1 GiB capacity, enforced across concurrent upload processes. It is not a public/static directory. Persist and back up it alongside the database and normal files. The updater and operations backup include `quarantine.tar` and stop an active scan worker during capture; restore drills restore quarantine separately with scanning disabled. Never restore only database and normal files when pending uploads exist. Signature databases are replaceable and are not part of document recovery.

Orphans from ambiguous commits are intentionally retained. Do not delete quarantine or unreferenced `.scanned` candidates by age alone while writers are running; reconcile them against database references during an administrator-controlled maintenance window. There is no automatic quarantine-expiry job in this release.

Before activation, test clean files, EICAR, embedded attachments, encrypted PDFs, archive limits, scanner outage/stale signatures, retries, concurrent uploads and restoration in an isolated environment. Measure real documents and bursts; scan time depends on content and queue depth, not just file size.
