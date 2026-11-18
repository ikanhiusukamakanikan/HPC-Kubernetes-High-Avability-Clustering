# Pengujian dan analisis

Dokumen ini berisi prosedur pengujian, cara menjalankannya secara otomatis, dan hasil yang sudah tercatat pada 17 November 2026 (bagian terakhir). Angka hanya boleh berasal dari eksperimen yang benar-benar dijalankan; jangan mengisi angka estimasi sebagai hasil pengukuran. Pengujian memakai pekerjaan independen, tanpa MPI, dengan parameter kecil agar fokus tetap pada antrean dan pemulihan.

## Pemeriksaan offline

Tidak memerlukan Docker atau cluster:

```bash
python3 -m unittest discover -s tests -p 'test_offline.py' -v
find scripts tests -name '*.sh' -exec bash -n {} \;
```

Paket `python3-yaml` diperlukan. Pemeriksaan meliputi hasil prima yang diketahui, penulisan output worker, template konfigurasi, penempatan Job, kebijakan pemulihan, dan perhitungan waktu pemulihan dari fixture. Fixture bukan hasil eksperimen cluster.

## Kampanye otomatis (disarankan)

`scripts/run-campaign.sh` menjalankan skenario normal, FIFO, dan recovery, masing-masing tiga kali, **tanpa data kumulatif**. Cluster harus sudah berjalan (`bash scripts/setup.sh`).

```bash
bash scripts/run-campaign.sh                    # 3 skenario x 3 ulangan, sekitar 30 menit
bash scripts/run-campaign.sh --only recovery    # satu skenario saja
bash scripts/run-campaign.sh --reps 1 --recovery-seconds 30 --yes   # uji cepat
```

Opsi: `--reps N`, `--only normal,fifo,recovery`, `--out DIR`, `--recovery-seconds N` (default 120, sama dengan laporan), `--yes` (tanpa konfirmasi).

Cara skrip mencegah data kumulatif:

1. Sebelum setiap run, semua Job, Pod, dan Workload lama dihapus dari cluster; skrip menunggu sampai benar-benar kosong dan berhenti jika masih ada setelah tiga menit.
2. Setiap run memakai nama Job unik (misalnya `normal11181530r1-1`), sehingga berkas lama di NFS tidak tercampur.
3. Metrik dihitung hanya dari Job dengan awalan nama run itu. Jika `summary.json` mencatat lebih banyak Job daripada yang dikirim run tersebut, run ditandai `contaminated`.
4. Hasil ditulis ke folder baru `results/campaign-<waktu>/`; folder `results/` lama tidak diubah dan berkas NFS tidak dihapus.

Syarat lulus tiap run: normal 9 dari 9 Job terverifikasi; FIFO 6 dari 6 dengan urutan admission sama dengan urutan submit; recovery tepat satu kasus kegagalan dengan Pod pengganti di node lain dan terverifikasi. Jika skrip dihentikan di tengah, worker yang dimatikan dihidupkan kembali dan kuota antrean dikembalikan secara otomatis.

Keluaran:

```text
results/campaign-<waktu>/
  normal-01 .. normal-03/     jobs.csv, attempts.csv, recovery.csv, distribution.csv,
  fifo-01 .. fifo-03/         summary.json, run-metrics.json, snapshots.jsonl,
  recovery-01 .. recovery-03/ events.json, nodes.json, failures.jsonl (recovery),
                              nfs-output/ (salinan bukti NFS run itu)
  environment/                versi dan konfigurasi
  campaign-summary.csv        satu baris per run
  campaign-summary.md         tabel ringkas, median dan rentang waktu pemulihan
```

`campaign-summary.md` adalah sumber angka untuk Bab III. Skrip keluar dengan status tidak nol bila ada run yang bermasalah.

## Prosedur manual

Bagian berikut adalah prosedur yang sama dilakukan langkah demi langkah. Pakai hanya bila ingin mengendalikan sendiri tiap tahap.

## Pengumpulan bukti

Mulai collector di terminal pertama, sebelum mengirim pekerjaan. Gunakan direktori baru untuk setiap skenario dan pengulangan:

```bash
bash scripts/collect.sh results/normal-01
```

Collector menyimpan snapshot Job, Pod, dan Workload setiap sekitar dua detik, serta snapshot terakhir events dan node. Hentikan dengan Ctrl+C setelah seluruh pekerjaan selesai dan collector sempat merekam kondisi akhirnya. Jangan menghapus Job sebelum pengumpulan selesai. Collector tidak menghapus output NFS.

Semua Job HPC yang terlihat masuk snapshot, sehingga Job dari run sebelumnya membuat CSV dan `summary.json` bersifat kumulatif. Karena itu, **sebelum setiap run manual**, ekspor hasil run sebelumnya lalu bersihkan Job lama dan tunggu sampai kosong:

```bash
kubectl -n hpc delete jobs -l app=hpc-compute --wait=true
kubectl -n hpc get jobs,pods,workloads     # harus kosong sebelum collector dimulai
```

Gunakan nama unik per skenario/pengulangan dan jangan menjalankan eksperimen lain secara bersamaan. Saat menganalisis folder yang sudah kumulatif, pisahkan skenario menurut nama Job.

## Eksekusi normal dan distribusi

Setelah smoke test, gunakan 9 pekerjaan masing-masing minimal 20 detik:

```bash
for i in $(seq 1 9); do
  bash scripts/hpc.sh submit --name "normal01-$i" --seconds 20
  sleep 1
done
for i in $(seq 1 9); do
  bash scripts/hpc.sh wait "normal01-$i" --timeout 900
done
```

Harapkan semua Job Complete dan hasil terverifikasi. Evaluasi node yang dipilih dari attempts.csv. Karena penyebaran memakai preferensi scheduler, perbedaan jumlah percobaan antar-node tidak otomatis berarti gagal. Periksa apakah pekerjaan hanya dijalankan pada tiga worker dan mengapa distribusi tidak merata bila ada.

## Antrean FIFO

Gunakan kuota satu pekerjaan untuk mengamati admission secara jelas. Di terminal kedua:

```bash
export KUBECONFIG="$PWD/.runtime/kubeconfig"
kubectl patch clusterqueue hpc-queue --type=json -p='[
 {"op":"replace","path":"/spec/resourceGroups/0/flavors/0/resources/0/nominalQuota","value":"500m"},
 {"op":"replace","path":"/spec/resourceGroups/0/flavors/0/resources/1/nominalQuota","value":"128Mi"}
]'
```

Mulai collector dengan run `results/fifo-01`, lalu submit enam pekerjaan secara berurutan:

```bash
for i in $(seq 1 6); do
  bash scripts/hpc.sh submit --name "fifo01-$i" --seconds 15
  sleep 2
done
for i in $(seq 1 6); do
  bash scripts/hpc.sh wait "fifo01-$i" --timeout 900
done
```

Bandingkan urutan `created_at` dengan `admitted_at` di jobs.csv. Timestamp admission berasal dari kondisi Admitted Workload yang tertangkap collector. Jika timestamp sama sampai resolusi API atau data hilang, laporkan urutannya tidak dapat dibedakan; jangan mengarang urutan dari completion time. Raw Workload di snapshots.jsonl menyimpan creationTimestamp Workload untuk pemeriksaan lebih teliti.

Kembalikan kuota ke konfigurasi file sebelum skenario lain:

```bash
source scripts/common.sh
render "$ROOT/deploy/queue.yaml.tmpl" > "$ROOT/.runtime/queue.yaml"
k apply -f "$ROOT/.runtime/queue.yaml"
```

## Kegagalan dan pemulihan worker

Mulai collector `results/recovery-01`. Di terminal kedua, kirim satu pekerjaan 120 detik agar masih aktif saat worker dihentikan:

```bash
source scripts/common.sh
JOB=$(bash scripts/hpc.sh submit --name recovery01 --seconds 120)
k -n hpc wait --for=condition=Ready pod -l "hpc.local/job=$JOB" --timeout=180s
NODE=$(k -n hpc get pod -l "hpc.local/job=$JOB" -o jsonpath='{.items[0].spec.nodeName}')
echo "Job $JOB berjalan pada $NODE"
# Tunggu beberapa detik agar attempt.json awal tersedia pada NFS.
sleep 5
bash scripts/fail-worker.sh "$NODE" results/recovery-01
bash scripts/hpc.sh status
bash scripts/hpc.sh wait "$JOB" --timeout 900
bash scripts/hpc.sh result "$JOB"
```

Catatan: `source scripts/common.sh` mengaktifkan `set -euo pipefail` pada terminal interaktif, sehingga satu perintah gagal dapat menutup terminal. Untuk demo atau pengulangan, lebih aman memakai `scripts/run-campaign.sh` atau `export KUBECONFIG="$PWD/.runtime/kubeconfig"` dengan `alias k='kubectl --context kind-hpc'`.

Pod pengganti harus memiliki UID dan node berbeda, sementara nama Job tetap sama. Periksa snapshot, events.json, dan minimal dua direktori percobaan NFS. Percobaan awal boleh tetap mencatat Running pada file karena proses terputus; gunakan observed_pod_phase dan bukti penghentian container untuk menafsirkannya.

Setelah Job Complete, tunggu sekitar lima detik agar collector merekam kondisi terakhir, hentikan collector, kemudian hidupkan worker kembali:

```bash
bash scripts/restore-worker.sh "$NODE"
```

Skrip pemulihan node hanya menghidupkan container; ini bukan mekanisme memulihkan pekerjaan. Pekerjaan harus berhasil pada worker lain sebelum node lama dihidupkan. Tidak ada force-delete manual dalam prosedur ini. Jika timeout, simpan bukti kegagalan dan gunakan troubleshooting.

## Membuat CSV

Setelah collector berhenti, jalankan dari host. Sesuaikan `--shared` jika konfigurasi tidak memakai direktori default:

```bash
python3 evaluation/summarize.py --run results/recovery-01 --shared data/shared
```

| Berkas | Isi |
|---|---|
| `jobs.csv` | Waktu submit, admission pertama yang tertangkap, awal eksekusi pertama, completion, status, dan validasi |
| `attempts.csv` | Node, UID Pod, status dari file, fase Pod teramati, durasi, dan hasil tiap percobaan |
| `recovery.csv` | Job terdampak, node mati/pengganti, waktu kegagalan, awal percobaan pengganti, dan validasi |
| `distribution.csv` | Jumlah percobaan per node; termasuk percobaan yang terputus |
| `summary.json` | Jumlah Job teramati, Complete, hasil terverifikasi, dan kasus pemulihan |

Nilai yang tidak memiliki bukti dibiarkan kosong. `Unfinished` bukan otomatis gagal: bisa berarti collector dihentikan sebelum status akhir tersedia. Jika `failure_cases=0` pada skenario recovery, periksa apakah attempt awal sudah tercatat sebelum stop dan file failure ada; nilai nol bukan bukti tidak ada gangguan.

Metrik utama:

- Tingkat keberhasilan = Job Complete dengan hasil terverifikasi / Job yang dikirim. Cocokkan jumlah Job pada daftar submit dengan jobs_observed agar pekerjaan yang tidak pernah tertangkap tidak hilang dari denominator.
- Waktu antre = admission pertama yang tertangkap − creationTimestamp Job. Ini mencakup keterlambatan pembuatan Workload; gunakan timestamp Workload bila membutuhkan waktu antre Kueue murni.
- Turnaround = completionTime Job − creationTimestamp Job, termasuk antre dan seluruh percobaan.
- Durasi percobaan = monotonic elapsed_seconds di worker; percobaan mati bisa tidak memiliki nilai akhir.
- Waktu pemulihan = awal program pada percobaan pengganti di node lain − waktu permintaan stop worker. Termasuk deteksi, toleration, failure recovery, penjadwalan, mount, dan startup. Ini bukan waktu sampai hasil selesai.

`recovery.csv.verified` menandai validasi hasil percobaan pengganti pertama. Tetap periksa `jobs.csv.status=Complete`; validasi aplikasi dan keberhasilan orkestrasi merupakan dua bukti berbeda.

Lakukan tiga pengulangan untuk tiap skenario normal, FIFO, dan recovery dengan nama/direktori berbeda. Gunakan median serta rentang min–maks waktu pemulihan, dan catat parameter mesin, versi, dan batas sumber daya. Tidak ada target waktu pemulihan wajib; laporkan hasil nyata dan penyebab variasinya.

Arsipkan konfigurasi dan versi dari terminal host:

```bash
docker version > results/docker-version.txt
kind version > results/kind-version.txt
kubectl --kubeconfig .runtime/kubeconfig version -o yaml > results/kubernetes-version.yaml
docker image inspect hpc-compute:local hpc-nfs:local > results/images.json
cp config/cluster.env results/cluster.env
```

Jangan menyertakan `.runtime/kubeconfig` atau private key pada pengumpulan tugas. Untuk BAB III–IV nantinya, gunakan CSV dan bukti kejadian aktual; jangan mengisi angka estimasi seolah hasil pengukuran.

## Hasil yang tercatat (17 November 2026)

Sumber: sembilan folder `results/<skenario>-0N`. Karena folder tersebut kumulatif, angka di bawah dihitung ulang per skenario berdasarkan nama Job. Dari seluruh kampanye, 50 Job dikirim dan 50 Complete dengan hasil terverifikasi; terdapat 53 percobaan (tiga tambahan adalah percobaan yang terputus akibat worker dimatikan).

| Skenario | Run | Job per run | Complete dan terverifikasi |
|---|---|---|---|
| Smoke test | 2 | 1 | 2 dari 2 |
| Normal | 3 | 9 | 27 dari 27 |
| FIFO | 3 | 6 | 18 dari 18 |
| Recovery | 3 | 1 | 3 dari 3 |

### Normal dan distribusi

| Run | Job per worker (worker / worker2 / worker3) | Waktu antre terbesar | Median turnaround |
|---|---|---|---|
| normal-01 | 3 / 3 / 3 | 40 s | 43 s |
| normal-02 | 3 / 3 / 3 | 20 s | 24 s |
| normal-03 | 3 / 3 / 3 | 40 s | 43 s |

Job berjalan dalam gelombang tiga (waktu antre sekitar 0, 20, dan 40 s), sesuai kuota tiga pekerjaan serentak dan Job 20 detik. `normal-02` tampak lebih cepat hanya karena Job 4 sampai 9 dikirim sekitar dua menit setelah Job 1 sampai 3, sehingga antrean lebih pendek; ini bukan percepatan.

### FIFO

| Run | Urutan admission = urutan submit | Waktu antre Job 1 sampai 6 (s) | Job per worker |
|---|---|---|---|
| fifo-01 | Ya | 0, 17, 32, 48, 64, 80 | 6 / 0 / 0 |
| fifo-02 | Ya | 0, 17, 33, 49, 66, 82 | 6 / 0 / 0 |
| fifo-03 | Ya | 0, 16, 33, 49, 65, 81 | 5 / 0 / 1 |

Setiap Job menunggu Job di depannya (jarak sekitar 16 sampai 17 s, yaitu 15 s komputasi ditambah sekitar 2 s overhead). Pada skenario ini hanya satu Pod berjalan pada satu waktu, dan hampir semua Job mendarat di satu worker. Dugaan penyebabnya: Pod yang sudah selesai tidak dihitung oleh topology spread sehingga semua worker tampak sama kosong. Dugaan ini tidak dibuktikan oleh data; rancangan hanya menjanjikan spread sebagai preferensi.

### Kegagalan dan pemulihan

| Run | Worker dimatikan | Pengganti berjalan di | Waktu pemulihan | Turnaround Job | Hasil |
|---|---|---|---|---|---|
| recovery-01 | hpc-worker | hpc-worker2 | 145,3 s | 275 s | Complete, terverifikasi |
| recovery-02 | hpc-worker | hpc-worker2 | 146,9 s | 277 s | Complete, terverifikasi |
| recovery-03 | hpc-worker | hpc-worker3 | 146,9 s | 278 s | Complete, terverifikasi |

Median 146,9 s, rentang 145,3 sampai 146,9 s. Setiap pengganti berjalan di worker lain, pada Pod baru dengan nama Job yang sama, dan mengulang komputasi 120 detik dari awal. Rentang yang sempit wajar karena penundaan berasal dari timer tetap, bukan proses acak. Waktu pemulihan adalah mulai percobaan pengganti dikurangi saat permintaan stop, bukan waktu sampai Job selesai.

Rincian waktu pada `recovery-01` (nol = permintaan stop; dari `events.json`):

| Detik | Kejadian | Komponen |
|---|---|---|
| 0 | Container worker dimatikan (`docker stop --time 0`) | `fail-worker.sh` |
| sekitar 49 | NodeNotReady | Controller manager |
| sekitar 79 | TaintManagerEviction (30 s setelah taint) | Taint manager |
| sekitar 144 | KueueForcefullyDeleted (Pod dipaksa Failed) | Kueue |
| sekitar 145 | Pod pengganti dibuat, dijadwalkan di worker lain, dan mulai | Job controller, scheduler, kubelet |

Jadi sekitar 145 s adalah deteksi sekitar 49 s, toleration 30 s, dan masa tunggu Kueue sekitar 65 s. Ini bukan SLA; di repositori ini hanya `EVICTION_SECONDS` (30 s) yang dapat diubah.

### Hal yang perlu dijelaskan saat membaca data lama

1. Total per node pada `distribution.csv` tampak timpang (misalnya 31 / 11 / 11 pada `recovery-03`) karena kumulatif dan karena seluruh kegagalan mengenai `hpc-worker`. Per skenario, distribusi normal merata 3 / 3 / 3.
2. `failure_cases` 1, 2, dan 3 pada tiga run recovery adalah akibat data kumulatif, bukan tiga kegagalan per run.
3. `attempt.json` percobaan yang terputus tetap `Running` karena proses mati sebelum sempat menulis status akhir.
4. Tiga ulangan pada satu mesin menunjukkan perilaku berulang, bukan statistik. Laporkan median dan rentang serta lingkungan pengujian.