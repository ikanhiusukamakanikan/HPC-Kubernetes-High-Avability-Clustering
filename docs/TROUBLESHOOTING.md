# Troubleshooting

Jalankan perintah kubectl dari host dengan `export KUBECONFIG="$PWD/.runtime/kubeconfig"`. Simpan log sebelum menghapus atau membuat ulang cluster.

## Setup terputus

Setup tidak mendukung melanjutkan otomatis dan menolak cluster bernama sama. Periksa titik kegagalan, catat log, perbaiki konfigurasi, lalu jalankan `bash scripts/teardown.sh --yes` dan `bash scripts/setup.sh`. Teardown mempertahankan data/shared dan results. Jika ada Job yang perlu disimpan, ekspor bukti sebelum teardown.

## Head kehabisan memori

Periksa `docker stats --no-stream`, `docker inspect hpc-control-plane`, dan `docker logs hpc-control-plane`. Nama `hpc` mengikuti CLUSTER_NAME. Di node, `journalctl -u kubelet --no-pager -n 100` membantu memeriksa komponen yang gagal. Status OOMKilled dapat terlihat pada Pod, sedangkan OOM di dalam container node dapat mematikan proses tanpa menghentikan seluruh container.

Head 1 GiB adalah batas eksperimen yang ketat. Naikkan `HEAD_MEMORY_MIB=2048` atau lebih di konfigurasi dan ikuti panduan perubahan kapasitas. Jangan menyimpulkan kegagalan Kueue sebagai kegagalan logika antrean sebelum memastikan control plane stabil.

## Worker Ready tetapi pekerjaan Pending

```bash
kubectl describe nodes
kubectl -n hpc get pods -o wide
kubectl -n hpc describe pod NAMA_POD
kubectl -n hpc get workloads -o yaml
kubectl describe clusterqueue hpc-queue
```

Jika Insufficient cpu/memory, bandingkan allocatable dengan requests pekerjaan dan Pod sistem. Container limit Docker berbeda dari quota Kueue dan requests Pod. Setelah node mati, kuota Kueue tetap total semula sehingga Job admitted dapat menunggu worker sehat yang sedang sibuk.

Jika allocatable tidak sekitar target konfigurasi, periksa `docker exec NAMA_WORKER cat /var/lib/kubelet/config.yaml` dan log kubelet. Jangan menjalankan seluruh eksperimen sebelum alokasi ini benar. Jika mengubah kapasitas, lakukan rebuild sesuai panduan.

## Job tetap suspended

Pastikan controller Kueue Running, label queue pada Job benar, LocalQueue ada di namespace hpc, dan ClusterQueue Active. Baca `kubectl -n kueue-system logs deployment/kueue-controller-manager --all-containers=true --tail=100`. Webhook juga harus siap; rollout Deployment sukses tidak menjamin seluruh jalur webhook sudah dapat menerima request pada detik yang sama. Tunggu beberapa detik dan ulangi submit dengan nama baru jika request sebelumnya gagal sebelum Job tercipta.

## Mount NFS gagal

```bash
kubectl -n hpc-system logs deployment/nfs
kubectl -n hpc describe pod NAMA_POD
docker exec hpc-worker command -v mount.nfs
docker exec hpc-control-plane ls -ld /srv/hpc /srv/hpc/output
```

Ganti nama node sesuai konfigurasi. NFS client harus terpasang pada node, kernel host mendukung NFS v4, dan IP server pada PV harus sama dengan IP internal head. `Operation not supported` pada Ganesha VFS umumnya menuntut pemeriksaan filesystem direktori ekspor; gunakan ext4 Linux dan jangan `/mnt/d`. `Permission denied` saat menulis menuntut pemeriksaan UID 1000 dan owner direktori. Jangan mengatasinya dengan chmod 777 seluruh repository.

Untuk menguji akses dari satu worker secara manual pada lab:

```bash
HEAD_IP=$(kubectl get node hpc-control-plane -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')
docker exec hpc-worker mkdir -p /mnt/hpc-check
docker exec hpc-worker mount -t nfs -o vers=4.1 "$HEAD_IP:/shared" /mnt/hpc-check
docker exec hpc-worker ls /mnt/hpc-check
docker exec hpc-worker umount /mnt/hpc-check
```

PV sudah Bound tidak memastikan server berjalan. Setelah rebuild, IP head dapat berubah; setup membuat ulang PV dalam cluster baru.

## ImagePullBackOff atau ErrImageNeverPull

Image lokal harus dimuat ke containerd internal kind. Jalankan `kind load docker-image --name hpc hpc-compute:local hpc-nfs:local`. Jika mengubah worker.py, build ulang lalu load ulang sebelum membuat Job baru. Jangan mengganti isi tag local di tengah eksperimen yang sama. Pod lama tidak otomatis berganti image.

## SSH gagal

Periksa path public key konfigurasi dan key yang diberikan lewat `ssh -i`. Jalankan `docker exec hpc-control-plane systemctl status ssh --no-pager` dan `docker exec hpc-control-plane sshd -t`. Pastikan port 2222 belum dipakai aplikasi lain. Key host berubah saat rebuild; hapus entri known_hosts lama hanya setelah memastikan perubahan itu memang akibat rebuild.

## Job tidak pulih setelah worker dihentikan

Periksa berurutan: container worker benar-benar stopped, node menjadi NotReady/Unknown, Pod mendapat deletionTimestamp, kemudian Pod menjadi Failed dan Pod pengganti dibuat. Periksa anotasi safe-to-forcefully-delete pada Pod serta argumen FailureRecoveryPolicy pada Deployment Kueue.

```bash
kubectl get nodes
kubectl -n hpc get pods -o wide
kubectl -n hpc get job NAMA_JOB -o yaml
kubectl -n hpc get pods -l hpc.local/job=NAMA_JOB -o yaml
kubectl -n kueue-system get deployment kueue-controller-manager -o yaml
```

Proses normal mencakup deteksi node, toleration, tambahan masa tunggu controller pemulihan, dan startup ulang. Timeout 900 detik pada panduan adalah batas observasi, bukan SLA. Jika melewatinya, simpan snapshot/log dan laporkan skenario gagal. Jangan menghapus finalizer atau force-delete Pod untuk membuat hasil eksperimen tampak berhasil. Setelah bukti disimpan, hidupkan node kembali untuk membersihkan kondisi terminal melalui kubelet.

Rujukan: [mekanisme failure recovery Kueue](https://kueue.sigs.k8s.io/docs/tasks/manage/setup_failure_recovery/).
