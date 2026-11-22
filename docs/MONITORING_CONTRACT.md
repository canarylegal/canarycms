# Optional generic monitoring (version 1)

Core works without monitoring configuration, a monitoring account, network access to a receiver, or Odin. This feature is a separate host command, `scripts/monitoring_delivery.py`. It is not imported by the application, Compose startup, migrations, deployment, backup or local health probes. Nothing installs or enables a job. No licence, feature gate, provider integration, credentials API or inbound application endpoint is added.

The receiver owns incident thresholds, deduplication, notification destinations, acknowledgement, escalation and maintenance windows. Odin is one possible receiver, with no special code or dependency in Core. A receiver must implement the contract below: an arbitrary chat webhook or simple ping service is not automatically compatible; those need a receiver-side adapter. SMTP/recipient delivery belongs to the chosen receiver in this implementation.

## Preparation only

Copy `ops/monitoring.example.json` to a private, operator-owned configuration file and keep `enabled` false until activation is separately authorised. Missing configuration, an omitted `--config`, or explicit `enabled: false` exits successfully with `status: disabled` and makes no state directory, credential read or network request. Malformed configuration fails this command only, with a sanitised error; Core keeps running. Removing/turning off configuration disconnects delivery and retains any existing outbox.

An enabled configuration requires:

- A fixed HTTPS `endpoint` with no userinfo, query string or fragment. No redirects or ambient HTTP proxies are followed. Certificate and hostname verification are mandatory. An optional absolute `ca_file` supports an operator-managed private CA, not an insecure TLS mode.
- An opaque canonical UUID `installation_id`, assigned by the installation operator. It is not a licence key. Register it with the receiver explicitly; registration is outside Core.
- A private owner-only `token_file`, containing a scoped bearer credential. Obtain it directly from the receiver, store it locally and rotate/revoke it there. The receiver must bind it to the permitted installation; never trust the body installation ID alone. No machine-management permission is needed.
- Absolute paths for `state_dir` and `report_file`. The state directory must be operator-owned, 0700 and not a symlink; the enabled configuration and token must be owner-only regular files. Use a dedicated state directory outside live data and the source checkout.
- `expected_checks`, explicitly listing coverage. Defaults cover the application probe, database, storage, document server and public access. Only add backup/recovery once their schedules and freshness policy are approved. An excluded check is reported as `disabled`, never healthy. The receiver should enforce its own agreed coverage so disabling a check cannot silently remove oversight.

The report source is the existing operations `health-status.json`. The reporter does not run the monitor or enable its schedule. Existing health endpoints, diagnostics, backups and recovery commands continue independently. See [operations](OPERATIONS.md) for generation of this local report. A missing/stale report produces unknown coverage and suppresses the delivery heartbeat; it never implies a healthy application.

Manual invocation, only after reviewing a private test configuration:

```sh
python3 scripts/monitoring_delivery.py --config /private/test-monitoring.json
```

There is deliberately no new systemd timer or activation command. A future authorised scheduler should run the independent command after the local monitor, typically every five minutes. Failure of one invocation must not stop Core or prevent the next local monitor. A successful delivery result describes reporting, not application health: a fresh observation can correctly report database failure while the reporting command succeeds.

## Wire contract

Machine-readable schema: [monitoring-v1.schema.json](contracts/monitoring-v1.schema.json). POST JSON to the configured endpoint using `Content-Type: application/json`, `Authorization: Bearer …`, and `Idempotency-Key` equal to the event UUID. No business records, raw URLs, hostnames, report details, filenames, credentials or exception messages are included. The allowlist is applied before sending, including when loading queued payloads after restart.

Common fields are `schema_version: 1`, `kind`, `event_id`, `installation_id`, `stream_id` and `created_at`. All IDs are canonical UUID strings. All times are integer UTC Unix seconds. The stream ID identifies one durable reporter-state generation.

An `observation` additionally contains:

- `sequence`: a strictly increasing positive integer within the stream.
- `source_observed_at`: the source report timestamp, or null when unavailable/unparseable. A timestamp may be stale or future-dated; it must not be treated as proof of freshness.
- `checks`: exactly `application`, `database`, `storage`, `onlyoffice`, `public_access`, `backup`, `recovery`, and `monitor_source`. Values are `up`, `down`, `unknown`, `disabled`, or `not_configured`.

The source must be structurally valid and no more than 600 seconds old, with no future timestamp, to set `monitor_source` up. Missing required checks remain unknown. `application` up means the local application probe returned database/storage results, not that those dependencies are healthy. An explicit application probe failure is down. Older source observations cannot reset freshness after a newer one. Duplicate unchanged source observations are not requeued; fresh reports with new timestamps are reported even if check states are unchanged. Stale/invalid source input never resolves failures by claiming healthy states.

A `heartbeat` additionally contains `last_observation_sequence`. It confirms that this invocation consumed a fresh source and drained/acknowledged its observation queue. It does not assert healthy dependencies. It is sent only after successful queue delivery and a final source-age check. It is never queued for replay: an old heartbeat arriving late must not revive a dead reporter. The receiver must check heartbeat `created_at`, its own clock/skew policy and observation sequence, rather than using arrival time alone. If its latest observation is older than the referenced sequence, show incomplete coverage instead of healthy coverage.

## Receiver obligations

1. Authenticate and scope the credential before accepting a payload. Validate version, sizes and schema. Keep credentials and identifiers out of public logs as appropriate.
2. Commit an observation durably before returning any 2xx. Treat duplicate event IDs/stream sequences idempotently and acknowledge already accepted events. Delivery is at-least-once, not exactly-once.
3. Preserve observation ordering per stream. Delayed queued observations are history, not evidence of current health. Apply source freshness independently; never resolve an active incident from an old healthy snapshot. Retain a per-stream sequence watermark to reject duplicate/out-of-order state changes even when detailed event history expires.
4. Recognise a new stream as an explicit reporting-generation change. On lost/restored reporter state, the operator must reconcile or register a replacement stream; do not silently trust a reset sequence as continuous coverage. The receiver decides whether/how a new stream supersedes an old one.
5. Track missed heartbeats independently of Core and of the Core host. Notify through receiver-owned channels. There is no inbound command or application-management capability in this contract.
6. Ignore no unsupported versions silently: reject them so the reporter remains visibly degraded. Version 1 does not include an automatic enrolment, capability-negotiation or configuration-control API.

## Durability and bounds

State is atomically replaced and fsynced under a nonblocking single-writer lock. A single reserved `state.tmp` scratch file is reused after an interrupted save, so repeated interruptions do not accumulate temporary files. State/credential/report files are bounded and symlinks are refused. Corrupt, oversized or foreign-destination state fails closed; it is not discarded. State is bound to endpoint plus installation ID. Changing recipients at the receiver or rotating the same destination token does not reset the queue. Changing endpoint/installation requires a separately reviewed fresh state directory or deliberate reconciliation, so old events cannot leak to a different destination.

The outbox holds at most 100 observations in a state file capped at 512 KiB. A full outbox does not silently discard observations: the command reports `queue_full`, attempts bounded draining, suppresses heartbeat, and retries collection on the next invocation. A later fresh full snapshot restores current coverage after draining; intermediate changes not collected while full cannot be reconstructed. Pending events are not automatically deleted by age. A receiver must distinguish historical observation delivery from current status.

Each invocation attempts at most five queued observations and one heartbeat. A separate child process bounds each network attempt to six seconds, including DNS stalls; the HTTPS socket timeout is three seconds. Response bodies are not consumed, stored or logged. The network budget is therefore at most 36 seconds per invocation; local filesystem operations are not covered by that network deadline. No retries occur within an attempt. Failed observations remain durable with 30-second exponential retry delays capped at five minutes; numeric `Retry-After` on 429/503 is honoured within that cap. Authentication rejection is reported distinctly, without credential/endpoint details. Heartbeat failure is retried on the next scheduled/manual invocation and never requeues an already acknowledged observation.

These failures affect this host command only. Slow/unavailable receivers, bad credentials, malformed settings, queue pressure and disconnecting monitoring cannot gate Core login, document handling, local integrations or startup. The command emits only a small sanitised status summary; no per-attempt log file or unbounded history is created.

## Tests and review before activation

`python3 -m unittest discover -s scripts/tests -p 'test_monitoring_delivery.py' -v` uses only synthetic reports and loopback TLS with an ephemeral test certificate (requires OpenSSL). Run in a disposable network-disabled container for explicit egress isolation. It covers absent/disabled/misconfigured configuration, queue limits, restart/idempotency, disconnection, malformed/stale/replayed sources, TLS trust, redirects, auth failures, throttling and stalled/unreachable receivers. Existing Core tests remain independent and require no receiver.

Before any production activation: choose an independent receiver, register scoped credentials, agree expected checks/heartbeat cadence, verify recipient delivery and receiver persistence/escalation in isolation, test state-loss/new-stream handling, and separately approve scheduling. No live receiver, Odin deployment, notification channel, background job or GitHub Actions change is part of this feature.
