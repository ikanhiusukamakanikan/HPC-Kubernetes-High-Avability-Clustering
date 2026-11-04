#!/usr/bin/env bash
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
bash "$ROOT/scripts/check.sh"
if kind get clusters | grep -Fxq "$CLUSTER_NAME"; then
  fail "Cluster $CLUSTER_NAME sudah ada. Setup tidak menimpa cluster; lihat panduan pemulihan setup."
fi
mkdir -p "$ROOT/.runtime" "$SHARED_DIR" "$ROOT/results"
chmod 700 "$ROOT/.runtime"
SHARED_DIR="$(cd -- "$SHARED_DIR" && pwd)"
export SHARED_DIR
render "$ROOT/deploy/kind.yaml.tmpl" > "$ROOT/.runtime/kind.yaml"
docker build -t hpc-compute:local "$ROOT/images/compute"
docker build -t hpc-nfs:local "$ROOT/images/nfs"
kind create cluster --name "$CLUSTER_NAME" --image "$KIND_IMAGE" \
  --config "$ROOT/.runtime/kind.yaml" --kubeconfig "$KUBECONFIG" --wait 300s
chmod 600 "$KUBECONFIG"
kind load docker-image --name "$CLUSTER_NAME" hpc-compute:local hpc-nfs:local
HEAD="${CLUSTER_NAME}-control-plane"
# NFS client berada di node karena kubelet melakukan mount, bukan di image pekerjaan.
while IFS= read -r node; do
  docker exec "$node" bash -ceu 'export DEBIAN_FRONTEND=noninteractive; apt-get update; apt-get install -y --no-install-recommends nfs-common; rm -rf /var/lib/apt/lists/*'
done < <(kind get nodes --name "$CLUSTER_NAME")
bash "$ROOT/scripts/setup-ssh.sh"
python3 "$ROOT/scripts/resources.py"
k wait --for=condition=Ready nodes --all --timeout=300s
# unduh satu rilis; simpan artefak yang benar-benar diterapkan untuk audit.
curl --fail --location --retry 3 \
  "https://github.com/kubernetes-sigs/kueue/releases/download/$KUEUE_VERSION/manifests.yaml" \
  -o "$ROOT/.runtime/kueue.yaml"
# Sesuaikan controller untuk lab kecil sebelum Deployment pertama kali dibuat.
python3 - <<'PY'
from pathlib import Path
import os, yaml
p = Path(os.environ['ROOT']) / '.runtime/kueue.yaml'
docs = list(yaml.safe_load_all(p.read_text()))
for d in docs:
    if d and d.get('kind') == 'Deployment' and d['metadata']['name'] == 'kueue-controller-manager':
        spec = d['spec']['template']['spec']
        spec['nodeSelector'] = {'hpc.local/role': 'head'}
        spec.setdefault('tolerations', []).append({
            'key': 'node-role.kubernetes.io/control-plane', 'operator': 'Exists', 'effect': 'NoSchedule'})
        for container in spec['containers']:
            if container['name'] == 'manager':
                args = container.setdefault('args', [])
                flags = [a for a in args if a.startswith('--feature-gates=')]
                if flags:
                    args.remove(flags[0])
                gates = flags[0].split('=', 1)[1] + ',' if flags else ''
                args.append('--feature-gates=' + gates + 'FailureRecoveryPolicy=true')
                container['resources'] = {'requests': {'cpu': '50m', 'memory': '96Mi'},
                                         'limits': {'cpu': '300m', 'memory': '256Mi'}}
p.write_text(yaml.safe_dump_all(docs, sort_keys=False))
PY
k apply --server-side -f "$ROOT/.runtime/kueue.yaml"
k -n kueue-system rollout status deployment/kueue-controller-manager --timeout=300s
render "$ROOT/deploy/queue.yaml.tmpl" > "$ROOT/.runtime/queue.yaml"
# Readiness manager bisa mendahului propagasi endpoint/certificate webhook.
for attempt in {1..10}; do
  if k apply -f "$ROOT/.runtime/queue.yaml"; then break; fi
  [[ "$attempt" -lt 10 ]] || fail 'Konfigurasi antrean gagal; periksa webhook Kueue.'
  sleep 3
done
export HEAD_IP
HEAD_IP="$(k get node "$HEAD" -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')"
render "$ROOT/deploy/storage.yaml.tmpl" > "$ROOT/.runtime/storage.yaml"
k apply -f "$ROOT/.runtime/storage.yaml"
k -n hpc-system rollout status deployment/nfs --timeout=180s
k -n hpc wait --for=jsonpath='{.status.phase}'=Bound pvc/shared --timeout=60s
k get nodes -o wide
echo "Setup selesai. Uji integrasi: bash tests/smoke.sh"
echo "SSH: ssh -p $SSH_PORT hpc@127.0.0.1"
