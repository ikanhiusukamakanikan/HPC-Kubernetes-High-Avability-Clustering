"""Pekerjaan CPU deterministik; setiap Pod menulis satu percobaan independen."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time


def now():
    return datetime.now(timezone.utc).isoformat()


def count_primes(limit):
    return sum(all(n % d for d in range(2, math.isqrt(n) + 1)) for n in range(2, limit + 1))


def reference_count(limit):
    sieve = bytearray(b'\x01') * (limit + 1)
    sieve[:2] = b'\x00\x00'
    for p in range(2, math.isqrt(limit) + 1):
        if sieve[p]:
            sieve[p*p:limit+1:p] = b'\x00' * (((limit - p*p) // p) + 1)
    return sum(sieve)


def atomic_json(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=50000)
    parser.add_argument('--seconds', type=int, default=30)
    args = parser.parse_args()
    if not 2 <= args.limit <= 2000000 or not 1 <= args.seconds <= 1200:
        parser.error('limit harus 2..2000000 dan seconds 1..1200')
    job = os.environ['JOB_NAME']
    uid = os.environ['POD_UID']
    folder = Path(os.environ.get('OUTPUT_ROOT', '/shared/output')) / job / uid
    folder.mkdir(parents=True, exist_ok=True)
    record = dict(job=job, pod_uid=uid, pod=os.environ.get('POD_NAME'),
                  node=os.environ.get('NODE_NAME'), started_at=now(), status='Running',
                  limit=args.limit, minimum_seconds=args.seconds)
    atomic_json(folder / 'attempt.json', record)
    started = time.monotonic()
    cycles = 0
    with (folder / 'events.jsonl').open('a', buffering=1) as log:
        def event(kind, **fields):
            row = dict(time=now(), event=kind, **fields)
            log.write(json.dumps(row) + '\n')
            print(json.dumps(row), flush=True)
        event('started', **record)
        try:
            while True:
                result = count_primes(args.limit)
                cycles += 1
                event('progress', cycles=cycles, prime_count=result)
                if time.monotonic() - started >= args.seconds:
                    break
            expected = reference_count(args.limit)
            if result != expected:
                raise ValueError(f'Hasil {result} != referensi {expected}')
            record.update(status='Succeeded', finished_at=now(), cycles=cycles,
                          elapsed_seconds=time.monotonic()-started,
                          prime_count=result, expected_count=expected, verified=True)
            atomic_json(folder / 'result.json', record)
            atomic_json(folder / 'attempt.json', record)
            event('completed', **record)
        except Exception as exc:
            record.update(status='Failed', finished_at=now(), error=str(exc))
            atomic_json(folder / 'attempt.json', record)
            event('failed', error=str(exc))
            raise


if __name__ == '__main__':
    main()
