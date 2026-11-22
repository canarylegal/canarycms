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

Global contact merges and merge previews require an effective firm administrator
(built-in admin role or the permission category's Admin flag). A merge rewrites
portal identities, matter links, ledger/invoice and signing references across
the installation. Service-level merge authorization also enforces this rule.
Staff with ordinary matter access can continue to manage permitted portal logins
but must ask an administrator to merge duplicate contacts.

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
