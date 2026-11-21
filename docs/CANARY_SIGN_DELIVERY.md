# Durable Canary Sign invitations and reminders

New signing invitations and reminders are queued in the same transaction as their signing/audit changes. A failed enqueue rolls back the business action. Payloads (including signing links and any already-provisioned portal access code) and recipient/access bindings are encrypted at rest. This release does not change login-code generation or queue historical messages.

Existing Send, Amend and Remind actions trigger a best-effort delivery wakeup **after commit**. Submitting a signature also wakes pending invitations so sequential recipients can receive their invitation when eligible. These are on-demand user-action tasks, not scheduled jobs. `CANARY_BACKGROUND_JOBS_ENABLED=0` and disabled timers remain unchanged. A crash can leave work pending for operator dispatch; there is no startup or periodic sweep.

The UI layout and interactions are unchanged. A successful API action now confirms **queued**, not provider delivery. Provider acceptance is recorded separately and does not prove inbox delivery or reading.

## Retries and cancellation

The current client retains an `X-Document-Operation-ID` across uncertain Send/Amend/Remind responses and reloads in the same tab. A repeated key with matching inputs returns the original operation; changed inputs are rejected. Other API clients must retain this header for retries. Without a key, a reminder is a new explicit command. Source-file locking also prevents concurrent creation of multiple pending requests for the same document.

Dispatch commits an attempt before contacting a provider. Competing dispatchers cannot send that attempt again. A second eligibility check occurs after the claim and immediately before the provider call. Signing/cancellation and the provider call share the request lock: an already-started send cannot be recalled, but a cancellation committed before delivery prevents it.

Checks include request state/expiry, firm/matter enablement, outstanding recipient status and routing order, destination/contact identity, signing-token identity, portal access, code identity and session version. No new access code is generated during delivery. Later sequential signers remain pending with `waiting_turn`; inactive or changed targets are cancelled rather than silently redirected. Missing transport configuration is a reviewable failure, not a dropped message.

SMTP's explicit rejection is recorded as failed. A timeout, unexpected Graph response or unknown transport result is **uncertain**. No failed/uncertain/sending message is automatically retried. Stable notification IDs aid provider investigation but are not a guarantee of exactly-once email delivery. A crash after provider acceptance but before recording the result leaves `sending`, never a false recorded success.

## Operator diagnostics and explicit action

Run inside the backend environment:

```sh
python scripts/canary_sign_notifications.py diagnostics
python scripts/canary_sign_notifications.py dispatch --id DELIVERY_UUID --actor-id ADMIN_UUID
```

Diagnostics are read-only and omit addresses, bodies, signing tokens, access codes and provider response text. They expose request/recipient/delivery IDs, current state/version, eligibility, attempt codes and stale claims. Staff-notification batch dispatch excludes external signing mail; the dedicated signing command requires an active administrator. User-action dispatch is restricted to active staff with matter access.

To retry a definite rejection or unconfigured transport after resolving it:

```sh
python scripts/canary_sign_notifications.py retry --id DELIVERY_UUID --actor-id ADMIN_UUID \
  --expected-version CURRENT_VERSION --reason 'Reviewed evidence and resolved failure'
python scripts/canary_sign_notifications.py dispatch --id DELIVERY_UUID --actor-id ADMIN_UUID
```

For `sending` older than 15 minutes, first review with `mark-uncertain`. For uncertain outcomes, inspect provider evidence and use `--acknowledge-uncertain` on retry only after explicitly accepting possible duplicate delivery. Review actions are version-checked and audited. `cancel` supports pending/failed/uncertain deliveries; it cannot recall an accepted or actively sending message. Cancelled stale invitations are not revived by retry: create a new explicit reminder after confirming current eligibility.

No dispatch command was run against dev during verification, and no real recipient mail was sent by deployment testing. No scheduler is installed or enabled. DocuSign dispatch and templates are outside this release.

## Validation

`test_canary_sign_delivery_postgres.py` uses synthetic contacts and fake senders only. It covers atomic queue rollback, encrypted payloads, HTTP operation replay, concurrent dispatch/reminders, sequential eligibility, cancellation in the claim gap, expiry, token/access/destination changes, provider rejection/timeouts and result-commit failure. Browser retry identities are covered by frontend unit tests. The core workflow restart/restore manifest also authenticates signing delivery bindings and verifies retained attempts.

Diagnostic detail is bounded to 200 deliveries by default (maximum 1,000), with unresolved work listed first and aggregate counts across the entire matching queue. Use `diagnostics --request-id REQUEST_UUID --limit 200` to investigate a particular request; `has_more` indicates additional detail exists. No payloads are printed.
