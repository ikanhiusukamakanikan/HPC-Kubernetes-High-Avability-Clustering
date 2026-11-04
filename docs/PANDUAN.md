# Panduan menjalankan cluster

Semua perintah di bawah dijalankan dari root repository pada terminal Linux Ubuntu/Debian atau WSL 2, menggunakan Docker Engine lokal dengan container Linux dan cgroup v2. Setup membutuhkan internet untuk image, paket Debian, dan manifest Kueue. Tidak ada cloud atau layanan berbayar yang diperlukan.

## Lingkungan dan dependensi

Gunakan direktori pada filesystem Linux, misalnya `~/projects/hpc`, terutama untuk `SHARED_DIR`. Jangan gunakan `/mnt/c`, `/mnt/d`, SMB, atau direktori Windows untuk ekspor NFS VFS: kemampuan file handle dan permission berbeda. Pada WSL, salin atau clone repository ke direktori home Linux sebelum menjalankan setup. Docker daemon harus berjalan pada mesin Linux/WSL yang sama, bukan Docker context jarak jauh.

Pasang Docker Engine mengikuti [panduan resmi Ubuntu](https://docs.docker.com/engine/install/ubuntu/) atau [Debian](https://docs.docker.com/engine/install/debian/). Pastikan akun dapat menjalankan `docker info` tanpa sudo, mengikuti [langkah pascainstalasi Docker](https://docs.docker.com/engine/install/linux-postinstall/). Keanggotaan grup docker memberikan kontrol setara root terhadap host lab.

Pasang perangkat lainnya:

```bash
sudo apt-get update
sudo apt-get install -y curl ca-certificates python3 python3-yaml openssh-client

case "$(uname -m)" in
  x86_64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) echo 'Arsitektur belum didukung'; exit 1 ;;
esac
curl -fLo /tmp/hpc-kind "https://kind.sigs.k8s.io/dl/v0.31.0/kind-linux-$ARCH"
sudo install -m 0755 /tmp/hpc-kind /usr/local/bin/kind
curl -fLo /tmp/hpc-kubectl "https://dl.k8s.io/release/v1.35.0/bin/linux/$ARCH/kubectl"
curl -fLo /tmp/hpc-kubectl.sha256 "https://dl.k8s.io/release/v1.35.0/bin/linux/$ARCH/kubectl.sha256"
printf '%s  /tmp/hpc-kubectl\n' "$(cat /tmp/hpc-kubectl.sha256)" | sha256sum --check
sudo install -m 0755 /tmp/hpc-kubectl /usr/local/bin/kubectl

docker info --format 'Cgroup: {{.CgroupVersion}}; Driver: {{.Driver}}'
```

Output cgroup harus `2`; backend yang dirancang adalah Docker Engine rootful. Rootless Docker, Docker remote, dan Windows containers belum didukung. Pastikan kernel Linux memiliki dukungan client NFS v4; pada WSL gunakan kernel WSL terbaru. Mount NFS dilakukan kubelet di container node yang privileged.

Versi dasar: kind v0.31.0, Kubernetes v1.35.0 dengan digest image tetap, Kueue v0.20.4 dan API `v1beta2`. Versi image Debian/Python menggunakan tag distribusi; build berikutnya dapat mengambil pembaruan paket. Untuk reproduksi eksperimen, catat ID image yang dipakai dan jangan rebuild di tengah rangkaian pengujian.

Sediakan setidaknya anggaran empat node sebesar 4 GiB RAM ditambah RAM OS, daemon Docker, cache image, dan proses build. Total kebutuhan host lebih besar dari batas container. Saat bootstrap, kind membuat node tanpa batas; batas CPU/RAM diterapkan sesudah instalasi paket dan sebelum Kueue/NFS dijalankan. Ini memungkinkan bootstrap, tetapi membutuhkan ruang RAM sementara yang cukup.

## Konfigurasi awal

```bash
cp config/cluster.env.example config/cluster.env
# Jika belum mempunyai key, buat key khusus lab dengan nama ini:
ssh-keygen -t ed25519 -f "$HOME/.ssh/hpc_lab" -C hpc-lab
```

Edit `config/cluster.env`, minimal:

```bash
SSH_PUBLIC_KEY="$HOME/.ssh/hpc_lab.pub"
```

Private key tetap di host; hanya public key disalin ke head. Jika memakai nama key khusus, sertakan `-i ~/.ssh/hpc_lab` pada perintah SSH. File konfigurasi menggunakan sintaks Bash dan dibaca sebagai kode, sehingga hanya gunakan konfigurasi yang dipercaya.

```bash
bash scripts/check.sh
bash scripts/setup.sh
```

Setup membangun image komputasi dan NFS, membuat empat node, memasang NFS client ke seluruh node, menyiapkan SSH di head, menetapkan batas Docker dan allocatable worker, lalu memasang Kueue dan NFS. NFS berupa Pod yang dipasang khusus pada head dan menggunakan direktori host yang di-bind melalui head. SSH berupa service langsung pada container head.

Setup menolak menimpa cluster bernama sama. Jika setup gagal, baca troubleshooting; setelah memperbaiki penyebabnya, gunakan teardown untuk membuang cluster parsial dan jalankan setup kembali. Direktori hasil NFS tetap disimpan.

## Pemeriksaan setelah setup

Gunakan kubeconfig khusus proyek agar tidak mengubah konfigurasi cluster lain:

```bash
export KUBECONFIG="$PWD/.runtime/kubeconfig"
kubectl get nodes -o wide
kubectl get nodes -o custom-columns=NAME:.metadata.name,CPU:.status.allocatable.cpu,MEMORY:.status.allocatable.memory
kubectl -n kueue-system get pods
kubectl -n hpc-system get pods
kubectl -n hpc get pvc
docker stats --no-stream
bash tests/smoke.sh
```

Harapkan empat node `Ready`, controller Kueue dan NFS siap, serta PVC `Bound`. Worker harus melaporkan sekitar 800m CPU dan 700 MiB RAM allocatable. Smoke test memastikan pekerjaan prima menghasilkan 168 untuk rentang 1..1000 dan berkas hasil tersedia pada penyimpanan bersama. Jangan anggap PVC `Bound` sebagai bukti NFS berfungsi; mount dibuktikan oleh pekerjaan.

## Penggunaan dari host

```bash
JOB=$(bash scripts/hpc.sh submit --seconds 30 --limit 50000)
echo "$JOB"
bash scripts/hpc.sh status
bash scripts/hpc.sh queue
bash scripts/hpc.sh logs "$JOB"
bash scripts/hpc.sh wait "$JOB" --timeout 900
bash scripts/hpc.sh result "$JOB"
```

`--seconds` adalah durasi minimum komputasi, bukan sleep atau waktu eksekusi pasti. Program mengulang perhitungan prima sampai durasi minimum tercapai, lalu memverifikasi hasil dengan sieve. Pekerjaan tidak menggunakan MPI. Submit mencetak nama unik agar dapat dipakai oleh perintah selanjutnya. Nama juga dapat ditentukan melalui `--name`, maksimum 50 karakter DNS huruf kecil.

Perintah lain:

```bash
# Melihat manifest tanpa membuat Job:
bash scripts/hpc.sh submit --seconds 30 --dry-run
# Membatalkan Job; log/hasil yang sudah tersimpan tetap ada:
bash scripts/hpc.sh cancel "$JOB"
```

Log Kubernetes pada node mati dapat tidak tersedia; catatan progres yang sudah ditulis melalui NFS tetap menjadi bukti. `logs` menampilkan 100 baris terakhir per Pod; gunakan berkas `events.jsonl` untuk riwayat penuh.

## Login SSH ke head node

```bash
ssh -i ~/.ssh/hpc_lab -p 2222 hpc@127.0.0.1
# Di dalam head:
hpc status
JOB=$(hpc submit --seconds 30)
hpc wait "$JOB"
hpc result "$JOB"
ls /srv/hpc/output
exit
```

Satu akun `hpc` memiliki UID/GID 1000. Akses memakai key, password dan login root SSH dimatikan. Port hanya di-bind ke loopback host. Akun mendapat salinan kubeconfig administrator untuk administrasi lab satu pengguna. Akun ini dapat mengubah cluster; rancangan ini tidak menyediakan isolasi multiuser atau RBAC terbatas.

Jika menjalankan SSH dari Windows ke Engine di WSL, port localhost biasanya diteruskan oleh WSL; bila tidak, jalankan SSH dari terminal WSL yang sama. Pada rebuild cluster, host key berubah. Setelah memastikan cluster memang dibuat ulang, hapus entri lama dengan `ssh-keygen -R '[127.0.0.1]:2222'`.

## Lokasi hasil

Default direktori host:

```text
data/shared/
  input/                         berkas input tambahan pengguna
  output/<job>/<pod-uid>/
    attempt.json                 status percobaan terakhir yang sempat ditulis
    events.jsonl                 progres bertimestamp UTC
    result.json                  hasil terverifikasi dari percobaan sukses
  logs/                          tempat tambahan untuk arsip pengguna
results/<run>/                   snapshot cluster dan laporan CSV
```

Pekerjaan prima menggunakan parameter CLI; tidak membutuhkan berkas input. Direktori input tersedia untuk pengembangan workload berikutnya. `attempt.json` yang masih `Running` setelah worker mati berarti proses tidak sempat menulis status akhir; bandingkan dengan snapshot Kubernetes. Jangan menafsirkan nilai itu sebagai proses masih hidup.

`5Gi` pada PV/PVC adalah ukuran deklaratif, bukan kuota filesystem NFS. Pemakaian disk nyata mengikuti kapasitas direktori host. Berkas tidak dihapus otomatis agar bukti eksperimen tetap tersedia.

## Mengubah CPU dan RAM

Tiga lapisan konfigurasi memiliki fungsi berbeda:

| Parameter | Fungsi |
|---|---|
| `NODE_CPUS`, `NODE_MEMORY_MIB` | Batas nyata Docker untuk tiap node, default 1 CPU dan 1024 MiB |
| `HEAD_CPUS`, `HEAD_MEMORY_MIB` | Override opsional head; kosong mengikuti nilai umum |
| `WORKER_POD_CPU_M`, `WORKER_POD_MEMORY_MIB` | Anggaran scheduler untuk seluruh Pod per worker, termasuk Pod sistem |
| `QUEUE_CPU_M`, `QUEUE_MEMORY_MIB` | Total requests pekerjaan yang boleh diterima Kueue |
| `JOB_CPU_M`, `JOB_MEMORY_MIB` | Requests satu pekerjaan untuk penjadwalan dan perhitungan kuota |
| `JOB_LIMIT_CPU_M`, `JOB_LIMIT_MEMORY_MIB` | Batas satu container pekerjaan |

Contoh meningkatkan seluruh node menjadi 2 CPU/2 GiB dengan enam pekerjaan serentak:

```bash
NODE_CPUS=2
NODE_MEMORY_MIB=2048
WORKER_POD_CPU_M=1700
WORKER_POD_MEMORY_MIB=1600
QUEUE_CPU_M=3000
QUEUE_MEMORY_MIB=768
# Requests pekerjaan tetap 500m dan 128 MiB.
```

Sisakan kapasitas untuk OS node, kubelet, containerd, dan komponen jaringan. Requests pekerjaan harus muat pada worker, dan kuota antrean harus masuk akal terhadap kapasitas tiga worker. Kuota tetap tidak otomatis mengecil ketika satu worker mati: sebagian pekerjaan bisa menunggu scheduler walaupun sudah admitted.

Untuk menaikkan hanya head saat OOM:

```bash
HEAD_CPUS=2
HEAD_MEMORY_MIB=2048
```

Cara paling konsisten menerapkan perubahan adalah rebuild setelah mencadangkan hasil dan memastikan tidak ada pekerjaan yang perlu dipertahankan:

```bash
bash scripts/teardown.sh --yes
bash scripts/setup.sh
```

Teardown menghapus status Job di etcd, konfigurasi antrean, dan node. Data NFS serta `results/` tetap ada. Pengaturan CPU/RAM tidak mengubah file lama. Gunakan nama Job unik pada eksperimen berikutnya.

Untuk menaikkan hanya batas head tanpa rebuild, setelah mengedit konfigurasi:

```bash
source scripts/common.sh
docker update --cpus "$HEAD_CPUS" --memory "${HEAD_MEMORY_MIB}m" \
  --memory-swap "${HEAD_MEMORY_MIB}m" "${CLUSTER_NAME}-control-plane"
```

Perubahan worker sebaiknya memakai rebuild agar allocatable, kuota, dan konfigurasi CLI di head tetap konsisten. Perubahan `SSH_PORT`, `SHARED_DIR`, image node, atau nama cluster juga memerlukan rebuild.

## Menghapus cluster

```bash
bash scripts/teardown.sh --yes
```

Tidak ada perintah penghapusan rekursif data di skrip proyek. Simpan hasil eksperimen sebelum membersihkannya secara manual.
