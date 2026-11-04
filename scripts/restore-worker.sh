#!/usr/bin/env bash
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
[[ $# -eq 1 ]] || fail 'Pemakaian: bash scripts/restore-worker.sh NAMA-WORKER'
[[ "$(k get node "$1" -o jsonpath='{.metadata.labels.hpc\.local/role}')" == compute ]] || fail 'Hanya compute node.'
[[ "$(docker inspect -f '{{index .Config.Labels "io.x-k8s.kind.cluster"}}' "$1")" == "$CLUSTER_NAME" ]] || fail 'Container bukan milik cluster ini.'
docker start "$1"
k wait --for=condition=Ready "node/$1" --timeout=180s
