# Self-contained document regression fixtures

The blank-email, digital quote-letterhead and quote-table cleanup tests generate
their own DOCX assets. They do not require a developer's Downloads directory,
pre-seeded firm templates, real clients or production documents.

`tests/document_fixture_helpers.py` supplies a fresh synthetic matter and user,
reserved blank-email/blank-letter templates, a quote table and a small generated
header image. Files live in pytest's temporary directory. Reserved precedent
references and letterhead settings are changed only in the test transaction and
restored by rollback. The tests inspect decompressed DOCX XML for substitutions;
searching compressed ZIP bytes cannot reliably validate document text.

The database-backed compose tests require a migrated disposable PostgreSQL
instance, as do the existing integration tests. The pure quote-table test needs
no database. Do not point the integration suite at dev or a live database.

To include the optional Commercial tests, mount a compatible Commercial package
read-only and set `COMMERCIAL_PACKAGE_DIR` to that package root (containing
`canary-commercial.json` and `python/canary_commercial`). The Casera tests check
PDF creation/status formatting/risk normalization; the DocuSign tests calculate
signature/date-field placement. Neither requires provider credentials or calls.

Run the following inside the isolated backend test container, with a synthetic
`DATABASE_URL`, temporary `FILES_ROOT`, no published ports and an internal-only
Docker network. Keep `CANARY_BACKGROUND_JOBS_ENABLED=0` and
`CANARY_COMMERCIAL_SERVICE_ENABLED=0`:

```sh
alembic upgrade head
python -m pytest -p no:cacheprovider -q tests -rs
```

For the previously skipped coverage alone, select:

```sh
python -m pytest -p no:cacheprovider -q -rs \
  tests/test_casera_placeholder.py tests/test_docusign_tabs.py \
  tests/test_blank_email_compose.py tests/test_compose_quote_digital_letterhead.py \
  tests/test_quote_table_cleanup.py
```

The expected focused result is 14 passing tests with no skips (12 previously
unexecuted tests plus two neighbours). Verify the final full-suite skip summary
as well. Core-only environments may still intentionally skip optional Commercial
modules when no package is supplied; such a run is not complete combined coverage.
