# Status validasi implementasi

Dokumen ini membedakan pemeriksaan offline, pengujian pada cluster, dan hal yang belum dibuktikan. Seluruh angka cluster di bawah berasal dari folder `results/` yang direkam pada 17 November 2026 (UTC, sekitar 17:50 sampai 18:25). Rincian dan cara membacanya ada di [PENGUJIAN.md](PENGUJIAN.md).

## Pemeriksaan offline (tanpa cluster)

| Pemeriksaan | Hasil |
|---|---|
| `python3 -m unittest discover -s tests -p test_offline.py -v` | 5 pengujian lulus |
| `bash -n` pada seluruh skrip Bash di scripts dan tests | Lulus |
| Kompilasi sintaks Python di scripts, images, evaluation, dan tests | Lulus |

Pengujian Python meliputi hasil prima referensi, eksekusi worker dengan output terverifikasi, render template YAML, pembatasan penempatan Job dan konfigurasi recovery, serta analisis CSV dengan bukti pemulihan sintetis. Hasil fixture analisis tidak merupakan hasil cluster.

## Pengujian pada cluster (kind di Docker Engine)

| Pemeriksaan | Hasil | Bukti |
|---|---|---|
| Build image, deployment kind, Kueue, dan NFS | Berjalan; empat node, Kueue, NFS, dan PVC siap | `results/*/nodes.json` |
| Smoke test (prima 1..1000 = 168 melalui NFS) | 2 dari 2 lulus | `jobs.csv` (Job `prime-...`) |
| Eksekusi normal dan distribusi | 3 run x 9 Job, 27 dari 27 Complete dan terverifikasi; distribusi 3 / 3 / 3 pada setiap run | `results/normal-01..03` |
| Antrean FIFO (kuota satu pekerjaan) | 3 run x 6 Job, 18 dari 18 Complete; urutan admission sama dengan urutan submit pada ketiga run | `results/fifo-01..03` |
| Worker mati dan pemulihan otomatis | 3 dari 3 berhasil; waktu mulai pengganti 145,3 s, 146,9 s, dan 146,9 s; pengganti selalu di worker lain | `results/recovery-01..03` |
| Keseluruhan | 50 Job dikirim, 50 Complete dan terverifikasi; 53 percobaan (tiga percobaan tambahan adalah percobaan yang terputus oleh kegagalan worker) | `results/recovery-03/summary.json` |

Konfigurasi yang tercatat: tiap worker melaporkan sekitar 800m CPU dan 700 MiB allocatable pada host yang melaporkan 16 CPU dan sekitar 7,6 GiB RAM. Versi: kind v0.31.0, Kubernetes v1.35.0, Kueue v0.20.4.

## Cara membaca folder results/ yang sudah ada

Sembilan folder pertama direkam dengan collector tanpa membersihkan Job lama, sehingga CSV dan `summary.json` bersifat **kumulatif** (misalnya `recovery-03` menampilkan 50 Job). Angka per skenario di atas sudah dipisahkan berdasarkan nama Job (`normal01-*`, `fifo01-*`, `recovery01`). `failure_cases` bernilai 1, 2, dan 3 pada tiga run recovery karena percobaan terputus dari run sebelumnya ikut terhitung; kegagalan worker sebenarnya tepat satu per run. Berkas `current.tmp` pada tiap folder hanyalah berkas sementara collector, bukan bukti.

Untuk data yang tidak kumulatif, gunakan `scripts/run-campaign.sh` (lihat PENGUJIAN.md). Skrip itu membersihkan Job lama sebelum setiap run dan memberi nama Job unik.

## Yang belum dibuktikan

| Hal | Status |
|---|---|
| SSH ke head node dan perintah `hpc` di dalamnya | Tidak ada bukti tercatat di `results/`; uji manual sebelum demo |
| Kecukupan RAM 1 GiB untuk head | Tidak ada pengukuran tercatat; naikkan `HEAD_MEMORY_MIB` bila OOM |
| Kegagalan head, NFS, atau host | Di luar cakupan; titik tunggal kegagalan |
| Perilaku `FailureRecoveryPolicy` pada versi selain Kueue v0.20.4 | Belum diuji; fitur masih Alpha |
| Jumlah ulangan | Tiga per skenario pada satu mesin: cukup untuk menunjukkan perilaku berulang, belum untuk statistik |

Semua node berbagi satu kernel, jam, CPU, dan RAM, sehingga hasil menggambarkan perilaku orkestrasi, bukan performa jaringan atau perangkat keras terpisah.