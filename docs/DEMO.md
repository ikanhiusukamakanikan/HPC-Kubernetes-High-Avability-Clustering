# Panduan demo langsung
## Yang harus dibuktikan

| # | Klaim | Yang dilihat audiens | Waktu |
|---|---|---|---|
| 1 | Cluster sehat | Empat node Ready | 1 menit |
| 2 | Pekerjaan berjalan dari awal sampai akhir | Submit, antrean, eksekusi, hasil terverifikasi | 2 menit |
| 3 | Worker mati dan pekerjaan tetap selesai | Node NotReady, Pod pengganti di worker lain, Job Complete | 3 sampai 4 menit |
| 4 | Ada bukti dari run nyata | Folder `results/`, 3 dari 3 pemulihan | 1 menit |

## Persiapan

1. `bash scripts/check.sh`, lalu `bash scripts/setup.sh` bila cluster belum ada (setup mengunduh image, beri waktu).
2. `bash tests/smoke.sh`. Baris terakhir yang diharapkan: `Smoke test lulus: hasil prima 1..1000 = 168 tersimpan melalui NFS.`
3. Latih seluruh demo kegagalan sekali, lalu hidupkan kembali worker.
4. Bersihkan Job lama agar layar rapi: `kubectl -n hpc delete jobs -l app=hpc-compute --wait=true`.
5. Rekam video layar satu run penuh sebagai cadangan.
6. Pastikan SSH ke head sudah pernah dicoba (lihat `PANDUAN.md`); uji SSH belum tercatat di `results/`.
7. Tutup notifikasi, besarkan font terminal (minimal 22 pt), dan colok daya.

## Tata letak terminal (3 panel)

- **Panel A:** tempat mengetik perintah. Siapkan semua perintah dalam berkas teks dan salin-tempel.
- **Panel B:** `watch -n 2 kubectl -n hpc get pods -o wide`, dan bila muat `watch -n 2 kubectl get nodes`.
- **Panel C (opsional):** `bash scripts/collect.sh results/demo` untuk merekam bukti.

Di setiap panel:

```bash
export KUBECONFIG="$PWD/.runtime/kubeconfig"
alias k='kubectl --context kind-hpc'
```

Hindari `source scripts/common.sh` di terminal interaktif: skrip itu mengaktifkan `set -euo pipefail`, sehingga satu perintah gagal dapat menutup terminal di depan audiens.

## Langkah 1: kesehatan cluster

```bash
k get nodes -o wide
k -n kueue-system get pods
k -n hpc-system get pods
k -n hpc get pvc
```

Lulus bila satu control-plane dan tiga worker `Ready`, Pod Kueue dan NFS `Running`, dan PVC `shared` `Bound`.

## Langkah 2: submit dan antrean

```bash
JOB=$(bash scripts/hpc.sh submit --seconds 30)
echo $JOB
bash scripts/hpc.sh queue
bash scripts/hpc.sh status
```

Lulus bila nama Job tercetak, Workload muncul pada antrean, dan Pod dijadwalkan di salah satu worker.

## Langkah 3: tunggu dan tampilkan hasil

```bash
bash scripts/hpc.sh wait "$JOB"
bash scripts/hpc.sh result "$JOB"
```

Lulus bila `wait` mencetak `Complete` dan hasil menampilkan `"verified": true`.

## Langkah 4: demo kegagalan worker

Gunakan Job **30 detik**, bukan 120 detik. Waktu mulai ulang tetap sekitar 145 detik, tetapi total menunggu turun dari sekitar 4,5 menit menjadi sekitar 3 menit. Sampaikan: "Eksperimen tercatat memakai Job 120 detik; demo langsung memakai 30 detik."

```bash
JOB=$(bash scripts/hpc.sh submit --name demo1 --seconds 30)
k -n hpc wait --for=condition=Ready pod -l "hpc.local/job=$JOB" --timeout=180s
NODE=$(k -n hpc get pod -l "hpc.local/job=$JOB" -o jsonpath='{.items[0].spec.nodeName}')
echo "Job berjalan di: $NODE"
sleep 5
bash scripts/fail-worker.sh "$NODE" results/demo
```

`fail-worker.sh` hanya menerima compute node dan mematikan container dengan `docker stop --time 0`, setara mencabut listrik. Selama menunggu, narasikan panel B dengan garis waktu dari run `recovery-01`:

| Sekitar | Yang terlihat | Penjelasan |
|---|---|---|
| 0 s | Container worker dihentikan | Worker yang menjalankan Job dimatikan paksa |
| 49 s | Node `NotReady` | Control plane menyadari node diam |
| 79 s | Pod ditandai dihapus, tertahan `Terminating` | Toleration 30 s habis; tidak ada yang bisa memastikan Pod berhenti |
| 144 s | Pod dipaksa `Failed` | Kueue failure recovery setelah menunggu satu menit |
| 145 s | Pod pengganti di worker lain | Job controller membuat pengganti, scheduler menempatkannya di worker sehat |

Setelah Pod pengganti berjalan:

```bash
bash scripts/hpc.sh status
bash scripts/hpc.sh wait "$JOB" --timeout 900
bash scripts/hpc.sh result "$JOB"
```

Lulus bila Pod pengganti berada di node **berbeda** dari `$NODE`, Job berakhir `Complete`, dan hasil `"verified": true`. Setelah Job selesai, hidupkan kembali worker:

```bash
bash scripts/restore-worker.sh "$NODE"
```

## Langkah 5: tunjukkan bukti tercatat

```bash
cat results/recovery-01/recovery.csv
cat results/recovery-01/summary.json
ls results/
```

Angka kunci: 50 Job dikirim dan 50 Complete terverifikasi; distribusi normal 3 / 3 / 3 pada tiga run; urutan FIFO terjaga pada tiga run; pemulihan 3 dari 3, 145,3 sampai 146,9 s, di worker berbeda. Siapkan penjelasan bahwa CSV lama bersifat kumulatif (lihat `VALIDASI.md`); kampanye baru dari `scripts/run-campaign.sh` tidak kumulatif.

## Daftar lulus atau gagal

| Pemeriksaan | Perintah | Berfungsi bila |
|---|---|---|
| Node siap | `k get nodes` | Empat node `Ready` |
| Penyimpanan | `k -n hpc get pvc` dan `bash tests/smoke.sh` | PVC `Bound`; smoke test mencetak baris 168 |
| Antrean | `bash scripts/hpc.sh queue` | Workload terdaftar berurutan |
| Job berjalan | `bash scripts/hpc.sh wait "$JOB"` | `Complete` |
| Hasil benar | `bash scripts/hpc.sh result "$JOB"` | `verified: true` |
| Pemulihan | Panel B dan `hpc.sh result` | Pod baru di node lain, Job `Complete` |

## Bila terjadi masalah

| Masalah | Tindakan |
|---|---|
| Cluster mati atau Pod tertahan | Putar video cadangan: "Ini rekaman run yang sama" |
| `ErrImageNeverPull` | Image belum dimuat ke node; tidak bisa diperbaiki langsung, pakai video |
| Pemulihan lebih lambat dari 145 s | Lanjutkan narasi dan sebut tiga run tercatat (145 sampai 147 s) |
| Job mendarat di worker yang tidak diduga | Tidak masalah, `NODE` dibaca dari Pod |
| Worker tidak mau hidup | `docker start NODE`, lalu `k wait --for=condition=Ready node/NODE --timeout=180s` |
| Nama Job demo sudah ada | Pakai nama baru (`demo2`) atau `bash scripts/hpc.sh cancel demo1` |

## Pembersihan

```bash
bash scripts/hpc.sh cancel demo1
bash scripts/restore-worker.sh "$NODE"   # bila belum dihidupkan
```

Untuk menghapus seluruh cluster: `bash scripts/teardown.sh --yes` (data NFS dan `results/` tetap).