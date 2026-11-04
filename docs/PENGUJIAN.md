# Pengujian dan analisis

Dokumen ini adalah prosedur pengujian yang akan dilakukan setelah deployment. Tidak ada angka hasil cluster yang diklaim sebelum eksperimen benar-benar dijalankan. Pengujian memakai pekerjaan independen, tanpa MPI, dengan parameter kecil agar fokus tetap pada antrean dan pemulihan.

## Pemeriksaan offline

Tidak memerlukan Docker atau cluster:

```bash
python3 -m unittest discover -s tests -p 'test_offline.py' -v
find scripts tests -name '*.sh' -exec bash -n {} \;
```

Paket `python3-yaml` diperlukan. Pemeriksaan meliputi hasil prima yang diketahui, penulisan output worker, template konfigurasi, penempatan Job, kebijakan pemulihan, dan perhitungan waktu pemulihan dari fixture. Fixture bukan hasil eksperimen cluster.

## Pengumpulan bukti

Mulai collector di terminal pertama, sebelum mengirim pekerjaan. Gunakan direktori baru untuk setiap skenario dan pengulangan:

```bash
bash scripts/collect.sh results/normal-01
```

Collector menyimpan snapshot Job, Pod, dan Workload setiap sekitar dua detik, serta snapshot terakhir events dan node. Hentikan dengan Ctrl+C setelah seluruh pekerjaan selesai dan collector sempat merekam kondisi akhirnya. Jangan menghapus Job sebelum pengumpulan selesai. Collector tidak menghapus output NFS.

Semua Job HPC yang terlihat masuk snapshot. Jalankan skenario pada cluster yang tidak memiliki Job eksperimen lama; ekspor hasilnya dahulu, lalu hapus Job lama jika memang tidak diperlukan. Gunakan nama unik per skenario/pengulangan. Jangan menjalankan eksperimen lain secara bersamaan.

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
