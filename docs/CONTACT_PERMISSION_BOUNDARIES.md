# Contact and matter permission boundaries

A contact portal login covers all matters associated with that contact. Staff may
read or manage that login only when they can access every matter linked through
matter contact links, grants, matter access, forms, quotes and signing recipients. Retained and inactive
links count, since reactivation may restore access. The server derives these
links; an optional `case_id` cannot narrow the check. A contact with no matter
links retains the existing global address-book access policy. Effective firm
administrators retain access.

The same rule applies to notification preferences, invitations, deletion and
full grant listings. Matter-specific grant mutations retain their existing
matter checks. Resolving a duplicate-email login requires permission for both
contacts, before revealing the other login or changing its grants.

Staff may preview and merge duplicate contacts only when they can access every
matter associated with both contacts. The check covers matter links, retained
portal grants/access, forms, quotes, signing recipients, ledger accounts,
invoices, portal activity, revocation blocks and grant-view records. Inactive or
historical records are included. Contact-wide access/OTP records follow this
combined contact scope. Unlinked contacts remain mergeable by staff.

The existing record-read permissions for these types are matter-based; merging
contact references does not grant ledger posting or approval rights. Effective
administrators retain their existing matter access. Missing/unresolvable matter
references fail closed. Both preview and the service-level merge require an
actor and run the check; preview grants no reusable authorization.

Merge locks both contacts, existing dependent records and their parent records,
then affected matters and access rules within the merge transaction. This blocks
new contact references and concurrent changes to the checked authorization
state until commit/rollback. Locks may briefly delay concurrent edits on the
same contacts/matters. Denied requests can still generate security audit events,
but do not merge contacts, reset codes or change business records. A regression
asserts that every contact foreign-key table has an authorization classification,
so new record types must be accounted for when extending the schema.

Changing a matter's fee earner requires the current fee earner or an effective
administrator. Eligibility of the new fee earner is still checked. Requests that
carry the unchanged fee-earner ID do not require additional authority. Access
mode checks use the existing assignment, including when both fields are sent in
one request.

Pending email-open previews recheck matter access, file ownership and email file
type before returning metadata. Invalid or expired entries are cleared. A valid
preview does not consume the pending open; claim remains a separate operation.

These are authorization changes, with no schema migration or external provider
calls. Existing client portal sessions are not globally revoked by deployment;
credential exposure that occurred before the fix requires separate incident
assessment and targeted rotation where warranted.
