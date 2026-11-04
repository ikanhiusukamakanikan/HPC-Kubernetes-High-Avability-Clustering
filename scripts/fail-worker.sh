#!/usr/bin/env bash
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
[[ $# -eq 2 ]] || fail 'Pemakaian: bash scripts/fail-worker.sh NAMA-WORKER DIREKTORI-RUN'
NODE="$1"
RUN="$2"
[[ "$(k get node "$NODE" -o jsonpath='{.metadata.labels.hpc\.local/role}')" == compute ]] || fail 'Hanya compute node boleh dihentikan.'
[[ "$(docker inspect -f '{{index .Config.Labels "io.x-k8s.kind.cluster"}}' "$NODE")" == "$CLUSTER_NAME" ]] || fail 'Container bukan milik cluster ini.'
[[ "$(docker inspect -f '{{.State.Running}}' "$NODE")" == true ]] || fail 'Worker sudah berhenti.'
mkdir -p "$RUN"
python3 - "$NODE" >> "$RUN/failures.jsonl" <<'PY'
from datetime import datetime, timezone
import json, sys
print(json.dumps({'event': 'stop_requested', 'node': sys.argv[1], 'time': datetime.now(timezone.utc).isoformat()}))
PY
# Penghentian paksa untuk mensimulasikan node mati, bukan drain terencana.
docker stop --time 0 "$NODE"
python3 - "$NODE" >> "$RUN/failures.jsonl" <<'PY'
from datetime import datetime, timezone
import json, sys
print(json.dumps({'event': 'stopped', 'node': sys.argv[1], 'time': datetime.now(timezone.utc).isoformat()}))
PY
echo "Worker berhenti. Jangan start kembali sebelum pekerjaan pengganti berhasil."
