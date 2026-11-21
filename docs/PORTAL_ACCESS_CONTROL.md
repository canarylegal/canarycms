# Portal access and revocation

Portal requests carry their verified session in the request-scoped SQLAlchemy
unit of work. `portal_policy.authorize` enforces current contact/matter access,
portal enablement, session generation and resource scope. Internal staff and
background service calls without a portal principal retain their own authorization
paths. New portal entry points must use `get_portal_contact` and the policy before
reading resources and before committing mutations; never substitute a raw Contact
for a verified principal in a public endpoint.

Exchange sessions are limited to their matter. Client-only forms, quotes and
Canary Sign require client access. Signing-link sessions are limited to one
request; authenticated access-code sessions retain the normal portal experience.
List and direct download routes enforce the same boundaries.

## Mutation ordering

At the durable write boundary take shared locks on Contact, FirmSettings, Case,
then the appropriate portal access row. Folder uploads also lock and revalidate
the grant. Form/signing mutations then lock their workflow row and refresh it.
These shared locks prevent revocation updates from committing in the middle of
an authorized mutation while allowing independent portal writes to progress.
Uploads stream/write candidate bytes before this boundary; authorization failure
removes unpublished candidate bytes. A revocation that commits before the boundary
causes rejection. If the mutation owns these locks first, revocation waits for its
transaction and later requests are rejected.

Uploads, removals and completion lock the same form submission. Pending status
and attachment responses are refreshed under that lock, preventing lost updates
and modifications after snapshot completion. Stale or forged attachment references
in a submitted payload are rejected; they cannot replace server-owned references.
Session expiry is also rechecked at the write boundary. Bytes are retained after ambiguous
commit errors; never delete a possibly committed file because the acknowledgement
was lost. Existing document recovery diagnostics can identify unreferenced files.

## Links and legacy compatibility

New Canary Sign invitations bind their token to the contact's current access
version. Link exchange accepts only pending, unexpired requests and outstanding
recipients, and issues a request-scoped session. Credential rotation invalidates
old sessions and links. An explicit new reminder rotates a stale/unbound link and
queues its new binding through the existing durable outbox; it does not send old
queued content under new credentials. No automatic resend or scheduling is added.

Migration `fea7a8b9c0d1` adds a nullable recipient access-version binding and the
matter-contact revocation table. It does not backfill historical links, rotate
access codes, modify documents/signatures, or enqueue mail. Historical unbound
links fail closed with instructions to use the access code; an authorized staff
reminder can issue a fresh link. Existing authenticated clients can still view
completed artifacts when their current portal rights allow it. An already-issued
request-scoped session can read that request's completed artifacts, but a completed
link cannot initiate a new session.

File-open tokens retain their 120-second default lifetime and additionally carry
the issuing session's audience, matter, expiry and access generation. Redemption checks
current access as well as grant/file scope. They do not contain a reusable signed
portal login token. Previously issued unbound file-open URLs must be reopened
from the portal after deployment.

## Removing a matter contact

Removing the last matching contact snapshot records an audited matter-specific
block, expires that contact's folder grants, disables exchange login and invalidates
Canary Sign link bindings on that matter. Other matters and the global client's
login remain intact. Removing one of multiple remaining snapshots does not revoke
the relationship. Explicitly adding the contact again clears the block; expired
grants and disabled exchange access are not silently restored, and historical
signing links require a fresh reminder. Historical form/signature records remain.

## Regression checks

`tests/test_portal_access_postgres.py` exercises production routes and dependencies
against isolated PostgreSQL with synthetic clients/files, no real mail and jobs
disabled. It covers the original seven finding groups, signing-link scope and
completion, credential rotation, both transaction orders of revocation, concurrent
form uploads/completion, candidate cleanup and ambiguous commit preservation.
It runs in `scripts/test-core-workflows.sh` alongside existing document, financial,
notification, browser, restart and restore checks. DocuSign is outside this release.
