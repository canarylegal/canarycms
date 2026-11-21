# Staff notification outbox

Invoice approvals/rejections, anticipated-payment approvals/rejections/amendments,
and Canary Sign sent/completed/declined staff alerts now queue encrypted, frozen
messages in the same database transaction as their business change. Queue/audit
failure prevents that transaction from succeeding. The migration does not backfill
historical alerts. No frontend, login-code or external-recipient delivery flow changes.
Portal uploads, form completions, quote responses and opted-in calendar reminders also
use this outbox. With the paired commercial-package update, DocuSign staff alerts
and opted-in search-result alerts do too. External messages, support mail, email tests,
password resets and login codes remain on their existing paths.

There is **no worker, scheduler or automatic retry** in this release. Eligible staff
alerts accumulate as pending, including while email is disabled. An operator must
explicitly dispatch them. Existing backup/monitoring scheduled jobs remain disabled.

## On-demand operations

Run inside the backend container, using an active administrator's UUID for ACTOR
and the notification UUID/version returned by list/inspect. These are trusted-host
operations: host/database access is required and `--actor-id` supplies audit attribution,
not a substitute for authenticating access to the host.

```
python scripts/staff_notifications.py list --state pending --limit 100
python scripts/staff_notifications.py inspect --id ID
python scripts/staff_notifications.py dispatch --id ID --actor-id ACTOR
python scripts/staff_notifications.py dispatch-pending --limit 25 --actor-id ACTOR
python scripts/staff_notifications.py retry --id ID --actor-id ACTOR --expected-version 3 --reason 'Provider confirmed rejection; configuration corrected'
python scripts/staff_notifications.py cancel --id ID --actor-id ACTOR --expected-version 4 --reason 'Superseded; do not send'
```

Reviewing a retry makes it pending; a separate dispatch sends it. Batch dispatch
only selects pending items, with a maximum of 200. A batch can partially succeed:
inspect durable states before continuing. Exit 0 means the command succeeded with
no failed/uncertain/sending results; 2 reports those attention states, and 3 indicates
an operation error. No success is printed before its database commit succeeds.

The dispatcher records an attempt and audit event, commits the `sending` claim,
then contacts the provider. Concurrent dispatchers cannot send the same claim.
Every attempt rechecks active recipient, unchanged address and current matter
access. Invalid encrypted payloads, unavailable configuration and lost access fail
before network I/O. Recipient changes require cancellation and business review;
retries never silently redirect frozen messages to a different address.

`sent` means **accepted by the configured provider**, not delivered to the inbox.
Explicit SMTP rejections are failed. Timeouts, unknown transport errors and ambiguous
results are uncertain. There is no automatic retry, fallback transport or exactly-once
email guarantee. SMTP Message-ID and Graph x-canary-notification-id identify the
stable notification for investigation; providers need not deduplicate them.

## Interrupted attempts and duplicate risk

A crash, or a failed final database commit after provider acceptance, leaves `sending`.
Once at least 15 minutes old, investigate provider evidence and the worker process:

```
python scripts/staff_notifications.py mark-uncertain --id ID --actor-id ACTOR --expected-version 2 --reason 'Worker stopped; checked provider logs'
python scripts/staff_notifications.py retry --id ID --actor-id ACTOR --expected-version 3 --reason 'Reviewed provider evidence; resend authorised' --acknowledge-uncertain
```

Ensure the old process is stopped before retrying. The acknowledgment explicitly
accepts duplicate-delivery risk; use cancel if resending is inappropriate. Late worker
results are audited and cannot overwrite a subsequent review. Reviews require a
reason and matching version, preventing stale operator decisions. Audit metadata
and CLI output exclude recipient addresses, bodies and raw provider errors. Avoid
placing secrets or message contents in review reasons.

## Backups and recovery

Back up the database **and the applicable encryption keys** with the deployment's
existing recovery procedure. Payloads use DATA_ENCRYPTION_KEY (or the legacy
JWT_SECRET-derived key); retain required keys until migration is complete. The
existing `reencrypt_data_secrets.py --dry-run`/apply procedure includes outbox
payloads when migrating from the legacy key. It does not support arbitrary key loss.

```
python scripts/check_notification_outbox.py
```

This read-only check authenticates/decrypts every payload, verifies its hash, and
reports counts/states plus an inventory hash without exposing contents or sending.
The core-workflow suite compares this inventory before/after real backend restart
and isolated PostgreSQL backup restore, including pending and uncertain examples.

After restoring an older backup, **do not dispatch pending rows until reconciled
against provider evidence**: messages sent after the backup may appear pending in
that backup. No jobs automatically send restored mail. Retain attempts/audits and
resolve those cases explicitly. Migration downgrade is intentionally blocked to
avoid dropping notification evidence; roll forward instead.

## Verification

Failure-path tests cover transaction rollback, preflight failures, denied access,
corrupt payloads, provider rejection/timeout, claim/final commit failures, interrupted
workers, audited versioned review and unchanged login-code dispatch. PostgreSQL
tests exercise competing enqueue/dispatch transactions; restart/restore checks
verify durable state. Tests inject synthetic providers and never contact real recipients.

## Remaining staff alerts and diagnostics

Run `python scripts/staff_notifications.py diagnostics` for aggregate state counts,
oldest pending age, attempt count and stale sending count. It uses a read-only snapshot,
prints no identifiers/recipients/content and exits 2 when failed, uncertain or stale
attempts need attention. It never retries or changes state.

Portal file IDs, form submission IDs, quote delivery IDs and commercial request/product
IDs provide event identities. Notification retry never reruns an upload, form completion
or vendor operation. Separate new upload requests remain separate business operations;
this is not a new portal-upload idempotency protocol. Concurrent form/quote transitions
are locked. Form completion writes a fresh durable candidate instead of overwriting
its pending snapshot; retained unreferenced candidates remain available for review.

Calendar reminders use subscription, due date, reminder kind and a snapshot fingerprint.
Historical sent buckets remain respected; new buckets live in the outbox. Before delivery,
subscriptions must still be enabled, unchanged, due today and accessible through their
matter or calendar. Expired/revoked reminders fail closed; review and cancel stale items.
Reminder collection performs no network I/O and does not commit on its own. Existing
background collectors remain controlled by CANARY_BACKGROUND_JOBS_ENABLED; dev is
configured with this set to 0, and backup/monitoring timers remain disabled.

Deploy the Core change before the paired commercial package, then restart the backend.
Keep local commercial UI changes intact. Test the paired package using its
`scripts/test-staff-outbox.sh`; no live provider credentials are used in those tests.
Search webhook queue failures must propagate without committing the callback receipt.
DocuSign queues inside a savepoint before creating an envelope, so a queue/audit failure
cannot itself trigger remote creation; provider failure rolls back the tentative notice.
Existing provider-side operations still have their own recovery limits, outside this
outbox's email-delivery guarantee.
