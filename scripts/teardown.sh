#!/usr/bin/env bash
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
[[ ${1:-} == --yes ]] || fail 'Ini menghapus cluster beserta status Kubernetes. Gunakan --yes; data NFS dan results tetap disimpan.'
kind delete cluster --name "$CLUSTER_NAME" --kubeconfig "$KUBECONFIG"
echo 'Cluster dihapus; direktori data dan hasil analisis tetap tersimpan.'
