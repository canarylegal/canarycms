import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import operational_health as health
from app.request_diagnostics import RequestDiagnosticsMiddleware, logger


def test_dependency_failures_are_separate_and_sanitized(monkeypatch):
    monkeypatch.setattr(health, 'database_probe', lambda: {'status': 'ok'})
    monkeypatch.setattr(health, 'storage_probe', lambda: {'status': 'ok'})
    def fail(): raise OSError('postgres://secret-password; confidential document')
    monkeypatch.setattr(health, 'office_probe', fail)
    result = health.health_snapshot()
    assert result['ready'] is True
    assert result['status'] == 'degraded'
    assert result['checks']['onlyoffice']['status'] == 'failed'
    assert 'secret' not in json.dumps(result)
    monkeypatch.setattr(health, 'database_probe', fail)
    assert health.health_snapshot()['ready'] is False


def test_storage_checks_read_write_space_and_does_not_create_missing_mount(monkeypatch, tmp_path):
    import app.file_storage
    monkeypatch.setattr(app.file_storage, 'FILES_ROOT', tmp_path)
    monkeypatch.setenv('CANARY_STORAGE_MIN_FREE_BYTES', '0')
    assert health.storage_probe()['status'] == 'ok'
    assert list(tmp_path.iterdir()) == []
    monkeypatch.setenv('CANARY_STORAGE_MIN_FREE_BYTES', str(2**63))
    assert health.storage_probe()['code'] == 'storage_low_space'
    monkeypatch.setattr(app.file_storage, 'FILES_ROOT', tmp_path / 'absent')
    assert health.storage_probe()['code'] == 'storage_missing'
    assert not (tmp_path / 'absent').exists()


def test_readiness_is_minimal_and_detailed_health_is_admin_only(monkeypatch):
    import app.main as main
    snapshot = {'ready': False, 'status': 'degraded', 'checks': {'database': {'status': 'failed'}}}
    monkeypatch.setattr(main, 'health_snapshot', lambda **kwargs: snapshot)
    client = TestClient(main.app)
    response = client.get('/health/ready')
    assert response.status_code == 503
    assert response.json() == {'status': 'not_ready'}
    assert response.headers['cache-control'] == 'no-store'
    assert client.get('/admin/health').status_code in (401, 403)
    main.app.dependency_overrides[main.require_admin] = lambda: object()
    try:
        assert client.get('/admin/health').json() == snapshot
    finally:
        main.app.dependency_overrides.pop(main.require_admin)


def test_request_ids_and_logs_do_not_include_secrets_or_resource_ids(monkeypatch):
    records = []
    monkeypatch.setattr(logger, 'log', lambda level, value: records.append(json.loads(value)))
    app = FastAPI()
    app.add_middleware(RequestDiagnosticsMiddleware)
    @app.get('/documents/{file_id}')
    def document(file_id):
        raise RuntimeError('secret body and database password')
    client = TestClient(app)
    response = client.get('/documents/private-filename?token=secret-query',
                          headers={'Authorization': 'Bearer secret', 'Cookie': 'session=secret', 'X-Request-ID': 'untrusted'})
    assert response.status_code == 500
    request_id = response.headers['x-request-id']
    assert len(request_id) == 32 and request_id != 'untrusted'
    assert response.json()['request_id'] == request_id
    assert records[0]['request_id'] == request_id
    assert records[0]['route'] == '/documents/{file_id}'
    assert records[0]['error_type'] == 'RuntimeError'
    assert records[0]['error_location']['function'] == 'document'
    assert records[0]['error_location']['line'] > 0
    for value in ('secret', 'private-filename', 'untrusted', 'Authorization', 'Cookie'):
        assert value not in json.dumps(records)
        assert value not in response.text
    response = client.get('/unknown-sensitive-filename?password=secret')
    assert response.status_code == 404
    assert records[-1]['route'] == '<unmatched>'
    assert 'sensitive' not in json.dumps(records)


def test_office_timeout_is_bounded_and_not_an_application_readiness_failure(monkeypatch):
    monkeypatch.setenv('ONLYOFFICE_DS_INTERNAL_URL', 'http://office')
    def timeout(url, timeout):
        assert timeout == 3
        raise TimeoutError('private upstream URL')
    monkeypatch.setattr(health, 'urlopen', timeout)
    assert health.probe('onlyoffice', health.office_probe) == {'status': 'failed', 'code': 'onlyoffice_unavailable'}
