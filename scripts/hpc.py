"""CLI kubectl tanpa library tambahan. Dapat dipakai dari host atau SSH head."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid


def settings():
    defaults = {'JOB_CPU_M': '500', 'JOB_MEMORY_MIB': '128', 'JOB_LIMIT_CPU_M': '700',
                'JOB_LIMIT_MEMORY_MIB': '256', 'EVICTION_SECONDS': '30'}
    path = Path('/etc/hpc/client.json')
    if path.exists():
        defaults.update(json.loads(path.read_text()))
    return {k: os.environ.get(k, v) for k, v in defaults.items()}


def kubectl(*args, capture=False, body=None):
    p = subprocess.run(['kubectl', '-n', 'hpc', *args],
                       input=json.dumps(body) if body is not None else None,
                       text=True, stdout=subprocess.PIPE if capture else None, check=True)
    return p.stdout if capture else None


def manifest(name, limit, seconds, cfg):
    labels = {'app': 'hpc-compute', 'hpc.local/job': name}
    return {'apiVersion': 'batch/v1', 'kind': 'Job',
            'metadata': {'name': name, 'namespace': 'hpc',
                         'labels': {**labels, 'kueue.x-k8s.io/queue-name': 'hpc'}},
            'spec': {'suspend': True, 'parallelism': 1, 'completions': 1,
                     'backoffLimit': 6, 'activeDeadlineSeconds': 1800,
                     'podReplacementPolicy': 'Failed',
                     'template': {'metadata': {'labels': labels, 'annotations': {
                         'kueue.x-k8s.io/safe-to-forcefully-delete': 'true'}}, 'spec': {
                         'restartPolicy': 'Never', 'terminationGracePeriodSeconds': 5,
                         'automountServiceAccountToken': False,
                         'nodeSelector': {'hpc.local/role': 'compute'},
                         'securityContext': {'runAsUser': 1000, 'runAsGroup': 1000,
                                             'runAsNonRoot': True},
                         'tolerations': [dict(key='node.kubernetes.io/'+key, operator='Exists',
                                              effect='NoExecute', tolerationSeconds=int(cfg['EVICTION_SECONDS']))
                                         for key in ('not-ready', 'unreachable')],
                         'topologySpreadConstraints': [{
                             'maxSkew': 1, 'topologyKey': 'kubernetes.io/hostname',
                             'whenUnsatisfiable': 'ScheduleAnyway',
                             'labelSelector': {'matchLabels': {'app': 'hpc-compute'}}}],
                         'containers': [{'name': 'compute', 'image': 'hpc-compute:local',
                             'imagePullPolicy': 'Never',
                             'args': ['--limit', str(limit), '--seconds', str(seconds)],
                             'env': [{'name': 'JOB_NAME', 'value': name}] + [
                                 {'name': key, 'valueFrom': {'fieldRef': {'fieldPath': field}}}
                                 for key, field in [('POD_UID', 'metadata.uid'),
                                                    ('POD_NAME', 'metadata.name'), ('NODE_NAME', 'spec.nodeName')]],
                             'resources': {
                                 'requests': {'cpu': cfg['JOB_CPU_M']+'m', 'memory': cfg['JOB_MEMORY_MIB']+'Mi'},
                                 'limits': {'cpu': cfg['JOB_LIMIT_CPU_M']+'m', 'memory': cfg['JOB_LIMIT_MEMORY_MIB']+'Mi'}},
                             'securityContext': {'allowPrivilegeEscalation': False,
                                                 'capabilities': {'drop': ['ALL']}},
                             'volumeMounts': [{'name': 'shared', 'mountPath': '/shared'}]}],
                         'volumes': [{'name': 'shared', 'persistentVolumeClaim': {'claimName': 'shared'}}]}}}}


def main():
    parser = argparse.ArgumentParser(description='CLI pekerjaan HPC')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('submit')
    p.add_argument('--name')
    p.add_argument('--limit', type=int, default=50000)
    p.add_argument('--seconds', type=int, default=30)
    p.add_argument('--dry-run', action='store_true', help='Cetak JSON tanpa menghubungi cluster')
    sub.add_parser('config', help=argparse.SUPPRESS)
    sub.add_parser('status')
    sub.add_parser('queue')
    for cmd in ('logs', 'cancel', 'result', 'wait'):
        p = sub.add_parser(cmd)
        p.add_argument('name')
        if cmd == 'wait':
            p.add_argument('--timeout', type=int, default=900)
    args = parser.parse_args()
    cfg = settings()
    if args.command == 'config':
        print(json.dumps(cfg, indent=2))
    elif args.command == 'submit':
        name = args.name or ('prime-' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S') + '-' + uuid.uuid4().hex[:6])
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,48}[a-z0-9]|[a-z]', name):
            parser.error('Nama harus 1..50 karakter DNS huruf kecil, tanpa tanda hubung di akhir.')
        if not 2 <= args.limit <= 2000000 or not 1 <= args.seconds <= 1200:
            parser.error('limit harus 2..2000000; seconds harus 1..1200')
        job = manifest(name, args.limit, args.seconds, cfg)
        if args.dry_run:
            print(json.dumps(job, indent=2))
        else:
            kubectl('create', '-f', '-', body=job, capture=True)
            print(name)
    elif args.command == 'status':
        kubectl('get', 'jobs', '-l', 'app=hpc-compute', '-o', 'wide')
        kubectl('get', 'pods', '-l', 'app=hpc-compute', '-o', 'wide')
    elif args.command == 'queue':
        kubectl('get', 'workloads', '-o', 'wide')
    elif args.command == 'logs':
        kubectl('logs', '-l', 'hpc.local/job='+args.name, '--all-containers=true', '--prefix', '--tail=100')
    elif args.command == 'cancel':
        kubectl('delete', 'job', args.name)
    elif args.command == 'result':
        root = Path(os.environ.get('SHARED_DIR', '/srv/hpc')) / 'output' / args.name
        if not root.is_dir():
            parser.exit(1, 'Belum ada direktori hasil. Jalankan dari host/SSH head.\n')
        results = sorted(root.glob('*/result.json'))
        if not results:
            parser.exit(1, 'Belum ada percobaan yang menghasilkan result.json.\n')
        for path in results:
            print(path.read_text())
    elif args.command == 'wait':
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            job = json.loads(kubectl('get', 'job', args.name, '-o', 'json', capture=True))
            conditions = {c['type'] for c in job.get('status', {}).get('conditions', []) if c['status'] == 'True'}
            if 'Complete' in conditions:
                print(args.name + ' Complete')
                return
            if 'Failed' in conditions:
                parser.exit(1, args.name + ' Failed\n')
            time.sleep(2)
        parser.exit(1, args.name + ' melewati timeout; periksa status Pod dan log\n')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
