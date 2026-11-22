# Hosted Commercial connection — contract 1

Status: Core-side foundation, opt-in and disabled by default. This document defines a proposed server contract; no hosted service or provider migration is included. Core remains self-hosted and independently usable. Firms use their own provider accounts and are billed by providers directly. Canary supplies integration software, not purchased searches or filings.

## Ownership and compatibility

The local Commercial adapter owns provider-specific screens, drafts, request/result schemas and mapping into matter records. Core owns installation activation, encrypted local credentials, operation persistence, authorization and application receipts. The hosted service owns Canary's developer secrets, installation entitlements and provider execution. It must never access a customer's database, filesystem or Core session tokens.

Existing mounted Commercial integrations, credentials, routes, callbacks and migrations remain unchanged. The new tables are separate and empty; there is no credential copying, switching, backfill or scheduled worker. Registering a local adapter is a later explicit migration, not a side effect of attaching the existing package. Core-only operation remains supported.

Configure `CANARY_COMMERCIAL_SERVICE_ENABLED=1` and an operator-controlled `CANARY_COMMERCIAL_SERVICE_ORIGIN` only when a reviewed service is available. The origin must be HTTPS, port 443, without userinfo, path, query or fragment. It is never supplied by browser input, a provider response or adapter payload. Outbound requests refuse redirects and environment proxies, verify TLS, use bounded timeouts and limit decoded responses to 1 MiB. Operators must control DNS/egress for this trusted origin. No arbitrary URL proxy exists. Large documents need a separately reviewed transfer contract; do not weaken these limits to add one.

A dedicated valid `DATA_ENCRYPTION_KEY` is required for new secret writes. Preserve this key in the firm's protected backup/restore procedure. No cloud key or developer secret is installed locally. Local payloads and results are encrypted too. Core's licence code is an activation input, not a provider credential or general-purpose bearer token.

Admin → Integrations always opens a Commercial Overview, including on Core-only installations. The licence key field remains visible but disabled when hosted activation is disabled. Activated installations can replace their key or disconnect locally. The UI describes locally recorded activation, not verified live subscription entitlement: the current contract does not supply subscription state or product entitlements. Existing attached local integrations remain available under Provider settings without requiring hosted activation during the transition. A temporary status failure does not clear known connection/package state or remove existing records. Future hosted provider tabs must use service-verified entitlements, retain read access to existing settings/results when expired, and enforce new-operation entitlement server-side; no hosted provider tabs are added by this UI change. The management endpoints are firm-admin-only (not portal users or master recovery sessions):

- `GET /commercial-connection/status`: enabled, connected, version, installation_id, tenant_id, contract_version; never secrets. Connected means locally activated, not a current service-health guarantee.
- `POST /commercial-connection/activate`: activation_code and expected_version.
- `POST /commercial-connection/disconnect`: expected_version. Clears local service credentials, increments the generation and preserves evidence/firm credentials. This is local disconnection, not remote revocation of a stolen installation token. A future service must offer an authenticated operator revocation mechanism.
- `GET /commercial-connection/credentials/{key}`: key, configured, version only.
- `PUT /commercial-connection/credentials/{key}`: expected_version and secret_json (a secret JSON object encoded as a string), or null to revoke. Keys are adapter-defined identifiers. No endpoint reads plaintext back to browsers.

Credential editing UI and provider-specific connection fields remain the adapter's responsibility. These endpoints do not modify legacy integration settings. All changes use optimistic versions; a revoked credential keeps its incremented version, so delayed refreshes cannot resurrect it. No activation code, credential value, raw remote error or request payload is written to the audit trail. Validation errors on these endpoints never echo input.

## Activation

`POST {origin}/v1/installations/activate`, JSON, `X-Canary-Contract: 1`:

```json
{
  "contract_version": "1",
  "installation_id": "uuid-generated-and-persisted-by-core",
  "expected_tenant_id": null,
  "activation_code": "one-time-or-retry-safe-code"
}
```

HTTP 200 response:

```json
{
  "contract_version": "1",
  "installation_id": "same-uuid",
  "tenant_id": "service-assigned-firm-uuid",
  "installation_secret": "at-least-32-characters"
}
```

The server must authenticate the activation code, bind the installation to the entitled firm and make identical interrupted activation safely repeatable. It must not allow an installation ID alone to retrieve a secret. Credentials must have at least 256 bits of entropy, a bounded lifetime/rotation policy and explicit revocation. An active installation cannot silently move between tenants or origins. Core persists only the encrypted installation secret and the binding, not the activation code. Failed/ambiguous activation can be retried using the persisted installation ID; remote rotation must not invalidate an active secret before Core can recover the result.

Subsequent requests use `Authorization: Bearer <installation_secret>`. The server derives tenant/installation authority from that credential and checks all supplied IDs against it; request IDs and caller-supplied tenant IDs are not authority. Per-tenant limits, entitlement checks and provider destination allowlists are server requirements. Firm staff JWTs never leave Core.

## Local adapters

There are deliberately no production adapters registered by this change. A reviewed local package registers a uniquely versioned adapter name in `app.commercial_connection.ADAPTERS`, with:

- its local credential key;
- strict request and result validators returning canonical JSON objects;
- a transactional local result application callback.

Validators reject unknown fields, unwanted personal data, provider credentials and unsupported operation versions. Core also rejects common credential keys recursively in persisted request/result documents; this defence does not replace strict adapter schemas. Provider credentials travel only in the dedicated transient `credentials` envelope. Neither provider-specific code nor developer secrets belong in Core.

The adapter uses a dedicated SQLAlchemy Session for `prepare`, `exchange` and `apply_result`; these functions own transactions. Pass the actual authenticated firm user, never a fabricated admin or remote identity. Core rechecks matter access on prepare, dispatch, reconciliation and application. A later automated worker needs its own explicit authorization and approval; no worker is included here.

## Operations

Core persists a caller-generated operation UUID before sending. Reusing it with another matter, adapter, tenant, installation or canonical payload is a conflict. The fingerprint is SHA-256 of canonical JSON of installation_id, tenant_id, case_id, adapter and payload; Core sends it as an opaque binding, not proof of authorization. The server stores and echoes the binding and separately compares repeated request contents.

`POST /v1/operations/{operation_id}` uses HTTP 200 for all valid contract responses:

```json
{
  "contract_version": "1",
  "installation_id": "uuid",
  "tenant_id": "uuid",
  "operation_id": "uuid",
  "fingerprint": "sha256",
  "adapter": "provider.operation.v1",
  "payload": {"reference": "adapter-validated-fields"},
  "credential_version": 3,
  "credentials": {"provider-account-fields": "transient-values"}
}
```

Credentials are loaded at dispatch, not copied into the queue. A password change before dispatch uses the new version. Already-in-flight requests cannot be recalled; an update applies to subsequent requests. Refresh results must use expected credential versions and never overwrite a newer password/token or revoked entry.

The server must durably claim `(tenant, installation, operation_id)` before a chargeable/irreversible provider request. Concurrent retries with changed content conflict. Provider-side idempotency or reconciliation is still needed for a crash after provider acceptance but before server recording. This protocol does not promise distributed exactly-once execution.

A response contains contract_version, installation_id, tenant_id, operation_id, fingerprint, state (`pending`, `completed`, `failed`) and, only for completion, an adapter-validated result object. Unknown response fields are rejected. No token updates, credentials or arbitrary error text are accepted in this envelope. `failed` is terminal only when the server knows the operation was not accepted or was definitively rejected; ambiguous provider outcomes must remain pending. Adapters can reconcile detailed provider status through future typed schemas rather than exposing raw responses.

Core transitions:

- `pending`: durable local request, not dispatched;
- `unknown`: persisted **before** the outbound POST; timeout, crash, invalid response or connection change cannot turn this back into a new request;
- `submitted`: service reports pending;
- `completed`: validated encrypted result retained locally;
- `failed`: definitive service rejection;
- `applied`: local effects and application receipt committed together.

`GET /v1/operations/{operation_id}` reconciles unknown/submitted work using only the installation credential. It returns the same response envelope. It must never submit to the provider or require stored firm credentials. A 404, expired entitlement, outage, mismatch or malformed response leaves work unresolved; Core never automatically replays the POST. No operator force-resend/reset endpoint is provided. A later reviewed recovery flow needs proof of non-acceptance before issuing another chargeable request.

A stale response after disconnect/reactivation is rejected using the local connection generation. A result from another installation/tenant/operation/fingerprint/contract is rejected. Terminal local results cannot be overwritten by delayed pending responses.

## Applying results locally

`apply_result` verifies matter access, result hash and receipt under locks. Its callback and the application receipt commit in the same local database transaction. Retry returns the recorded result without invoking the callback again. Application works while the service is disabled or disconnected, so existing records do not depend on subscriptions.

Callbacks must not commit, roll back, make network requests or write files. Core actively rejects callback commits; the trusted adapter must obey the rest of the contract. For document storage, a later adapter must use durable staging/content-addressed or existing idempotent file operations with reconciliation; a database receipt alone cannot atomically commit arbitrary filesystem writes. Ledger entries likewise need stable operation references and the local financial controls. This foundation proves atomic local DB effects, not completed provider-specific document/ledger integrations.

## Tokens and callbacks: explicit limits

Core is the authoritative persistent store for **all firm credentials, access tokens and refresh tokens**. Hosted Commercial may hold them in process memory for the current request only: exclude them from durable queues, request capture, traces, crash dumps, logs and backups. Do not place them in URLs. Canary-owned developer secrets remain in the hosted service's secret store.

Where a provider permits refresh directly from Core without Canary's developer secret, prefer that path. Serialize refresh locally and compare-and-swap the credential version. Where refresh requires the hosted secret, a separate protocol must return new tokens to Core and handle the provider-rotation/response-loss window. Without provider recovery or approved encrypted handoff storage, reauthorization may be unavoidable. This foundation intentionally does not implement token refresh or claim to solve that window.

There is no cloud callback receiver in this change. Do not move the current token-bearing callback handler into a persistent cloud event inbox. Initially prefer Core-driven status checks where supported. Before any provider migration, specify verified callback routing, offline Core behaviour, token delivery, webhook-secret ownership and retention. A callback may update credential-free transaction status; fetching provider data later still requires a new Core-authorized credential-bearing operation.

## Rollout and acceptance

1. Review the contract and provider account/direct-billing arrangements.
2. Build the service and one synthetic adapter against this contract; enforce tenant isolation and no credential persistence server-side.
3. Implement one real adapter, its local credential UI and provider-specific refresh/callback decisions; test sandbox operations and ambiguous outcomes.
4. Explicitly migrate that provider only after acceptance. Preserve old records and receipts; no automatic removal of the mounted package.

Acceptance tests include disabled mode; TLS/origin/redirect rejection; secret redaction; rotation/revocation/version conflicts; tenant/installation binding; concurrent duplicate dispatch; lost responses; receipt conflicts; atomic failed/successful application; revoked local access; and old-session UI responses. Existing Core and mounted-package contract checks must continue to pass. No live provider calls, Actions, scheduler or deployment is necessary for these tests.

## Isolated validation command

`make test-commercial-foundations` builds the local backend and creates a unique disposable PostgreSQL stack on an internal-only network, without published ports, provider credentials or live mounts. It verifies the migration preserves a synthetic legacy integration setting, checks that new tables start empty, runs unit and PostgreSQL concurrency/access tests, and removes its containers/network. Jobs remain disabled. Frontend validation remains `npm test`, `npm run test:outlook`, `npm run lint:ci` and `npm run build` in an isolated build environment.
