# Recoverable document saves and deletions

Document changes publish a database pointer to a new file rather than overwriting
current bytes. Before replacement or deletion, Canary copies the prior bytes into
`.recovery/<recovery-id>/` and stores a metadata snapshot and SHA-256 checksum in
`document_recovery`. New versions live under `.versions/<file-id>/`. These paths
are internal storage paths; virtual folders, column preferences and interactions
are unchanged.

The archive and candidate are flushed to disk before the transaction commits.
The File row, recovery record, version and audit event commit together. An error
before commit leaves the original pointer usable. If commit succeeds but its
acknowledgement is lost, the published candidate is retained. Never remove a
candidate merely because a commit call raised an exception.

This covers case-file and folder deletion (including cascaded attachments),
precedent-file deletion, ONLYOFFICE callback and browser-export saves, WebDAV
PUT, comment edits and restoring an editor backup. It does not make every
filesystem operation in Canary transactional: uploads, rename/move operations,
whole-matter deletion and external signing integrations require their own review.

## Save confirmation

Save Changes arms a UUID attempt bound to the current editor key. CommandService
receives that ID in `userdata`; polling reports success only when the matching
attempt commits bytes. Releasing/revoking a session, a refused callback,
Document Server errors, missing download URLs and unrelated version changes do
not count as saves. Duplicate confirmed callbacks are harmless; stale attempts
cannot acknowledge a newer one. A browser-export fallback persists actual bytes
and carries the same attempt ID. Older clients without attempt IDs cannot get a
positive polling confirmation; reload open editor pages after upgrading.

A failed or timed-out operation leaves the editor open. Do not claim success or
close it automatically. `downloadAs` events do not identify their initiating
request, so after an export timeout a second export is blocked until the late
response has been consumed. This prevents an old export from satisfying a new
save. A retry after an uncertain commit may report a conflict: inspect the stored
version before retrying again.

## Operator recovery

Run these commands **against the intended deployment only**, using its exact
Compose configuration/project and backend service. Replace `COMPOSE` below with
that deployment's `docker compose --env-file … -p … -f …` invocation. These
commands do not require scheduled jobs. First take a paired database/files
backup and rehearse recovery on an isolated copy when practical.

1. Find the file UUID in the document URL or its delete audit event. List retained
   versions (read-only):

   ```sh
   COMPOSE exec -T backend python -m app.document_recovery list --file-id FILE_UUID
   ```

2. Restore a deleted case document using a recovery UUID and the UUID of an
   active administrator:

   ```sh
   COMPOSE exec -T backend python -m app.document_recovery restore \
     --recovery-id RECOVERY_UUID --actor-id ADMIN_UUID
   ```

   A deletion group is restored together, parent before attachments. A folder
   deletion group restores all its recorded documents. Existing IDs or names,
   missing parent/matter/owner records and checksum mismatches stop the operation;
   the database transaction rolls back. No existing document is overwritten.

3. Restore a prior version of an existing case document, after releasing its edit
   session and checking its current version:

   ```sh
   COMPOSE exec -T backend python -m app.document_recovery restore \
     --recovery-id RECOVERY_UUID --actor-id ADMIN_UUID --expected-version CURRENT_VERSION
   ```

   The current version is itself retained. A stale expected version is rejected.
   Missing current bytes can be repaired from a verified archive. Confirm the
   document opens and inspect the `case.file.recover` audit event after success.

4. For non-case files (precedents, letterheads) or a missing matter, export verified
   bytes for a reviewed re-import through the appropriate feature:

   ```sh
   COMPOSE exec -T backend python -m app.document_recovery export \
     --recovery-id RECOVERY_UUID --output /tmp/recovered-document.docx
   ```

   Export refuses to overwrite an existing output file. Copy it out using the
   deployment's Compose `cp` command. Use the filename/format recorded by `list`.

Recovery reconstructs File metadata and bytes. It deliberately does not
reconstruct deleted sharing grants, edit sessions, precedent links or financial
references. Review any related records separately. Archives with missing bytes
cannot recreate them; use a verified backup. This feature is not a substitute
for database/files backups or protection against loss of the storage device.

## Retention and upgrades

No cleanup or retention job is installed or enabled. Old paths, recovery copies
and uncommitted orphan candidates are retained, so storage usage grows with
saves/deletions. Include hidden `.versions` and `.recovery` directories in backups
and monitor disk space. Do not delete them manually or treat an unreferenced
path as proof that a transaction failed. A future retention tool must cross-check
committed pointers/recovery records and have an explicit retention policy.

The migration is additive; existing document paths remain readable. Deploy
backend and frontend together. Downgrading the database drops recovery manifests
and attempt metadata, so export them and retain a paired backup first; restoring
the previous app image without dropping the additive schema is preferable.

## Regression coverage

`tests/test_document_durability.py` injects write/commit failures and tests
recovery, checksum rejection, callbacks and WebDAV revocation. The existing
session-release tests assert that no synthetic version bump occurs.
`tests/test_document_durability_postgres.py` checks competing row-lock updates
and real foreign-key cascade recovery. `scripts/test-core-workflows.sh` runs the
PostgreSQL checks and browser workflows in a disposable stack. No live data or
scheduled jobs are needed.

## Precedent uploads and comment edits

New precedent upload bytes and parent directories are flushed before publishing
rows. A failed commit acknowledgement never triggers deletion: the commit may
already have succeeded. After an error, inspect the precedent reference before
retrying. A definite rollback can leave an unreferenced candidate; retain it for
review against committed database references rather than automatically deleting
it. This change adds no cleanup job or retry receipt for precedent uploads.

The comment-edit endpoint accepts only matter documents with a `.txt` filename
and `text/plain` MIME type (including charset parameters). It checks the current
locked row before touching bytes. Other document types and system files cannot
be converted to text through this endpoint; valid comments retain the existing
version and recovery behaviour.
