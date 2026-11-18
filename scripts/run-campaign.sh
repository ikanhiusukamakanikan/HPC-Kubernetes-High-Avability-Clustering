#!/usr/bin/env bash
# Jalankan seluruh pengujian: normal, FIFO, dan failure/recovery, masing-masing REPS kali,
# TANPA data kumulatif. Pada awal setiap run semua Job/Pod/Workload lama dihapus dari
# cluster, dan setiap run memakai nama Job unik, sehingga collector hanya melihat Job run itu.
#
# Pemakaian (dari root repo, cluster sudah berjalan):
#   bash scripts/run-campaign.sh                   # 3 skenario x 3 ulangan (sekitar 30 menit)
#   bash scripts/run-campaign.sh --only recovery   # hanya satu skenario
#   bash scripts/run-campaign.sh --reps 1 --recovery-seconds 30 --yes   # uji cepat
#
# Hasil: results/campaign-<waktu>/{normal,fifo,recovery}-0N/ + campaign-summary.csv/.md
# Folder results/ lama tidak diubah.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

REPS=3
ONLY="normal,fifo,recovery"
OUT=""
ASSUME_YES=0
NORMAL_JOBS=9;  NORMAL_SECONDS=20
FIFO_JOBS=6;    FIFO_SECONDS=15
RECOVERY_SECONDS=120

usage() {
  cat <<'EOF'
Usage: bash scripts/run-campaign.sh [options]
  --reps N               repetitions per scenario (default 3)
  --only LIST            comma list of: normal,fifo,recovery (default all)
  --out DIR              output directory (default results/campaign-<UTC time>)
  --recovery-seconds N   length of the recovery job (default 120, as in the report)
  --yes, -y              do not ask before deleting old Jobs
  -h, --help             this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --reps) REPS="${2:?}"; shift 2 ;;
    --only) ONLY="${2:?}"; shift 2 ;;
    --out) OUT="${2:?}"; shift 2 ;;
    --recovery-seconds) RECOVERY_SECONDS="${2:?}"; shift 2 ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; fail "Unknown option: $1" ;;
  esac
done
[[ "$REPS" =~ ^[1-9][0-9]*$ ]] || fail '--reps must be a positive integer'
[[ "$RECOVERY_SECONDS" =~ ^[0-9]+$ ]] || fail '--recovery-seconds must be an integer'
IFS=, read -r -a SCENARIOS <<< "$ONLY"
for s in "${SCENARIOS[@]}"; do
  [[ "$s" == normal || "$s" == fifo || "$s" == recovery ]] || fail "Unknown scenario: $s"
done

TAG="$(date -u +%m%d%H%M)"
[[ -n "$OUT" ]] || OUT="$ROOT/results/campaign-$(date -u +%Y%m%dT%H%M%SZ)"
[[ "$OUT" = /* ]] || OUT="$PWD/$OUT"
[[ ! -e "$OUT" ]] || fail "Output directory already exists: $OUT"

hpc() { bash "$ROOT/scripts/hpc.sh" "$@"; }
log() { printf '\n[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

RUN=""; COLLECTOR_PID=""; STOPPED_NODE=""; QUOTA_CHANGED=0; ANY_BAD=0

stop_collector() {
  local grace="${1:-5}"
  [[ -n "$COLLECTOR_PID" ]] || return 0
  sleep "$grace"   # let the collector record the final state
  kill -TERM "$COLLECTOR_PID" 2>/dev/null || true
  wait "$COLLECTOR_PID" 2>/dev/null || true
  COLLECTOR_PID=""
  rm -f "$RUN/current.tmp"
}

queue_quota() { k get clusterqueue hpc-queue -o jsonpath='{.spec.resourceGroups[0].flavors[0].resources[*].nominalQuota}'; }

restore_quota() {
  render "$ROOT/deploy/queue.yaml.tmpl" > "$ROOT/.runtime/queue.yaml"
  k apply -f "$ROOT/.runtime/queue.yaml" >/dev/null
  QUOTA_CHANGED=0
}

set_fifo_quota() {
  k patch clusterqueue hpc-queue --type=json -p='[
   {"op":"replace","path":"/spec/resourceGroups/0/flavors/0/resources/0/nominalQuota","value":"500m"},
   {"op":"replace","path":"/spec/resourceGroups/0/flavors/0/resources/1/nominalQuota","value":"128Mi"}
  ]' >/dev/null
  QUOTA_CHANGED=1
  [[ "$(queue_quota)" == "500m 128Mi" ]] || fail "FIFO quota was not applied (got: $(queue_quota))"
}

cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  stop_collector 0 || true
  if [[ -n "$STOPPED_NODE" ]]; then
    echo "Restoring stopped worker $STOPPED_NODE ..." >&2
    bash "$ROOT/scripts/restore-worker.sh" "$STOPPED_NODE" || true
  fi
  if (( QUOTA_CHANGED )); then
    echo 'Restoring default queue quota ...' >&2
    restore_quota || true
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# --- The anti-cumulative step: nothing from earlier runs may remain in the cluster ----------
reset_state() {
  echo '  Clearing old Jobs, Pods and Workloads ...'
  k -n hpc delete jobs -l app=hpc-compute --ignore-not-found --wait=true --timeout=180s >/dev/null || true
  local n i
  for i in $(seq 1 60); do
    n=$(( $(k -n hpc get jobs -l app=hpc-compute -o name | wc -l) \
        + $(k -n hpc get pods -l app=hpc-compute -o name | wc -l) \
        + $(k -n hpc get workloads -o name | wc -l) ))
    (( n == 0 )) && return 0
    sleep 3
  done
  fail 'Old Jobs/Pods/Workloads are still present after 3 minutes; refusing to run on a dirty cluster.'
}

ensure_healthy() {
  k wait --for=condition=Ready nodes --all --timeout=180s >/dev/null
  [[ "$(k get nodes -l hpc.local/role=compute -o name | wc -l)" -eq 3 ]] || fail 'Expected 3 compute nodes.'
}

begin_run() {  # scenario rep
  RUN="$OUT/$1-$(printf '%02d' "$2")"
  log "RUN $1 #$2 -> $RUN"
  ensure_healthy
  reset_state
  mkdir -p "$RUN"
  bash "$ROOT/scripts/collect.sh" "$RUN" >/dev/null 2>"$RUN/collector.log" &
  COLLECTOR_PID=$!
  local i
  for i in $(seq 1 30); do [[ -s "$RUN/snapshots.jsonl" ]] && break; sleep 1; done
  [[ -s "$RUN/snapshots.jsonl" ]] || fail 'Collector produced no snapshot.'
}

archive_outputs() {  # copy this run's NFS evidence next to its CSVs (NFS itself is not touched)
  mkdir -p "$RUN/nfs-output"
  local name _
  while IFS=, read -r name _; do
    name="${name//$'\r'/}"
    if [[ -n "$name" && -d "$SHARED_DIR/output/$name" ]]; then
      cp -R "$SHARED_DIR/output/$name" "$RUN/nfs-output/" 2>/dev/null || true
    fi
  done < <(tail -n +2 "$RUN/jobs.csv")
}

end_run() {  # scenario rep prefix expected
  stop_collector 5
  python3 "$ROOT/evaluation/summarize.py" --run "$RUN" --shared "$SHARED_DIR" > "$RUN/summarize.stdout"
  archive_outputs
  local line
  line="$(python3 "$ROOT/evaluation/campaign_metrics.py" run --run "$RUN" --scenario "$1" \
          --rep "$2" --prefix "$3" --expected "$4")"
  python3 - "$line" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
status = 'OK ' if d['ok'] else 'CHECK'
bits = [f"jobs={d['jobs']}", f"verified={d['verified']}", f"attempts={d['attempts']}",
        f"nodes={d['per_node']}"]
if 'recovery_s' in d: bits.append(f"recovery={d.get('recovery_s')}s")
if 'fifo_in_order' in d: bits.append(f"fifo_in_order={d['fifo_in_order']}")
print(f"  [{status}] " + ' '.join(bits))
for p in d['problems']:
    print('    problem:', p)
PY
  [[ "$line" == *'"ok": true'* ]] || ANY_BAD=1
}

wait_all() {  # prefix count timeout
  local i
  for i in $(seq 1 "$2"); do
    hpc wait "$1$i" --timeout "${3:-900}" >/dev/null || echo "  WARNING: $1$i did not complete" >&2
  done
}

# --- Scenarios ------------------------------------------------------------------------------
run_normal() {
  local r="$1" prefix="normal${TAG}r$1-" i
  begin_run normal "$r"
  for i in $(seq 1 "$NORMAL_JOBS"); do
    hpc submit --name "$prefix$i" --seconds "$NORMAL_SECONDS" >/dev/null
    sleep 1
  done
  wait_all "$prefix" "$NORMAL_JOBS"
  end_run normal "$r" "$prefix" "$NORMAL_JOBS"
}

run_fifo() {
  local r="$1" prefix="fifo${TAG}r$1-" i
  reset_state
  set_fifo_quota
  begin_run fifo "$r"
  for i in $(seq 1 "$FIFO_JOBS"); do
    hpc submit --name "$prefix$i" --seconds "$FIFO_SECONDS" >/dev/null
    sleep 2
  done
  wait_all "$prefix" "$FIFO_JOBS"
  end_run fifo "$r" "$prefix" "$FIFO_JOBS"
  restore_quota
}

run_recovery() {
  local r="$1" job="recovery${TAG}r$1" node
  begin_run recovery "$r"
  hpc submit --name "$job" --seconds "$RECOVERY_SECONDS" >/dev/null
  k -n hpc wait --for=condition=Ready pod -l "hpc.local/job=$job" --timeout=180s >/dev/null
  node="$(k -n hpc get pod -l "hpc.local/job=$job" -o jsonpath='{.items[0].spec.nodeName}')"
  echo "  Job $job is running on $node; killing it in 5 s (hard stop, no drain)"
  sleep 5
  STOPPED_NODE="$node"
  bash "$ROOT/scripts/fail-worker.sh" "$node" "$RUN"
  echo '  Waiting for automatic recovery (about 145 s to restart, then the job runs again) ...'
  hpc wait "$job" --timeout 900 >/dev/null || echo "  WARNING: $job did not complete" >&2
  hpc result "$job" > "$RUN/result.txt" 2>&1 || true
  stop_collector 5
  # restart the old node only AFTER the job finished elsewhere
  bash "$ROOT/scripts/restore-worker.sh" "$node" >/dev/null
  STOPPED_NODE=""
  end_run recovery "$r" "$job" 1
}

# --- Main -----------------------------------------------------------------------------------
ensure_healthy
OLD_JOBS="$(k -n hpc get jobs -l app=hpc-compute -o name | wc -l)"
echo "Scenarios: ${SCENARIOS[*]} | repetitions: $REPS | tag: $TAG"
echo "Output:    $OUT"
echo "Old Jobs currently in the cluster that will be DELETED before the first run: $OLD_JOBS"
echo '(Old CSV/JSON files under results/ and files on NFS are not touched.)'
if (( ! ASSUME_YES )); then
  [[ -t 0 ]] || fail 'Not interactive; pass --yes to confirm.'
  read -r -p 'Continue? [y/N] ' ans
  [[ "$ans" == y || "$ans" == Y ]] || { echo 'Cancelled.'; exit 0; }
fi

mkdir -p "$OUT/environment"
{ docker version; kind version; k version -o yaml; } > "$OUT/environment/versions.txt" 2>&1 || true
k get nodes -o json > "$OUT/environment/nodes.json" 2>/dev/null || true
cp "$ROOT/config/cluster.env.example" "$OUT/environment/cluster.env.example" 2>/dev/null || true
restore_quota   # make sure we start from the configured quota

for scenario in "${SCENARIOS[@]}"; do
  for r in $(seq 1 "$REPS"); do
    "run_$scenario" "$r"
    sleep 5
  done
done

reset_state
log 'CAMPAIGN SUMMARY'
python3 "$ROOT/evaluation/campaign_metrics.py" aggregate --out "$OUT" || ANY_BAD=1
echo
echo "Done. Per-run CSVs: $OUT/<scenario>-0N/   Overview: $OUT/campaign-summary.md"
exit "$ANY_BAD"