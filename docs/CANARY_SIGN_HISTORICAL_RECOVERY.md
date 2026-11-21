# Canary Sign historical diagnostics and reviewed recovery

These operator-only tools never run automatically. There are no new UI controls, background jobs, portal routes or DocuSign changes. Deploying the migration creates an empty, append-only recovery receipt table; it does not backfill checksums, repair references or regenerate certificates.

## Investigation first

Run `python scripts/canary_sign_recovery.py diagnose` inside the backend environment. It uses a read-only database transaction and reads files without marking requests expired or changing their status. Findings identify missing references/files, legacy missing checksums, mismatches, cross-matter references, metadata size differences, all-signed pending requests and contradictory or incomplete completion evidence. An inaccessible path is reported, not read outside the files root.

A missing baseline is not proof of corruption. Likewise, hashing today's bytes cannot prove they are the originally signed bytes. Compare independently verified, paired database/files backups. A backup comparison establishes consistency as of that backup only. An unrelated certificate in the same matter is not evidence of ownership.

## Prepare evidence in isolation

Verify the selected backup's database and files archive checksums using the deployment/recovery runbook. Restore both to a disposable database and files volume, with no outbound mail/provider access and background jobs disabled. Run the export against that restored environment, never against dev as a substitute for independent evidence:

```sh
python scripts/canary_sign_recovery.py export-evidence \
  --request REQUEST_UUID --artifact certificate \
  --source-label 'Verified backup identity, manifest checksum and investigation reference' \
  --output-dir /review/evidence
```

The new private directory contains the original PDF bytes and metadata recording the request, matter, artifact role, original file ID, observed SHA-256, prior checksum and source label. Export rejects missing, mismatching, cross-matter or invalid PDFs. It does not generate a new certificate. Source labels are operator-attested provenance, not cryptographic proof: retain the verified backup and review its request/file association. Do not hand-edit the evidence to make a correction pass.

## Dry run and review

Copy the evidence bundle to a private operator directory outside application file storage. In the target backend environment, prepare a plan:

```sh
python scripts/canary_sign_recovery.py plan \
  --request REQUEST_UUID --artifact certificate --action baseline \
  --actor ACTIVE_ADMIN_UUID --reason 'Reviewed evidence and intended correction' \
  --evidence-dir /review/evidence > /review/plan.json
```

This is read-only. It records the exact current request/reference/file state, observed bytes, evidence, actor, reason and operation UUID. Its `plan_sha256` binds that complete proposal.

Supported corrections:

- `baseline`: set a missing checksum only when current bytes match the backup and the original file identity matches. This records a reviewed baseline now; it makes no claim about earlier authenticity.
- `restore`: recover an original signed PDF or certificate from the evidence bundle when the target reference/file is missing or its stored checksum mismatches. It creates a new immutable file and updates only that artifact reference. The old file/row is retained. It never replaces a healthy artifact, changes signature fields/status/timestamps, or synthesises a completion event. Snapshot restoration is deliberately excluded.

Requests must be unambiguously completed, and the acting administrator must be active. A missing certificate with no independently linked original remains unresolved; do not manufacture evidence or regenerate an apparently original certificate.

## Apply only after explicit approval

This is a privileged local CLI, not an authentication boundary for untrusted callers. The administrator UUID attributes the correction; the operator must obtain the user's approval of the exact plan before executing:

```sh
python scripts/canary_sign_recovery.py apply \
  --plan /review/plan.json --evidence-dir /review/evidence \
  --approve-plan EXACT_REVIEWED_PLAN_SHA256
```

Apply locks the operation, request and target file; rechecks the reviewed state/evidence; and commits the correction, general audit event and immutable receipt together. Replaying the same operation returns its recorded result. Reusing its ID for another plan or applying a stale plan fails. After a failure, roll back the session and retry the exact approved plan; re-plan only if state changed, with new approval. An acknowledgement lost after commit is resolved by replaying the same plan.

For restore failures, an unpublished immutable candidate may remain on disk. Existing document recovery procedures govern those candidates; do not delete or publish them merely because a command failed. The original reference/data remains intact on transaction rollback.

## Verify and retain evidence

Run `diagnose` again, inspect the explicit recovery audit event, and retain the plan, source backup and receipt. `python scripts/canary_sign_recovery.py receipts` verifies receipt fingerprints and emits a stable manifest suitable for comparing backup/restores. Database triggers reject receipt updates, deletes and truncation. Keep historical corrections for review; diagnostics alone never apply them.

The isolated PostgreSQL suite tests failure rollback, evidence/plan tampering, stale and cross-request plans, concurrent/repeated application, acknowledgement loss and immutable receipts. The core workflow restore test compares receipt manifests and tests the restored mutation guard. No job is enabled by this release.
