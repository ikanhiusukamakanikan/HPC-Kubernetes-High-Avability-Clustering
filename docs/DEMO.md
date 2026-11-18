# Panduan demo langsung

Dokumen ini adalah skrip presentasi singkat untuk menunjukkan alur aplikasi dan skenario pemulihan. Jalankan dari root repository pada terminal Linux/WSL. Instalasi dependensi dan penjelasan konfigurasi lengkap tetap berada di [PANDUAN.md](PANDUAN.md).

## Yang dibuktikan

| # | Klaim | Yang dilihat audiens | Perkiraan waktu |
|---|---|---|---|
| 1 | Cluster sehat | Satu head dan tiga worker `Ready` | 1 menit |
| 2 | Job berjalan dari awal sampai akhir | Submit, antrean, Pod, dan hasil terverifikasi | 1 menit |
| 3 | Worker mati tetapi Job tetap selesai | Worker `NotReady`, Pod pengganti, Job `Complete` | 3 sampai 4 menit |
| 4 | Eksperimen formal sudah dijalankan | Ringkasan normal, FIFO, dan recovery | 1 menit |

## Persiapan

Jika cluster belum dibuat:

```bash
bash scripts/check.sh
bash scripts/setup.sh
bash tests/smoke.sh
```

Baris terakhir smoke test yang diharapkan:

```text
Smoke test lulus: hasil prima 1..1000 = 168 tersimpan melalui NFS.
```

Sebelum mulai demo, bersihkan Job lama dan siapkan direktori bukti yang unik:

```bash
export KUBECONFIG="$PWD/.runtime/kubeconfig"
alias k='kubectl --context kind-hpc'

k -n hpc delete jobs -l app=hpc-compute --ignore-not-found --wait=true
DEMO_RUN="results/demo-$(date -u +%Y%m%dT%H%M%SZ)"
printf '%s\n' "$DEMO_RUN" > .runtime/demo-run-path
echo "Bukti demo: $DEMO_RUN"
```

## Tata letak terminal

- **Panel A:** perintah utama.
- **Panel B:** perubahan Pod dan node.
- **Panel C:** collector bukti; boleh dilewati bila hanya melakukan presentasi singkat.

Di Panel B:

```bash
export KUBECONFIG="$PWD/.runtime/kubeconfig"
watch -n 2 'kubectl --context kind-hpc -n hpc get pods -o wide; kubectl --context kind-hpc get nodes'
```

Di Panel C, bila ingin merekam demo:

```bash
export KUBECONFIG="$PWD/.runtime/kubeconfig"
bash scripts/collect.sh "$(cat .runtime/demo-run-path)"
```

Collector dihentikan dengan `Ctrl+C` setelah Job recovery selesai.

## Langkah 1: tunjukkan kesehatan cluster

Di Panel A:

```bash
k get nodes -o wide
k -n kueue-system get pods
k -n hpc-system get pods
k -n hpc get pvc
```

Yang harus terlihat:

- `hpc-control-plane` dan tiga worker berstatus `Ready`.
- Controller Kueue dan NFS berstatus `Running`.
- PVC `shared` berstatus `Bound`.

## Langkah 2: submit satu Job

```bash
JOB=$(bash scripts/hpc.sh submit --seconds 30)
echo "$JOB"
bash scripts/hpc.sh queue
bash scripts/hpc.sh status
```

Output akan menampilkan nama Job, Workload pada antrean Kueue, dan Pod pada salah satu compute worker. Nama Job dan Pod dibuat dinamis, misalnya:

```text
prime-20261118143000-a1b2c3
```

## Langkah 3: tunggu dan tampilkan hasil

```bash
bash scripts/hpc.sh wait "$JOB" --timeout 900
bash scripts/hpc.sh result "$JOB"
```

Output penting:

```text
prime-... Complete
```

Hasil JSON harus memuat:

```json
{
  "status": "Succeeded",
  "prime_count": 5133,
  "expected_count": 5133,
  "verified": true
}
```

## Langkah 4: demo worker mati

Gunakan Job 30 detik agar demonstrasi lebih singkat. Eksperimen formal memakai Job 120 detik, tetapi mekanisme pemulihannya sama.

```bash
RECOVERY_JOB=$(bash scripts/hpc.sh submit --name demo-recovery --seconds 30)
k -n hpc wait --for=condition=Ready pod \
  -l "hpc.local/job=$RECOVERY_JOB" --timeout=180s

NODE=$(k -n hpc get pod -l "hpc.local/job=$RECOVERY_JOB" \
  -o jsonpath='{.items[0].spec.nodeName}')
echo "Job $RECOVERY_JOB berjalan pada $NODE"

sleep 5
bash scripts/fail-worker.sh "$NODE" "$(cat .runtime/demo-run-path)"
```

Output penghentian:

```text
Worker berhenti. Jangan start kembali sebelum pekerjaan pengganti berhasil.
```

Di Panel B, jelaskan alur yang terlihat:

1. Worker yang menjalankan Job berubah menjadi `NotReady`.
2. Pod awal berhenti atau tertahan `Terminating`.
3. Kueue menandai percobaan lama gagal setelah masa tunggu recovery.
4. Job controller membuat Pod baru pada worker yang sehat.
5. Nama Job tetap sama, tetapi nama Pod, UID, dan worker berubah.

Pada kampanye yang tersimpan, Pod pengganti mulai sekitar 142 sampai 147 detik setelah worker dimatikan. Nilai tersebut adalah hasil pengukuran, bukan SLA.

## Langkah 5: buktikan Job pulih

```bash
bash scripts/hpc.sh status
bash scripts/hpc.sh wait "$RECOVERY_JOB" --timeout 900
bash scripts/hpc.sh result "$RECOVERY_JOB"
```

Demo lulus bila:

- Pod pengganti berjalan di node berbeda dari `$NODE`.
- Job yang sama berakhir `Complete`.
- Hasil menampilkan `"verified": true`.

Setelah Job selesai, hidupkan kembali worker lama:

```bash
bash scripts/restore-worker.sh "$NODE"
```

Output akhirnya akan menunjukkan node kembali `Ready`.

## Langkah 6: tunjukkan bukti eksperimen formal

```bash
cat results/campaign-20261118T062115Z/campaign-summary.md
cat results/campaign-20261118T062115Z/recovery-01/recovery.csv
```

Angka utama yang dapat disampaikan:

- 9 run: tiga normal, tiga FIFO, dan tiga recovery.
- 48 dari 48 Job `Complete` dan terverifikasi.
- Distribusi normal 3 / 3 / 3 pada setiap run.
- Urutan admission FIFO terjaga pada setiap run.
- Recovery berhasil 3 dari 3 kali.
- Waktu recovery 142,212 sampai 146,672 detik.

Kampanye formal dapat dijalankan ulang di luar sesi presentasi dengan:

```bash
bash scripts/run-campaign.sh --yes
```

Perintah tersebut memerlukan sekitar 30 menit, sehingga tidak perlu dijalankan saat demo langsung.

## Menutup collector

Jika Panel C digunakan, tunggu sekitar lima detik setelah Job selesai lalu tekan `Ctrl+C`. Setelah itu, di Panel A:

```bash
DEMO_RUN=$(cat .runtime/demo-run-path)
python3 evaluation/summarize.py --run "$DEMO_RUN" --shared data/shared
cat "$DEMO_RUN/recovery.csv"
```

Jika collector merekam Job biasa dan Job recovery dari awal demo, ringkasan ideal menunjukkan dua Job selesai, tiga percobaan, satu kasus kegagalan, dan satu pengganti terverifikasi.

## Checklist lulus

| Pemeriksaan | Lulus bila |
|---|---|
| Node | Empat node `Ready` sebelum kegagalan |
| Kueue dan NFS | Pod sistem `Running`, PVC `Bound` |
| Job biasa | `Complete` dan `verified: true` |
| Worker mati | Worker berubah `NotReady` |
| Recovery | Pod baru muncul di worker lain |
| Hasil recovery | Job `Complete` dan `verified: true` |
| Pemulihan node | Worker lama kembali `Ready` |

## Jika ada masalah saat presentasi

| Masalah | Tindakan |
|---|---|
| Nama `demo-recovery` sudah ada | `bash scripts/hpc.sh cancel demo-recovery`, lalu ulangi submit |
| Recovery lebih lama dari hasil tersimpan | Tetap tunggu sampai timeout; 142–147 detik bukan SLA |
| Worker belum kembali | `docker start "$NODE"`, lalu `k wait --for=condition=Ready "node/$NODE" --timeout=180s` |
| Pod `ErrImageNeverPull` | Image belum dimuat ke node; gunakan hasil kampanye tersimpan dan perbaiki setelah presentasi |
| Collector menolak direktori | Jalankan ulang bagian persiapan untuk membuat nama `DEMO_RUN` baru |

## Pembersihan

Hapus Job demo tanpa menghapus hasil NFS:

```bash
bash scripts/hpc.sh cancel "$JOB" 2>/dev/null || true
bash scripts/hpc.sh cancel "$RECOVERY_JOB" 2>/dev/null || true
```

Untuk menghapus seluruh cluster setelah presentasi:

```bash
bash scripts/teardown.sh --yes
```

Direktori `data/shared/` dan `results/` tetap disimpan.
