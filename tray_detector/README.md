# Tray Detector Pipeline

Modul `tray_detector` adalah sistem pengukur jarak berbasis visi komputer presisi (Computer Vision) untuk menghitung elevasi/jarak (`D_tray`) dari kamera *overhead* menuju dasar *tray/drip-grate* pada mesin pembuat kopi (seperti Jura). 

Tujuan utamanya adalah menentukan apakah tray berada pada posisi semestinya, miring, atau tidak pada lokasinya dengan resolusi jarak yang sangat akurat.

## Daftar Isi
- [Fitur Utama](#fitur-utama)
- [Prasyarat](#prasyarat)
- [Kalibrasi Awal (Wajib Sekali)](#kalibrasi-awal-wajib-sekali)
- [Cara Penggunaan (CLI)](#cara-penggunaan-cli)
- [Pemilihan Metode Deteksi](#pemilihan-metode-deteksi)
- [Konfigurasi Fisik (Manual)](#konfigurasi-fisik-manual)
- [Struktur Output (JSON)](#struktur-output-json)

---

## Fitur Utama
1. **Deteksi Berbasis Gelas (YOLO):** Mampu mengisolasi pendeteksian hanya di sisi luar gelas kuning melalui masking dinamis yang memotong bentuk gelas. Canny Edge tidak akan terkecoh pantulan di dalam gelas.
2. **Pendeteksian Empty Tray (Fallback):** Bila gelas tidak ditemukan, sistem otomatis mengaktifkan heuristik kotak potong vertikal (crop atas/bawah dan mengabaikan pinggir mangkuk saringan di tengah) untuk menghindari salah ukur dari tepi kerangka tray mati.
3. **Adaptive Thresholding & NMS:** Fitur *Spatial Non-Maximum Suppression* secara otomatis akan memangkas deteksi garis kembar pada bagian atas & bawah dari 1 batang sekat yang sama (memastikan 1 baris sekat hijau tebal murni hanya dihitung 1 pitch).

## Prasyarat
Pastikan environment sudah memiliki paket berikut (biasanya diinstal via environment pip/conda utama):
```bash
pip install opencv-python numpy ultralytics pyyaml
```
Sistem juga bergantung pada *weights* model pendeteksi ukuran kecil (`cup_detection_v3...pt`) yang harus ada dalam direktori `weights/` di root folder.

## Kalibrasi Awal (Wajib Sekali)

> **Penting:** Sebelum menggunakan tray detector, lakukan kalibrasi **sekali saja**. Kalibrasi ini menghitung konstanta fisik tray (`P_real_cm`, `ref_slats`) secara otomatis dan menyimpannya ke file `tray_calibration.yaml`.

### Langkah-Langkah
1. Letakkan **tray kosong** (tanpa gelas) di posisi normal.
2. Ukur jarak dari kamera ke permukaan tray menggunakan penggaris/meteran (dalam cm).
3. Jalankan script kalibrasi:

```bash
# Via kamera live (disarankan)
python -m tray_detector.calibrate_tray --camera 0 --distance 22.1

# Via gambar
python -m tray_detector.calibrate_tray --image foto_tray.jpg --distance 22.1
```

4. Pada mode kamera: tekan `c` untuk capture & kalibrasi, atau `q` untuk batal.
5. Hasil disimpan otomatis ke `tray_detector/tray_calibration.yaml`.

### Contoh Output Kalibrasi
```yaml
calibrated_at: "2026-04-07T17:00:00+07:00"
D_known_cm: 22.1
P_real_cm: 0.6660
ref_slats: 27
median_pitch_px: 12.4
theta_tilt_deg: 20.0
```

> **Catatan:** Kalibrasi ulang hanya diperlukan jika posisi kamera atau jenis tray berubah.

---

## Cara Penggunaan (CLI)
Anda dapat memanggil modul detektor langsung dari direktori root aplikasi utama (misal: `midas-coffee-machine`):

### 1. Mode Gambar Tunggal
Memproses satu foto dan mencetak hasil JSON + menyimpan visualisasi.
```bash
# Auto-detect cup via YOLO (Default)
python -m tray_detector.run_tray_detector --image test_tray25.0cm.jpg

# Menggunakan Method B (Sangat Disarankan karena Paling Akurat)
python -m tray_detector.run_tray_detector --image <nama_file.jpg> --method B

# Tanpa YOLO (Deteksi seluruh area frame)
python -m tray_detector.run_tray_detector --image <nama_file.jpg> --no-yolo
```

### 2. Mode Batch (Direktori)
Memproses seluruh gambar dalam satu folder sekaligus.
```bash
python -m tray_detector.run_tray_detector --input_dir path/to/images/ --output_dir results/batch/
```

### 3. Mode Live Camera
Menjalankan deteksi real-time menggunakan webcam atau kamera USB.
```bash
# Kamera default (index 0)
python -m tray_detector.run_tray_detector --camera

# Kamera spesifik dengan index 2
python -m tray_detector.run_tray_detector --camera 2

# Live mode dengan penguncian fokus (Wajib untuk akurasi jarak jauh tanpa gelas)
python -m tray_detector.run_tray_detector --camera 0 --lock-focus --focus-value 0
```

#### Shortcut Keyboard (Live Mode)
* `q`: Keluar dari aplikasi.
* `s`: Ambil screenshot (disimpan ke root folder).

---

## Opsi Argumen Lengkap

| Argumen | Deskripsi |
| :--- | :--- |
| `--image` | Path ke satu file gambar untuk diproses. |
| `--input_dir` | Direktori berisi kumpulan gambar untuk batch processing. |
| `--camera [index]` | Aktifkan mode live (default index 0 jika tidak diisi). |
| `--output_dir` | (Opsional) Folder tujuan visualisasi. Default: `tray_detector/results`. |
| `--method` | Pilihan: `auto` (fusi), `A` (apparent), `B` (pitch), `C` (PnP). Default: `auto`. |
| `--no-yolo` | Matikan YOLO. Gunakan full frame sebagai ROI (terbaik untuk tray kosong). |
| `--weights` | (Opsional) Path ke file YOLO weights `.pt` kustom. |
| `--params` | (Opsional) Path ke file calibration `.yaml` kustom. |
| `--lock-focus` | Menonaktifkan auto-focus kamera. Penting untuk kestabilan pembacaan. |
| `--focus-value` | Nilai fokus tetap (0-255). Nilai `0` biasanya berarti *infinity*. |

---

## Pemilihan Metode Deteksi
* **Method A**: Mengandalkan ukuran visual bingkai luar (bergantung pada akurasi mask YOLO).
* **Method B**: **Rekomendasi Utama.** Menghitung jarak berdasarkan pitch sekat fisik (slats). Tahan terhadap distorsi perspektif.
* **Method C**: Menggunakan prinsip Homografi / PnP dari 4 titik sudut tray yang terdeteksi.

## Konfigurasi Fisik (Manual)

> Jika Anda sudah menjalankan kalibrasi (bagian di atas), Anda **tidak perlu** mengedit file ini. Nilai-nilai akan dibaca otomatis dari `tray_calibration.yaml`.

Jika ingin override secara manual, edit `tray_detector/config.py`:
```python
P_REAL_CM = 0.69         # Pitch Fisik aktual (jarak sekat ke sekat dalam cm).
THETA_TILT_DEG = 20.0    # Sudut kemiringan kamera (derajat).
```

## Struktur Output (JSON)
Output JSON mencakup:
* `D_tray_cm`: Estimasi jarak akhir (rata-rata atau fusi).
* `D_left_cm` / `D_right_cm`: Jarak spesifik di sisi kiri/kanan gelas (untuk cek kemiringan).
* `confidence`: Skor kepercayaan (0.0 - 1.0).
* `status`: `"OK"` atau `"INSUFFICIENT_DATA"`.
