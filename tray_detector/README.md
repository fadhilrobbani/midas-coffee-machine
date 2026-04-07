# Tray Detector Pipeline

Modul `tray_detector` adalah sistem pengukur jarak berbasis visi komputer presisi (Computer Vision) untuk menghitung elevasi/jarak (`D_tray`) dari kamera *overhead* menuju dasar *tray/drip-grate* pada mesin pembuat kopi (seperti Jura). 

Tujuan utamanya adalah menentukan apakah tray berada pada posisi semestinya, miring, atau tidak pada lokasinya dengan resolusi jarak yang sangat akurat.

## Daftar Isi
- [Fitur Utama](#fitur-utama)
- [Prasyarat](#prasyarat)
- [Cara Penggunaan (CLI)](#cara-penggunaan-cli)
- [Pemilihan Metode Deteksi](#pemilihan-metode-deteksi)
- [Konfigurasi Fisik (Kalibrasi)](#konfigurasi-fisik-kalibrasi)
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

## Konfigurasi Fisik (Kalibrasi)
Kualitas pengukuran *sepenuhnya bersandar pada Konstanta Fisik* pada `tray_detector/config.py`.

Untuk mengubah ketepatan ukuran sentimeter keluaran, sesuaikan nilai berikut di **baris 20-23** `config.py`:
```python
P_REAL_CM = 0.69         # Pitch Fisik aktual (jarak sekat ke sekat dalam cm).
F_PIXEL = 662.17         # Focal length kamera.
THETA_TILT_DEG = 20.0    # Sudut kemiringan kamera (derajat).
```

## Struktur Output (JSON)
Output JSON mencakup:
* `D_tray_cm`: Estimasi jarak akhir (rata-rata atau fusi).
* `D_left_cm` / `D_right_cm`: Jarak spesifik di sisi kiri/kanan gelas (untuk cek kemiringan).
* `confidence`: Skor kepercayaan (0.0 - 1.0).
* `status`: `"OK"` atau `"INSUFFICIENT_DATA"`.
