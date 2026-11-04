#!/usr/bin/env bash
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
RUN="${1:-$ROOT/results/$(date -u +%Y%m%dT%H%M%SZ)}"
[[ ! -e "$RUN/snapshots.jsonl" ]] || fail 'Gunakan direktori pengumpulan baru.'
mkdir -p "$RUN"
echo "Mengumpulkan tiap 2 detik ke $RUN; Ctrl+C untuk berhenti." >&2
trap 'exit 0' INT TERM
while true; do
  k -n hpc get jobs,pods,workloads -o json > "$RUN/current.tmp"
  python3 - "$RUN/current.tmp" >> "$RUN/snapshots.jsonl" <<'PY'
import json, sys
from datetime import datetime, timezone
with open(sys.argv[1]) as f:
    data = json.load(f)
print(json.dumps({'observed_at': datetime.now(timezone.utc).isoformat(), 'items': data['items']}))
PY
  k -n hpc get events -o json > "$RUN/events.json"
  k get nodes -o json > "$RUN/nodes.json"
  sleep 2
done
