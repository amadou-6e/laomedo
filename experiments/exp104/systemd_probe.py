"""One-shot S14 outer controller. Never loads a provider credential."""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import time

from experiments.exp104.systemd_checks import assess

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = 'exp104-systemd-s14-20261010-a'
IMAGE = 'sha256:48b88125a5e7e0b03bb166468b3449ad46c263c4c148f9999098f41768dba793'
DEADLINE = None


def command(args, *, input=None, timeout=30, check=True):
    if DEADLINE is not None:
        timeout = min(timeout, DEADLINE - time.monotonic())
        if timeout <= 0:
            raise TimeoutError('overall_deadline')
    result = subprocess.run(args, input=input, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError('command_failed')
    return result


def inspect(name):
    result = command(['docker', 'inspect', name], check=False)
    if result.returncode:
        if ('Error: No such object: ' + name).encode() in result.stderr:
            return None
        raise RuntimeError('inspection_unavailable')
    return json.loads(result.stdout)[0]


def run(destination, source, review):
    global DEADLINE
    if destination.resolve() != (Path(tempfile.gettempdir()) / IDENTITY).resolve():
        raise ValueError('identity_root_mismatch')
    if (command(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']).stdout.decode().strip() != source or
        command(['git', '-C', str(ROOT), 'status', '--porcelain']).stdout.strip()):
        raise ValueError('source_not_exact_clean')
    approval = json.loads(review.read_text(encoding='utf-8'))
    if approval != {'identity': IDENTITY, 'source': source, 'image': IMAGE,
                    'verdict': 'approve', 'reviewer_session': '75a72664-34f4-412d-8699-f167e79ebe78'}:
        raise ValueError('review_record_mismatch')
    claim = Path(tempfile.gettempdir()) / (IDENTITY + '.claimed')
    descriptor = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    destination.mkdir(parents=True, exist_ok=False)
    DEADLINE = time.monotonic() + 240
    result = {'identity': IDENTITY, 'source': source, 'image': IMAGE,
              'review_sha256': sha256(review.read_bytes()).hexdigest(), 'status': 'incomplete',
              'stage': 'create', 'model_turns': 0, 'provider_credentials': 0}
    name, token = IDENTITY, secrets.token_hex(16)
    container_id = None
    try:
        created = command(['docker', 'create', '--name', name, '--label', 'laomedo.s14=' + token,
            '--privileged', '--cgroupns=private', '--network=none', '--memory=256m',
            '--memory-swap=256m', '--cpus=1', '--pids-limit=128',
            '--tmpfs', '/run:rw,size=32m', '--tmpfs', '/run/lock:rw,size=4m', IMAGE])
        container_id = created.stdout.decode().strip()
        if not re.fullmatch('[0-9a-f]{64}', container_id):
            raise ValueError('container_identity_missing')
        info = inspect(container_id)
        if (info['Image'] != IMAGE or info['Name'] != '/' + name or info.get('Mounts') or
            info['HostConfig']['CgroupnsMode'] != 'private' or info['HostConfig']['NetworkMode'] != 'none' or
            info['HostConfig']['PidMode'] or info['Config']['Labels'].get('laomedo.s14') != token):
            raise ValueError('container_boundary_mismatch')
        result['stage'] = 'copy_tracked_source'
        archive = command(['git', '-C', str(ROOT), 'archive', source, 'laomedo',
            'experiments/exp104/systemd_fixture.py']).stdout
        command(['docker', 'cp', '-', container_id + ':/opt'], input=archive)
        result['stage'] = 'systemd_boot'
        command(['docker', 'start', container_id])
        deadline = time.monotonic() + 30
        ready = False
        while time.monotonic() < deadline:
            probe = command(['docker', 'exec', container_id, 'systemctl', 'show', '--property=Version'], check=False)
            if probe.returncode == 0:
                ready = True
                break
            current = inspect(container_id)
            if current is None or not current['State']['Running']:
                break
            time.sleep(.2)
        if not ready:
            raise RuntimeError('systemd_not_ready')
        result['stage'] = 'capture'
        capture = command(['docker', 'exec', '-e', 'PYTHONPATH=/opt', container_id,
            'python3', '/opt/experiments/exp104/systemd_fixture.py', 'capture'], timeout=200)
        result['capture'] = json.loads(capture.stdout)
        result['assessment'] = assess(result['capture'])
        result['status'] = 'passed'
    except Exception as failure:
        result['error_class'] = type(failure).__name__
        if container_id:
            try:
                log = command(['docker', 'logs', '--tail', '40', container_id], check=False)
                result['boot_log'] = (log.stdout + log.stderr).decode('utf-8', errors='replace')[-8000:]
            except Exception:
                result['boot_log_unavailable'] = True
    finally:
        DEADLINE = time.monotonic() + 30
        try:
            current = inspect(name)
            if current is None:
                result['cleanup_verified'] = True
            elif (current['Name'] == '/' + name and current['Image'] == IMAGE and
                  current['Config']['Labels'].get('laomedo.s14') == token and
                  (container_id is None or current['Id'] == container_id)):
                fresh = inspect(current['Id'])
                if fresh and fresh['Name'] == current['Name'] and fresh['Config']['Labels'].get('laomedo.s14') == token:
                    command(['docker', 'rm', '-f', current['Id']])
                    result['cleanup_verified'] = inspect(current['Id']) is None
        except Exception as failure:
            result['cleanup_error_class'] = type(failure).__name__
        if result.get('cleanup_verified') is not True:
            result['status'] = 'incomplete'
        (destination / 'observation.json').write_text(json.dumps(result, sort_keys=True, indent=2) + '\n',
                                                     encoding='utf-8', newline='\n')
        DEADLINE = None
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--review', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.record, args.source, args.review)))
