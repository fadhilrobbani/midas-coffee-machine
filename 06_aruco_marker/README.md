# 06 ArUco Marker — Distance Estimation Experiment

Eksperimen untuk menguji apakah ArUco marker bisa menggantikan deteksi tray berbasis AI
untuk pengukuran jarak (depth) pada mesin kopi.

## Quick Start

### 1. Setup Environment
```bash
conda activate aruco-experiment
```

### 2. Generate Marker (Print ini di kertas)
```bash
python run_aruco.py --generate-marker
```
File PNG akan tersimpan di `markers/`. Print marker dan **ukur sisi hitamnya** (tanpa border putih).

### 3. Test pada Gambar
```bash
python run_aruco.py --image foto_marker.jpg --marker-size 5.0
```

### 4. Live Camera
```bash
python run_aruco.py --camera 0 --marker-size 5.0 --lock-focus
```
- `--marker-size`: ukuran fisik sisi marker dalam cm (sesuai hasil ukur cetakan)
- `--lock-focus`: kunci fokus kamera (recommended)
- `--focus-value N`: nilai fokus (0 = infinity)
- `--params`: Path ke custom calibration_params.yml (opsional)
- `--output-dir`: Path folder output custom (opsional)
- Kontrol saat live camera:
  - Tekan `q` untuk keluar
  - Tekan `s` untuk screenshot
  - Tekan `r` untuk merekam video (toggle record)

## Struktur File

| File | Deskripsi |
|------|-----------|
| `run_aruco.py` | CLI entry point (image / camera / generate) |
| `aruco_detector.py` | Class `ArucoDetector` dengan pose estimation |
| `generate_marker.py` | Utility generate marker PNG |
| `summarize_reports.py` | Script untuk menggabungkan session report JSON/MD menjadi satu Markdown ringkasan |
| `environment_aruco.yaml` | Conda environment definition |

## Cara Kerja

1. **Deteksi Marker** — `cv2.aruco.detectMarkers()` mencari pola ArUco pada frame
2. **Pose Estimation** — `cv2.aruco.estimatePoseSingleMarkers()` menghitung posisi 3D marker relatif terhadap kamera menggunakan `solvePnP`
3. **Output** — Jarak (cm), rotasi (euler angles), reprojection error
4. **Recording & Reporting** — Sistem dapat menghasilkan video record (melalui shortcut `r`), menyimpan tangkapan layar, dan men-generate session report yang bisa diringkas via `summarize_reports.py`.

## Kalibrasi

Menggunakan `calibration_params.yml` yang sudah ada di project root secara default.
Parameter yang dipakai: `camera_matrix_left` dan `dist_coeff_left`.

## Dictionary ArUco

| Dictionary | Grid | Jumlah ID | Catatan |
|-----------|------|-----------|---------|
| `DICT_4X4_50` | 4×4 | 50 | **Default** — paling tangguh untuk blur/kecil |
| `DICT_5X5_50` | 5×5 | 50 | Lebih unik, butuh resolusi lebih tinggi |
| `DICT_6X6_50` | 6×6 | 50 | Detail tinggi |
