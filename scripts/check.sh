#!/usr/bin/env bash
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
[[ $(uname -s) == Linux ]] || fail 'Jalankan di Linux/WSL, bukan PowerShell atau Git Bash.'
for tool in docker kind kubectl python3 ssh curl; do
  command -v "$tool" >/dev/null || fail "Dependensi belum tersedia: $tool"
done
python3 -c 'import yaml' || fail 'Pasang python3-yaml (lihat panduan).'
docker info >/dev/null
[[ $(docker info --format '{{.OSType}}') == linux ]] || fail 'Docker harus menggunakan container Linux.'
[[ $(docker info --format '{{.CgroupVersion}}') == 2 ]] || fail 'Image node yang dipilih memerlukan cgroup v2.'
[[ $(docker info --format '{{json .SecurityOptions}}') != *rootless* ]] || fail 'Setup dirancang untuk Docker Engine rootful.'
[[ $(docker context inspect --format '{{.Endpoints.docker.Host}}') == unix://* ]] || fail 'Gunakan Docker Engine lokal melalui Unix socket.'
[[ -f "$SSH_PUBLIC_KEY" ]] || fail "Public key tidak ditemukan: $SSH_PUBLIC_KEY"
[[ "$CLUSTER_NAME" =~ ^[a-z][a-z0-9-]*$ ]] || fail 'CLUSTER_NAME harus nama DNS huruf kecil.'
[[ ${#CLUSTER_NAME} -le 32 && "$CLUSTER_NAME" != *- ]] || fail 'CLUSTER_NAME maksimal 32 karakter dan tidak boleh diakhiri tanda hubung.'
[[ "$SHARED_DIR" == /* ]] || fail 'SHARED_DIR harus path absolut Linux.'
for key in NODE_MEMORY_MIB HEAD_MEMORY_MIB WORKER_POD_CPU_M WORKER_POD_MEMORY_MIB QUEUE_CPU_M QUEUE_MEMORY_MIB JOB_CPU_M JOB_MEMORY_MIB JOB_LIMIT_CPU_M JOB_LIMIT_MEMORY_MIB EVICTION_SECONDS SSH_PORT; do
  [[ ${!key} =~ ^[1-9][0-9]*$ ]] || fail "$key harus integer positif."
done
python3 - <<'PY'
import os
e = os.environ
num = lambda x: float(e[x])
assert num('NODE_CPUS') > 0 and num('HEAD_CPUS') > 0
assert num('WORKER_POD_CPU_M') < num('NODE_CPUS') * 1000
assert num('WORKER_POD_MEMORY_MIB') < num('NODE_MEMORY_MIB')
for unit in ('CPU_M', 'MEMORY_MIB'):
    assert num('JOB_'+unit) <= num('JOB_LIMIT_'+unit)
    assert num('JOB_'+unit) <= num('WORKER_POD_'+unit)
    assert num('JOB_'+unit) <= num('QUEUE_'+unit) <= 3*num('WORKER_POD_'+unit)
assert num('SSH_PORT') < 65536
PY
echo 'Dependensi dan parameter dasar memenuhi pemeriksaan. Kapasitas aktual diuji saat setup.'
docker version --format 'Docker server: {{.Server.Version}}'
kind version
kubectl version --client
