# Cluster HPC Kubernetes dengan Pemulihan Worker

Implementasi proyek akhir: satu head node dan tiga compute node menggunakan kind di Docker Engine. Head menjalankan control plane, Kueue StrictFIFO, NFS, dan SSH satu akun. Pekerjaan independen menghitung bilangan prima; worker yang mati menyebabkan pekerjaan diulang dari awal pada worker lain. Status berada di etcd bawaan Kubernetes, hasil dan log di NFS, tanpa database tambahan atau dashboard.

**Status:** cluster sudah dijalankan dan diuji pada Docker Engine (17 November 2026): 50 Job dikirim dan seluruhnya selesai dengan hasil terverifikasi, distribusi normal 3 / 3 / 3, urutan FIFO terjaga, dan pemulihan setelah worker mati berhasil 3 dari 3 kali dengan waktu mulai ulang 145,3 sampai 146,9 detik. Rincian dan batasannya ada di [status validasi](docs/VALIDASI.md) dan [pengujian](docs/PENGUJIAN.md).

## Mulai dari sini

1. Baca [panduan menjalankan](docs/PANDUAN.md) untuk dependensi dan perintah lengkap.
2. Pelajari [arsitektur dan batasan](docs/ARSITEKTUR.md).
3. Gunakan [panduan pengujian dan analisis](docs/PENGUJIAN.md) setelah cluster berjalan.
4. Jika ada kendala, lihat [troubleshooting](docs/TROUBLESHOOTING.md).
5. Lihat [status validasi](docs/VALIDASI.md) untuk membedakan pemeriksaan offline, pengujian cluster, dan hal yang belum dibuktikan.
6. Untuk presentasi, ikuti [panduan demo](docs/DEMO.md).

Ringkasan perintah di Linux/WSL dengan Docker Engine lokal:

```bash
cp config/cluster.env.example config/cluster.env
# Edit SSH_PUBLIC_KEY terlebih dahulu.
bash scripts/check.sh
bash scripts/setup.sh
bash scripts/hpc.sh submit --seconds 30
bash scripts/hpc.sh status
ssh -p 2222 hpc@127.0.0.1

# Seluruh pengujian (normal, FIFO, recovery; 3 ulangan; tanpa data kumulatif):
bash scripts/run-campaign.sh

# Hapus cluster (data/shared dan results tetap):
bash scripts/teardown.sh --yes
```

Default setiap node: batas Docker **1 vCPU dan 1024 MiB RAM**. Worker menyediakan 800m CPU dan 700 MiB untuk Pod, termasuk komponen sistem. Kuota Kueue total 1500m CPU dan 384 MiB; setiap pekerjaan meminta 500m CPU dan 128 MiB. Perubahan kapasitas dijelaskan di panduan.

Empat node berbagi satu mesin fisik. Batas 1 GB head sangat ketat dan dapat menimbulkan OOM; penambahan RAM head dijelaskan di panduan. Proyek menguji availability lapisan komputasi, bukan HA control plane atau MPI lintas node.

## Struktur

```text
config/       parameter pengguna
deploy/       template kind, NFS, dan Kueue
images/       image komputasi dan NFS Ganesha
scripts/      setup, CLI, pengumpulan data, dan simulasi
evaluation/   pembuat CSV dari snapshot dan log eksekusi, serta metrik kampanye
tests/        pemeriksaan offline dan uji integrasi
docs/         panduan Bahasa Indonesia
```

Rujukan: [kind v0.31.0](https://github.com/kubernetes-sigs/kind/releases/tag/v0.31.0), [konfigurasi kind](https://kind.sigs.k8s.io/docs/user/configuration/), [instalasi Kueue](https://kueue.sigs.k8s.io/docs/getting-started/installation/), [ClusterQueue](https://kueue.sigs.k8s.io/docs/concepts/cluster_queue/), dan [Kubernetes Job](https://kubernetes.io/docs/concepts/workloads/controllers/job/).