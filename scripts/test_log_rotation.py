"""Resolve shipped policies and prove Docker rollover without touching a deployment."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
POLICY = {'driver': 'json-file', 'options': {'max-size': '10m', 'max-file': '5'}}


def verify_policies():
    env = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'XDG_RUNTIME_DIR')}
    for path in ROOT.glob('docker-compose*.yml'):
        for key in re.findall(r'\$\{([A-Z_]+):\?', path.read_text()):
            env[key] = 'isolated-test-only'
    env['CORE_TEST_OUTPUT'] = '/tmp/canary-log-test-artifacts'
    combinations = [(['docker-compose.yml'], 6),
                    (['docker-compose.yml', 'docker-compose.dev-tunnel.yml'], 8),
                    (['docker-compose.core-test.yml', 'docker-compose.performance.yml'], 5)]
    for files, expected in combinations:
        command = ['docker', 'compose', '--env-file', '/dev/null', '--profile', '*']
        for name in files:
            command += ['-f', str(ROOT / name)]
        config = json.loads(subprocess.check_output(command + ['config', '--format', 'json'], env=env))
        assert len(config['services']) == expected, files
        for name, service in config['services'].items():
            assert service.get('logging') == POLICY, (files, name, service.get('logging'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, help='Already available image with Python; never pulled')
    args = parser.parse_args()
    verify_policies()
    subprocess.run(['docker', 'image', 'inspect', args.image], stdout=subprocess.DEVNULL, check=True)
    name = 'canary-logcheck-' + uuid.uuid4().hex
    code = "import sys; print('OLDEST-ROTATION-MARKER',flush=True); [print('x'*8191) for _ in range(7680)]; print('LATEST-ROTATION-MARKER',flush=True)"
    try:
        subprocess.run(['docker', 'run', '--name', name, '--pull', 'never', '--network', 'none',
                        '--memory', '128m', '--cpus', '0.5', '--log-driver', 'json-file',
                        '--log-opt', 'max-size=10m', '--log-opt', 'max-file=5',
                        '-e', 'CANARY_BACKGROUND_JOBS_ENABLED=0', '--entrypoint', 'python', args.image, '-c', code],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120, check=True)
        info = json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]
        assert info['HostConfig']['LogConfig'] == {'Type': POLICY['driver'], 'Config': POLICY['options']}
        assert not info['State']['OOMKilled'] and info['State']['ExitCode'] == 0
        with tempfile.TemporaryFile() as stream:
            subprocess.run(['docker', 'logs', name], stdout=stream, stderr=subprocess.PIPE, timeout=30, check=True)
            retained = stream.tell()
            stream.seek(0); first = stream.read(8192)
            stream.seek(max(0, retained - 8192)); last = stream.read()
        assert 0 < retained < 50 * 1024 * 1024, retained
        assert b'OLDEST-ROTATION-MARKER' not in first
        assert b'LATEST-ROTATION-MARKER' in last
        print(json.dumps({'passed': True, 'compose_variants': 3, 'policy': POLICY, 'emitted_bytes_minimum': 60 * 1024 * 1024, 'retained_stdout_bytes': retained}))
    finally:
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, check=True)


if __name__ == '__main__':
    main()
