"""Selaraskan Node Allocatable dengan batas container kind; dijalankan host Linux."""
import json
import os
from pathlib import Path
import subprocess
import sys
import yaml


def run(*args):
    return subprocess.check_output(args, text=True)


def memory_mib(quantity):
    if quantity.endswith('Ki'):
        return int(quantity[:-2]) // 1024
    if quantity.endswith('Mi'):
        return int(quantity[:-2])
    return int(quantity) // (1024 * 1024)


def main():
    context = 'kind-' + os.environ['CLUSTER_NAME']
    nodes = json.loads(run('kubectl', '--context', context, 'get', 'nodes', '-o', 'json'))['items']
    for node in nodes:
        name = node['metadata']['name']
        head = node['metadata']['labels'].get('hpc.local/role') == 'head'
        cpus = os.environ['HEAD_CPUS' if head else 'NODE_CPUS']
        memory = os.environ['HEAD_MEMORY_MIB' if head else 'NODE_MEMORY_MIB']
        subprocess.check_call(['docker', 'update', '--cpus', cpus, '--memory', memory+'m',
                               '--memory-swap', memory+'m', name])
        if head:
            continue
        capacity = node['status']['capacity']
        reserve_cpu = round(float(capacity['cpu']) * 1000) - int(os.environ['WORKER_POD_CPU_M'])
        reserve_memory = memory_mib(capacity['memory']) - int(os.environ['WORKER_POD_MEMORY_MIB'])
        if reserve_cpu < 0 or reserve_memory < 0:
            sys.exit('Kapasitas node lebih kecil dari anggaran Pod; periksa konfigurasi.')
        cfg = yaml.safe_load(run('docker', 'exec', name, 'cat', '/var/lib/kubelet/config.yaml'))
        cfg['kubeReserved'] = {'cpu': f'{reserve_cpu}m', 'memory': f'{reserve_memory}Mi'}
        cfg.pop('systemReserved', None)
        cfg['evictionHard'] = {'memory.available': '0Mi', 'nodefs.available': '5%',
                               'imagefs.available': '5%', 'nodefs.inodesFree': '5%'}
        cfg['enforceNodeAllocatable'] = ['pods']
        path = Path(os.environ['ROOT']) / '.runtime' / (name + '-kubelet.yaml')
        path.write_text(yaml.safe_dump(cfg))
        subprocess.check_call(['docker', 'cp', str(path), name+':/var/lib/kubelet/config.yaml'])
        subprocess.check_call(['docker', 'exec', name, 'systemctl', 'restart', 'kubelet'])


if __name__ == '__main__':
    main()
