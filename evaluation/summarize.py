"""CSV dari bukti observasi cluster dan log NFS; field tanpa bukti dibiarkan kosong."""
import argparse
from collections import Counter
import csv
from datetime import datetime
import json
from pathlib import Path


def stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None


def delta(end, start):
    return round((stamp(end) - stamp(start)).total_seconds(), 3) if end and start else ''


def lines(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def write_csv(path, fields, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def summarize(run, shared):
    jobs, pods, admissions = {}, {}, {}
    for snapshot in lines(run / 'snapshots.jsonl'):
        for obj in snapshot['items']:
            meta = obj['metadata']
            if obj['kind'] == 'Job' and meta.get('labels', {}).get('app') == 'hpc-compute':
                jobs[meta['name']] = obj
            elif obj['kind'] == 'Pod':
                pods[meta['uid']] = obj
            elif obj['kind'] == 'Workload':
                owner = next((r['name'] for r in meta.get('ownerReferences', []) if r['kind'] == 'Job'), None)
                for c in obj.get('status', {}).get('conditions', []):
                    if owner and c['type'] == 'Admitted' and c['status'] == 'True':
                        date = c['lastTransitionTime']
                        if owner not in admissions or stamp(date) < stamp(admissions[owner]):
                            admissions[owner] = date
    attempts = []
    for path in (shared / 'output').glob('*/*/attempt.json'):
        row = json.loads(path.read_text(encoding='utf-8'))
        if row['job'] not in jobs:
            continue
        pod = pods.get(row['pod_uid'], {})
        row['observed_pod_phase'] = pod.get('status', {}).get('phase', '')
        attempts.append(row)
    rows = []
    for name, job in jobs.items():
        tries = sorted((a for a in attempts if a['job'] == name), key=lambda a: a['started_at'])
        conditions = {c['type'] for c in job.get('status', {}).get('conditions', []) if c['status'] == 'True'}
        status = 'Complete' if 'Complete' in conditions else ('Failed' if 'Failed' in conditions else 'Unfinished')
        created = job['metadata']['creationTimestamp']
        first = tries[0]['started_at'] if tries else ''
        completed = job.get('status', {}).get('completionTime', '')
        rows.append(dict(job=name, created_at=created, admitted_at=admissions.get(name, ''),
                         first_started_at=first, completed_at=completed, status=status,
                         attempts=len(tries), verified=any(a.get('verified') is True for a in tries),
                         queue_seconds=delta(admissions.get(name), created),
                         turnaround_seconds=delta(completed, created)))
    rows.sort(key=lambda r: (r['created_at'], r['job']))
    write_csv(run / 'jobs.csv', ['job', 'created_at', 'admitted_at', 'first_started_at',
              'completed_at', 'status', 'attempts', 'verified', 'queue_seconds', 'turnaround_seconds'], rows)
    write_csv(run / 'attempts.csv', ['job', 'pod_uid', 'pod', 'node', 'started_at', 'finished_at',
              'status', 'observed_pod_phase', 'elapsed_seconds', 'cycles', 'prime_count', 'verified'], attempts)
    recovery = []
    for failure in lines(run / 'failures.jsonl'):
        if failure['event'] != 'stop_requested':
            continue
        t0 = failure['time']
        affected = {a['job'] for a in attempts if a.get('node') == failure['node']
                    and stamp(a['started_at']) <= stamp(t0)
                    and (not a.get('finished_at') or stamp(a['finished_at']) > stamp(t0))}
        for name in sorted(affected):
            candidates = sorted((a for a in attempts if a['job'] == name
                                 and a.get('node') != failure['node'] and stamp(a['started_at']) >= stamp(t0)),
                                key=lambda a: a['started_at'])
            replacement = candidates[0] if candidates else {}
            recovery.append(dict(job=name, failed_node=failure['node'], failure_at=t0,
                                 replacement_node=replacement.get('node', ''),
                                 replacement_started_at=replacement.get('started_at', ''),
                                 recovery_seconds=delta(replacement.get('started_at'), t0),
                                 verified=replacement.get('verified', False)))
    write_csv(run / 'recovery.csv', ['job', 'failed_node', 'failure_at', 'replacement_node',
              'replacement_started_at', 'recovery_seconds', 'verified'], recovery)
    distribution = Counter(a.get('node') for a in attempts)
    write_csv(run / 'distribution.csv', ['node', 'attempts'],
              [dict(node=n, attempts=c) for n, c in sorted(distribution.items(), key=lambda x: str(x[0]))])
    summary = {'jobs_observed': len(rows), 'jobs_complete': sum(r['status'] == 'Complete' for r in rows),
               'jobs_verified': sum(r['verified'] for r in rows), 'attempts': len(attempts),
               'failure_cases': len(recovery), 'replacements_verified': sum(r['verified'] for r in recovery)}
    (run / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--shared', type=Path, required=True)
    args = p.parse_args()
    if not (args.run / 'snapshots.jsonl').is_file():
        p.error('snapshots.jsonl tidak ditemukan; jalankan collector terlebih dahulu')
    print(json.dumps(summarize(args.run, args.shared), indent=2))
