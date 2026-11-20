# Isolated performance regression checks

Run `make test-performance`. It builds a new `canaryperf-*` Docker Compose project, creates synthetic data, profiles real PostgreSQL-backed routes, runs Chromium and concurrent HTTP workloads, and removes only that project's containers/network/volumes on exit. No live configuration, credentials, files, database or scheduled jobs are used. The network is internal-only and has no published ports. The seed requires both explicit test flags and the dedicated `canary_core_test` database, and refuses a populated database beyond the initial core fixture.

## Workload and measurement

- 5,002 matters (5,000 synthetic open property transactions plus the two core fixtures), 200 additional fee earners.
- One case with 1,200 real small text files: 400 at the root including 100 attachments, another 800 in folders, five pinned documents, and 100 portal form snapshots sharing five templates and referencing 100 contacts.
- Five measured warm route calls after one discarded warm-up, including serialization and SQL query counts. The SQL profiler uses TestClient against the real migrated PostgreSQL database; the browser/load tests use the actual nginx/HTTP path.
- Chromium sign-in, complete list rendering, fee-earner sorting, search, right-click matter/document menus, double-click matter/folder navigation and the existing display labels. Record renderer heap use after the workflow and count matter-list fetches.
- Four distinct staff accounts, each making five requests to both the complete matter list and the document-heavy case: 20 measurements per endpoint, with status and complete row-count assertions.

CPU/memory limits are explicit in `docker-compose.performance.yml`: backend 2 CPUs/2 GiB, PostgreSQL 1 CPU/1 GiB, nginx 0.5 CPU/256 MiB, Chromium runner 2 CPUs/3 GiB, ONLYOFFICE 2 CPUs/2 GiB. `resource-samples.jsonl` records backend/infrastructure CPU and memory samples during browser/load testing. These are container resource limits, not dedicated physical cores. The document server is started for realistic app routing but editor concurrency is not load-tested here.

## First measured improvements

Baseline source: `e9fe086`. All measurements used disposable containers. Local paired measurements on the same host with the capped synthetic stack:

| Measurement | Before | After |
|---|---:|---:|
| Document-list SQL queries | 213 | 15 |
| Document-list median route time (5 warm samples) | 91 ms | 54 ms |
| Document-list p95 HTTP time (4 staff accounts, 20 requests) | 884 ms | 576 ms |
| Matter-list SQL queries | 8 | 8 |
| Matter-list median route time | 181 ms | 191 ms |
| Matter-list p95 HTTP time | 793 ms | 693 ms |
| Instrumented 5,000-row staff-search/sort ID lookups | 11,237,031 | 200 |
| Instrumented staff-search/sort elapsed time | 232 ms | 10 ms |
| Browser initial list load | 1,241 ms | 1,290 ms |
| Browser search interaction | 564 ms | 592 ms |
| Browser opening the document-heavy matter | 456 ms | 283 ms |

The document fix batches portal-form contact/template metadata instead of issuing two queries per snapshot. The UI fix builds staff-label maps for search, sorting and row display instead of repeatedly scanning the staff list. Response fields, fallback labels, sorting semantics, layout, column controls and double-click/right-click interactions are preserved. No pagination, truncation or response-field removal is used to obtain these results.

The staff microbenchmark counts property reads to detect algorithmic regressions; its instrumented timing is not a browser latency claim. Browser search includes existing debounce/interaction costs. The small change in general list load/search is within the range where this short test does not establish an improvement. Matter responses remain approximately 4 MB and document responses approximately 0.94 MB before compression. Large-list payload/rendering remains a future scaling consideration; these results do not establish a production capacity limit.

## Regression gates

CI runs `.github/workflows/performance.yml` on PRs and main updates. The ordinary frontend suite also asserts that the 5,000-row search/sort performs at most 400 staff-ID reads and retains correct order/results.

The disposable API/browser job fails on:

- More than 30 queries for the document list or 20 for the matter list; a reintroduced per-form lookup fails deterministically.
- Any incorrect row counts, portal-form contact/template/status metadata, HTTP error or broken tested interaction.
- A warm single-route call over 5 seconds, concurrent p95 over 5 seconds, initial UI load over 15 seconds, sorting/search over 5 seconds, or opening the matter over 10 seconds.
- More than three matter-list fetches during the browser workflow.

Timing limits deliberately allow shared-runner variation. They catch large regressions rather than claiming an SLA; smaller changes should be reviewed using the uploaded JSON measurements and the same workload/resource settings. The query/lookup gates provide tighter, hardware-independent protection for the specific bottlenecks fixed here. Ordinary core workflow tests separately cover actual editing/save, access controls, session recovery, upload/download failure handling and column preferences.

Evidence is written beneath `artifacts/performance/` (override with a scratch `CORE_TEST_OUTPUT` directory). It contains only the synthetic fixture's metrics, traces/screenshots and service/build/cleanup logs. Never adapt this upload path to include real backup/configuration data.

A fresh-stack verification also passed the fee-earner UI sort (about 1.5 seconds for 5,002 rows). Its sampled maximum backend memory was about 265 MiB, PostgreSQL 62 MiB, nginx 15 MiB and idle ONLYOFFICE 549 MiB; the renderer reported about 57 MiB of JavaScript heap after the workflow. These are short-run samples, not proven long-term peaks. `resource-summary.json` accompanies the normalized resource samples.

This is a short metadata/list workload test, not a soak test, large-file transfer benchmark, multi-editor benchmark, external integration benchmark or proof of performance at arbitrary database sizes. Repeat with larger agreed workloads before increasing a deployment's expected load.
