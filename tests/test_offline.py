"""Pemeriksaan bermakna tanpa Docker: manifest, perhitungan, dan analisis pemulihan."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from string import Template
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


worker = load('worker', 'images/compute/worker.py')
cli = load('cli', 'scripts/hpc.py')
analysis = load('analysis', 'evaluation/summarize.py')


class OfflineTests(unittest.TestCase):
    def test_known_prime_results(self):
        for limit, expected in [(2, 1), (10, 4), (1000, 168)]:
            self.assertEqual(worker.count_primes(limit), expected)
            self.assertEqual(worker.reference_count(limit), expected)

    def test_job_worker_only_and_recovery(self):
        job = cli.manifest('test', 1000, 2, cli.settings())
        spec = job['spec']['template']['spec']
        self.assertEqual(spec['nodeSelector'], {'hpc.local/role': 'compute'})
        self.assertTrue(job['spec']['suspend'])
        self.assertEqual(job['spec']['podReplacementPolicy'], 'Failed')
        self.assertEqual(job['spec']['template']['metadata']['annotations'][
            'kueue.x-k8s.io/safe-to-forcefully-delete'], 'true')
        self.assertEqual(spec['volumes'][0]['persistentVolumeClaim']['claimName'], 'shared')

    def test_render_templates(self):
        env = dict(SSH_PORT='2222', SHARED_DIR_JSON='"/home/test/path with spaces"',
                   CLUSTER_NAME='hpc', HEAD_IP='172.18.0.2', QUEUE_CPU_M='1500', QUEUE_MEMORY_MIB='384')
        docs = {}
        for path in (ROOT / 'deploy').glob('*.tmpl'):
            docs[path.name] = list(yaml.safe_load_all(Template(path.read_text()).substitute(env)))
        self.assertEqual(len(docs['kind.yaml.tmpl'][0]['nodes']), 4)
        queue = next(d for d in docs['queue.yaml.tmpl'] if d['kind'] == 'ClusterQueue')
        self.assertEqual(queue['spec']['queueingStrategy'], 'StrictFIFO')

    def test_real_worker_writes_verified_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, JOB_NAME='test', POD_UID='uid', OUTPUT_ROOT=tmp, NODE_NAME='worker')
            subprocess.run([sys.executable, str(ROOT / 'images/compute/worker.py'),
                            '--limit', '1000', '--seconds', '1'], env=env,
                           stdout=subprocess.DEVNULL, check=True)
            result = json.loads((Path(tmp) / 'test/uid/result.json').read_text())
            self.assertTrue(result['verified'])
            self.assertGreaterEqual(result['elapsed_seconds'], 1)

    def test_recovery_analysis_and_missing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run, shared = root / 'run', root / 'shared'
            run.mkdir()
            job = {'kind': 'Job', 'metadata': {'name': 'job', 'creationTimestamp': '2026-01-01T00:00:00Z',
                   'labels': {'app': 'hpc-compute'}}, 'status': {}}
            (run / 'snapshots.jsonl').write_text(json.dumps({'items': [job]})+'\n')
            (run / 'failures.jsonl').write_text(json.dumps({'event': 'stop_requested', 'node': 'w1',
                                                          'time': '2026-01-01T00:00:10Z'})+'\n')
            for uid, node, start in [('a', 'w1', '00:00:01'), ('b', 'w2', '00:01:10')]:
                folder = shared / 'output/job' / uid
                folder.mkdir(parents=True)
                (folder / 'attempt.json').write_text(json.dumps(dict(job='job', pod_uid=uid, node=node,
                    started_at='2026-01-01T'+start+'Z', status='Running')))
            summary = analysis.summarize(run, shared)
            self.assertEqual(summary['jobs_complete'], 0)
            self.assertEqual(summary['failure_cases'], 1)
            import csv
            with (run / 'recovery.csv').open() as f:
                row = next(csv.DictReader(f))
            self.assertEqual(row['recovery_seconds'], '60.0')
            self.assertEqual(row['verified'], 'False')


if __name__ == '__main__':
    unittest.main()
