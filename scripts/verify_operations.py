"""Integration checks for test-operations.sh, never against an existing deployment."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
import operations as ops

root = Path(sys.argv[1]).resolve()
config = ops.read_json(root / 'compose.json')
if not config['name'].startswith('canaryops-') or config['services']['backend']['environment'].get('CANARY_TEST_FIXTURE') != '1':
    raise RuntimeError('Refusing to test outside a disposable operations stack.')
compose = ops.deploy.compose(root / 'compose.json')
def run(*args):
    return subprocess.check_output(compose + list(args), stderr=subprocess.DEVNULL, text=True).strip()
info = ops.deploy.inspect(run('ps','-q','frontend'))
ip = next(iter(info['NetworkSettings']['Networks'].values()))['IPAddress']
url = 'http://' + ip
export = root / 'export'; export.mkdir(mode=0o700)
(export / '.canary-backup-target').write_text('isolated-fixture')
secret = root / 'export-passphrase'; secret.write_text(secrets.token_urlsafe(48)); secret.chmod(0o600)
gnupg = root / 'gnupg'; gnupg.mkdir(mode=0o700); os.environ['GNUPGHOME'] = str(gnupg)
settings = dict(deployment_config=str(root / 'compose.json'),backup_dir=str(root/'backups'),
                state_dir=str(root/'state'),public_url=url,keep_backups=2,archive_images=True,
                export=dict(directory=str(export),target_id='isolated-fixture',passphrase_file=str(secret)))
ops.atomic_json(root / 'operations.json', settings)
backup = ops.backup_job(settings)
assert backup['status'] == 'ok' and backup['export']['status'] == 'ok'
run('up','-d','--wait','--wait-timeout','120','backend','frontend')

def http_status(path):
    try:
        with urllib.request.urlopen(url + '/api' + path, timeout=10) as response: return response.status
    except urllib.error.HTTPError as error: return error.code

with urllib.request.urlopen(url + '/api/health?token=ops-private-probe', timeout=10) as response:
    request_id = response.headers['X-Request-ID']
    assert len(request_id) == 32
for attempt in range(20):
    logs = {service: run('logs','--no-color',service) for service in ('backend','frontend')}
    if all(request_id in value for value in logs.values()): break
    time.sleep(0.1)
assert all(request_id in value and 'ops-private-probe' not in value for value in logs.values())
assert http_status('/health/ready') == 200
assert http_status('/admin/health') in (401,403)
run('stop','db')
try:
    assert http_status('/health') == 200
    assert http_status('/health/ready') == 503
    assert ops.monitor_job(settings)['checks']['database']['status'] == 'failed'
finally:
    run('up','-d','--wait','--wait-timeout','120','db')
run('stop','onlyoffice')
try:
    assert http_status('/health/ready') == 200
    report = ops.monitor_job(settings)
    assert report['checks']['database']['status'] == 'ok'
    assert report['checks']['onlyoffice']['status'] == 'failed'
finally:
    run('up','-d','--wait','--wait-timeout','600','onlyoffice')
recovery = ops.recovery_job(settings)
assert recovery['status'] == 'ok'
report = ops.read_json(recovery['report'])
assert report['cleanup'] == 'ok'
assert report['complete_bundle']
assert report['integrity']['secrets']['checked'] >= 2
assert report['integrity']['secrets']['failed'] == 0
assert report['optional_package_files']
assert report['verification']['documents_checked'] >= 1
assert report['verification']['ledger_accounts_checked'] >= 1
assert ops.monitor_job(settings)['status'] == 'ok'
# Corruption must fail before a restore can create any Docker resources.
latest = Path(backup['last_verified_backup'])
encrypted = export / backup['export']['filename']
with encrypted.open('ab') as stream: stream.write(b'corrupt')
try:
    ops.recovery_input(latest,settings,root/'state')
except RuntimeError:
    pass
else:
    raise AssertionError('Corrupted export was accepted')
print(json.dumps({'status':'passed','encrypted_restore':True,'document_hashes':True,'ledger_balances':True,
                  'private_request_diagnostics':True,'database_failure':True,'office_failure':True,'corruption_rejected':True,'isolated_cleanup':True}))
