# 07 MiDaS + ArUco Fusion — Estimasi Tinggi Gelas

Modul *standalone* yang menggabungkan **ArUco Marker** (jarak absolut) dengan **MiDaS** (kedalaman relatif) dan **YOLOv8** (deteksi gelas) untuk mengestimassi tinggi gelas secara geometris tanpa kalibrasi kurva/polinomial.

## Quick Start

### 1. Buat & Aktifkan Conda Environment Baru
```bash
conda env create -f environment_fusion.yaml
conda activate midas-aruco-env
```

### 2. Jalankan Estimasi
```bash
# Mode GUI (PC / Laptop dengan monitor)
python run_fusion.py --camera 0 --marker-size 5.0

# Mode Headless (untuk Kakip tanpa monitor)
python run_fusion.py --camera 0 --headless --marker-size 5.0
```

## Cara Kerja (Asynchronous Dual-Track)

| Sub-sistem | Teknologi | Beban | Frekuensi |
|---|---|---|---|
| **Fast Track** | ArUco Computer Vision | Sangat Ringan < 5ms | 30 FPS (konstan) |
| **Heavy Track** | YOLO + MiDaS | Menengah-Berat | Max 5 FPS (dibatasi) |

Fast Track selalu berjalan untuk mendapatkan `Z_tray` (jarak meja). Heavy Track hanya aktif saat marker dan gelas terbaca bersamaan.

## Argumen

| Argumen | Default | Deskripsi |
|---|---|---|
| `--camera` | 0 | Index kamera |
| `--marker-size` | 5.0 | Ukuran sisi ArUco (cm) |
| `--alpha` | 1.0 | Faktor skala geometri `Z_rim` |
| `--headless` | False | Nonaktifkan GUI (mode Kakip) |

## Prasyarat

- Marker ArUco **harus selalu terlihat** oleh kamera selama estimasi.
- Script ini mengimpor modul dari folder `06_aruco_marker/` dan `midas_volumecup/` di root project.
