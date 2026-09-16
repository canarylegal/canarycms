# Canary CMS — common developer commands (run from repo root).

.PHONY: help test-backend smoke-portal smoke-portal-ci smoke-portal-reset smoke-security test-e2e

help:
	@echo "Targets:"
	@echo "  make test-backend         Unit tests (pytest in backend/)"
	@echo "  make smoke-portal         Portal quote/form/Canary Sign smoke (running Docker stack)"
	@echo "  make smoke-portal-ci      Same + ensure fixture (CI / empty DB friendly)"
	@echo "  make smoke-portal-reset   Ensure fixture, reset demo pending items, then smoke"
	@echo "  make smoke-security       Live security verification harness"
	@echo "  make test-e2e             Thin Playwright browser smoke (running frontend+backend)"

test-backend:
	cd backend && python -m pytest -q

smoke-portal:
	./scripts/smoke-portal.sh

smoke-portal-ci:
	./scripts/smoke-portal.sh --ensure-fixture

smoke-portal-reset:
	./scripts/smoke-portal.sh --reset-demo

smoke-security:
	docker compose exec -T backend python scripts/live_security_verify.py

# Requires stack UI on BASE_URL (default http://127.0.0.1:8080) and staff creds.
# Firm staff (not master recovery) needed for the matter-open path; master is OK for login shell only.
test-e2e:
	cd frontend && BASE_URL="$${BASE_URL:-http://127.0.0.1:8080}" \
	  E2E_STAFF_EMAIL="$${E2E_STAFF_EMAIL:?Set E2E_STAFF_EMAIL}" \
	  E2E_STAFF_PASSWORD="$${E2E_STAFF_PASSWORD:?Set E2E_STAFF_PASSWORD}" \
	  npm run test:e2e
