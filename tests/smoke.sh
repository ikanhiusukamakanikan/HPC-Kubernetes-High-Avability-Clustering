#!/usr/bin/env bash
source "$(dirname -- "${BASH_SOURCE[0]}")/../scripts/common.sh"
test "$(k get nodes -l hpc.local/role=compute -o name | wc -l)" -eq 3
k wait --for=condition=Ready nodes --all --timeout=180s
NAME="$(bash "$ROOT/scripts/hpc.sh" submit --seconds 2 --limit 1000)"
bash "$ROOT/scripts/hpc.sh" wait "$NAME" --timeout 300
bash "$ROOT/scripts/hpc.sh" result "$NAME"
python3 - "$SHARED_DIR" "$NAME" <<'PY'
import json, sys
from pathlib import Path
results = list((Path(sys.argv[1]) / 'output' / sys.argv[2]).glob('*/result.json'))
assert results, 'Tidak ada hasil pada NFS'
assert all(json.loads(p.read_text())['prime_count'] == 168 for p in results)
PY
echo 'Smoke test lulus: hasil prima 1..1000 = 168 tersimpan melalui NFS.'
