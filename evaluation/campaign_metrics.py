"""Hitung metrik satu run dan gabungkan seluruh kampanye.

Dipakai oleh scripts/run-campaign.sh. Hanya Job yang namanya diawali --prefix
yang dihitung, sehingga sisa Job dari run lain tidak ikut. Jika summary.json
mencatat lebih banyak Job daripada yang diharapkan, run ditandai
'contaminated' agar kebocoran data kumulatif terlihat jelas.

  run        : metrik satu folder run -> JSON satu baris (juga run-metrics.json)
  aggregate  : gabungkan semua */run-metrics.json -> campaign-summary.csv/.md
"""
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from statistics import median


def stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None


def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run_metrics(args):
    run = Path(args.run)
    prefix = args.prefix
    summary = json.loads((run / 'summary.json').read_text()) if (run / 'summary.json').exists() else {}
    jobs = [r for r in read_csv(run / 'jobs.csv') if r['job'].startswith(prefix)]
    attempts = [r for r in read_csv(run / 'attempts.csv') if r['job'].startswith(prefix)]
    recovery = [r for r in read_csv(run / 'recovery.csv') if r['job'].startswith(prefix)]

    problems = []
    observed_total = summary.get('jobs_observed', len(jobs))
    contaminated = observed_total != len(jobs)
    if contaminated:
        problems.append(f'contaminated: summary.json has {observed_total} jobs, run has {len(jobs)}')
    if len(jobs) != args.expected:
        problems.append(f'expected {args.expected} jobs, found {len(jobs)}')

    complete = sum(r['status'] == 'Complete' for r in jobs)
    verified = sum(r['verified'] == 'True' for r in jobs)
    if complete != args.expected:
        problems.append(f'only {complete}/{args.expected} jobs Complete')
    if verified != args.expected:
        problems.append(f'only {verified}/{args.expected} jobs verified')

    per_node = {}
    for a in attempts:
        per_node[a['node']] = per_node.get(a['node'], 0) + 1
    queue = [v for v in (num(r['queue_seconds']) for r in jobs) if v is not None]
    turnaround = [v for v in (num(r['turnaround_seconds']) for r in jobs) if v is not None]

    out = {'scenario': args.scenario, 'rep': args.rep, 'prefix': prefix,
           'jobs': len(jobs), 'complete': complete, 'verified': verified,
           'attempts': len(attempts), 'per_node': dict(sorted(per_node.items())),
           'queue_max_s': max(queue) if queue else None,
           'turnaround_median_s': round(median(turnaround), 1) if turnaround else None,
           'contaminated': contaminated}

    if args.scenario == 'normal':
        counts = sorted(per_node.values())
        out['even_split'] = len(per_node) == 3 and counts[0] == counts[-1]

    if args.scenario == 'fifo':
        ordered = sorted(jobs, key=lambda r: (r['created_at'], r['job']))
        admitted = [r['admitted_at'] for r in ordered]
        if not all(admitted):
            out['fifo_in_order'] = None
            problems.append('admission time missing for some job; order cannot be proven')
        else:
            times = [stamp(t) for t in admitted]
            out['fifo_in_order'] = all(a <= b for a, b in zip(times, times[1:]))
            out['fifo_ties'] = sum(a == b for a, b in zip(times, times[1:]))
            if not out['fifo_in_order']:
                problems.append('admission order differs from submit order')

    if args.scenario == 'recovery':
        out['failure_cases'] = len(recovery)
        if len(recovery) != 1:
            problems.append(f'expected exactly 1 failure case, found {len(recovery)}')
        if recovery:
            r = recovery[0]
            out['failed_node'] = r['failed_node']
            out['replacement_node'] = r['replacement_node']
            out['recovery_s'] = num(r['recovery_seconds'])
            if not r['replacement_node'] or r['replacement_node'] == r['failed_node']:
                problems.append('replacement did not run on a different node')
            if r['verified'] != 'True':
                problems.append('replacement attempt not verified')
        failure_log = run / 'failures.jsonl'
        if not failure_log.exists():
            problems.append('failures.jsonl missing')

    out['ok'] = not problems
    out['problems'] = problems
    (run / 'run-metrics.json').write_text(json.dumps(out, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(out))


def fmt_nodes(per_node):
    return ' / '.join(f"{k.replace('hpc-', '')}:{v}" for k, v in per_node.items()) or '-'


def aggregate(args):
    root = Path(args.out)
    runs = []
    for path in sorted(root.glob('*/run-metrics.json')):
        runs.append(json.loads(path.read_text()))
    order = {'normal': 0, 'fifo': 1, 'recovery': 2}
    runs.sort(key=lambda r: (order.get(r['scenario'], 9), r['rep']))

    fields = ['scenario', 'rep', 'jobs', 'complete', 'verified', 'attempts', 'distribution',
              'queue_max_s', 'turnaround_median_s', 'fifo_in_order', 'recovery_s',
              'replacement_node', 'ok', 'problems']
    rows = []
    for r in runs:
        rows.append({'scenario': r['scenario'], 'rep': r['rep'], 'jobs': r['jobs'],
                     'complete': r['complete'], 'verified': r['verified'],
                     'attempts': r['attempts'], 'distribution': fmt_nodes(r['per_node']),
                     'queue_max_s': r['queue_max_s'], 'turnaround_median_s': r['turnaround_median_s'],
                     'fifo_in_order': r.get('fifo_in_order', ''), 'recovery_s': r.get('recovery_s', ''),
                     'replacement_node': r.get('replacement_node', ''), 'ok': r['ok'],
                     'problems': '; '.join(r['problems'])})
    with (root / 'campaign-summary.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    total_jobs = sum(r['jobs'] for r in runs)
    total_ok = sum(r['verified'] for r in runs)
    rec = [r['recovery_s'] for r in runs if r['scenario'] == 'recovery' and r.get('recovery_s')]
    lines = ['# Campaign summary', '',
             f'Runs: {len(runs)} | Jobs submitted: {total_jobs} | Complete and verified: {total_ok}', '']
    lines += ['| Scenario | Rep | Jobs | Verified | Jobs per worker | Max queue (s) | Median turnaround (s) | Extra | OK |',
              '|---|---|---|---|---|---|---|---|---|']
    for r in runs:
        extra = ''
        if r['scenario'] == 'normal':
            extra = 'even split' if r.get('even_split') else 'uneven'
        elif r['scenario'] == 'fifo':
            extra = 'FIFO order kept' if r.get('fifo_in_order') else 'FIFO NOT proven'
        elif r['scenario'] == 'recovery':
            extra = f"recovery {r.get('recovery_s')} s -> {r.get('replacement_node')}"
        lines.append(f"| {r['scenario']} | {r['rep']} | {r['jobs']} | {r['verified']} | "
                     f"{fmt_nodes(r['per_node'])} | {r['queue_max_s']} | {r['turnaround_median_s']} | "
                     f"{extra} | {'yes' if r['ok'] else 'NO'} |")
    if rec:
        lines += ['', f'Recovery time: median {round(median(rec), 1)} s, min {min(rec)} s, max {max(rec)} s '
                      f'over {len(rec)} runs.']
    bad = [r for r in runs if not r['ok']]
    if bad:
        lines += ['', '## Problems', '']
        for r in bad:
            lines.append(f"- {r['scenario']}-{r['rep']:02d}: " + '; '.join(r['problems']))
    (root / 'campaign-summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))
    raise SystemExit(0 if not bad else 1)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--run', required=True)
    r.add_argument('--scenario', required=True, choices=['normal', 'fifo', 'recovery'])
    r.add_argument('--rep', type=int, required=True)
    r.add_argument('--prefix', required=True)
    r.add_argument('--expected', type=int, required=True)
    a = sub.add_parser('aggregate')
    a.add_argument('--out', required=True)
    args = p.parse_args()
    run_metrics(args) if args.cmd == 'run' else aggregate(args)