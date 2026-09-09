# Canary CMS — common developer commands (run from repo root).

.PHONY: help test-backend smoke-portal smoke-portal-ci smoke-portal-reset smoke-security

help:
	@echo "Targets:"
	@echo "  make test-backend         Unit tests (pytest in backend/)"
	@echo "  make smoke-portal         Portal quote/form/Canary Sign smoke (running Docker stack)"
	@echo "  make smoke-portal-ci      Same + ensure fixture (CI / empty DB friendly)"
	@echo "  make smoke-portal-reset   Ensure fixture, reset demo pending items, then smoke"
	@echo "  make smoke-security       Live security verification harness"

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
