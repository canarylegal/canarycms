"""Fail CI when a build input drifts back to a mutable dependency."""
from pathlib import Path
import hashlib
import re

root = Path(__file__).resolve().parents[1]
for direct, lock in [('backend/requirements.txt', 'backend/requirements.lock'), ('backend/build-requirements.in', 'backend/build-requirements.lock')]:
    expected = hashlib.sha256((root / direct).read_bytes()).hexdigest()
    content = (root / lock).read_text()
    assert f'# Direct requirements sha256: {expected}' in content, f'Regenerate {lock} after changing {direct}'
    direct_versions = dict(re.findall(r'^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^\s]+)', (root / direct).read_text(), re.M))
    locked_versions = dict(re.findall(r'^([A-Za-z0-9_.-]+)==([^\s]+)', content, re.M))
    normalize = lambda value: re.sub(r'[-_.]+', '-', value).lower()
    locked_versions = {normalize(k): v for k, v in locked_versions.items()}
    for name, version in direct_versions.items():
        assert locked_versions.get(normalize(name)) == version, f'{name} differs between direct inputs and lock'
for name in ['backend/Dockerfile', 'frontend/Dockerfile', 'frontend/Dockerfile.e2e']:
    for image in re.findall(r'^FROM\s+(\S+)', (root / name).read_text(), re.M):
        assert re.search(r'@sha256:[0-9a-f]{64}$', image), f'Unpinned base: {image}'
for path in root.glob('docker-compose*.yml'):
    for image in re.findall(r'^\s*image:\s*(\S+)', path.read_text(), re.M):
        assert re.search(r'@sha256:[0-9a-f]{64}$', image), f'Unpinned image: {path.name}: {image}'
for path in (root / '.github/workflows').glob('*.yml'):
    for action in re.findall(r'uses:\s+([^\s]+)', path.read_text()):
        assert re.search(r'@[0-9a-f]{40}$', action), f'Unpinned action: {action}'
print('Image digests, action commits and Python lock inputs verified.')
