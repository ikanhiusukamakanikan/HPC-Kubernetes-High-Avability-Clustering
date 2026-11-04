#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export ROOT
set -a
source "$ROOT/config/cluster.env.example"
if [[ -f "$ROOT/config/cluster.env" ]]; then source "$ROOT/config/cluster.env"; fi
SHARED_DIR="${SHARED_DIR:-$ROOT/data/shared}"
HEAD_CPUS="${HEAD_CPUS:-$NODE_CPUS}"
HEAD_MEMORY_MIB="${HEAD_MEMORY_MIB:-$NODE_MEMORY_MIB}"
KUBECONFIG="$ROOT/.runtime/kubeconfig"
set +a
k() { kubectl --context "kind-$CLUSTER_NAME" "$@"; }
render() { python3 "$ROOT/scripts/render.py" "$1"; }
fail() { echo "ERROR: $*" >&2; exit 1; }
