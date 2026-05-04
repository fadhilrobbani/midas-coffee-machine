# 07 MiDaS + ArUco Fusion — Estimasi Tinggi Gelas

Modul *standalone* yang menggabungkan **ArUco Marker** (jarak absolut), **MiDaS** (kedalaman relatif), dan **YOLOv8** (deteksi multi-gelas) untuk mengestimasi tinggi gelas secara geometris. Sistem terbaru ini dilengkapi dengan penyimpanan menu profil (*Menu-Driven*), kompensasi lensa *Fisheye*, serta pelacakan *Multi-Cup* secara simultan.

## Prasyarat Lingkungan

```bash
conda env create -f environment_fusion.yaml
conda activate midas-aruco-env
```

## Alur Penggunaan (Workflow)

Sistem dirancang untuk beroperasi di pabrik dalam 3 fase utama:

### 1. Kalibrasi Lensa Fisheye (Khusus Kamera Baru / Sekali Saja)
Jika memakai kamera wide-angle/Fisheye, jarak yang terbaca akan mengerut dan jauh. Gunakan *auto-focal checkerboard* ini untuk mengukur *focal length* aslinya serta membuang kurva cembungnya:

```bash
python calibrate_fisheye.py --camera 0
```
- Arahkan kamera ke gambar papan catur (*Checkerboard*).
- Tekan secara berulang tombol **`SPASI`** tiap kali sudut kedeteksi (idealnya 10-15 pose yang berbeda).
- Tekan **`C`** untuk memproses. Parameter kamera akan tersimpan kuat di berkas `focal_length_calibration.yaml`. 

### 2. Pendaftaran Profil Mangkuk (Kalibrasi Mode 5)
Latih program di mana posisi aman gelas berukuran tertentu (misal: menu gelas `7.6` cm). Program akan merekam persentase *clipping* kedalaman secara otomatis (*PolyFit*).

```bash
python run_fusion.py --camera 0 --fisheye --calibrate 5 --n-positions 3 --true-height 7.6
```
- Gerakkan moncong wadah secara bertahap `n` kali ikuti instruksi yang tertulis di layar HUD kamera.
- Database akan disimpan langsung secara aman ke `calibration_fisheye_default.json`. (Ulangi perintah di atas untuk gelas ke-2 dengan `--true-height 10.1` dsb.).

### 3. Mode Operasional (Live)
Fase *Deployment*! Mode deteksi performa tinggi (*Fast Track* & *Heavy Track*) tanpa jeda untuk melihat hingga 2 gelas sekaligus!

```bash
python run_fusion.py --camera 0 --fisheye --target-cup 7.6
```
- Program otomatis membuka algoritma gelas berbasis referensi ukuran 7.6 cm.
- `S`: Tembak Tangkapan Layar *(Screenshot)*.
- `R`: Toggle Rekam / Matikan Video.
- *Status Teks*: `Z_tray` (Jarak meja ke kamera), `Z_rim` (Prediksi jarak bibir gelas), dan Tinggi Bersih Gelas (dalam sentimeter).

---

## Daftar Argumen Lengkap (`run_fusion.py`)

| Argumen | Default | Deskripsi Instruksi |
|---|---|---|
| `--camera` | `0` | Kode *port* kamera video |
| `--marker-size` | `5.0` | Sisi ArUco di meja (sentimeter) |
| `--calibrate` | `0` | Isi angka `5` untuk membuat profil kalibrasi |
| `--true-height` | `None` | (Kalibrasi) Masukkan tinggi fisik gelas aslinya |
| `--target-cup` | `None` | (Produksi Live) Ukuran referensi *Cup* mana yang ditarik |
| `--cup-profile` | `default` | Nama profil simpanan (misal `--cup-profile mesinB`) |
| `--fisheye` | `False` | Tarik `focal_length_calibration.yaml` untuk meratakan gambar |
| `--n-positions` | `3` | Hitungan fase titik berhenti (*Z-Grid*) yang harus dipelajari |
| `--headless` | `False` | Sembunyikan *Window* saat mesin ditanam di `Kakip RZ/V2H` |

## Hasil Akhir Perjalanan (Automatic Session Report)
Setelah menekan tombol **`Q`** atau mematikannya di terminal (`Ctrl+C`), ia akan mengenerate folder baru secara otomatis di bawah direktori `results/report/YYYY-MM-DD_HH-MM-SS/`:
- Menghasilkan gambar Grafik Ketinggian Multi-Gelas (`session_chart.png`).
- Mengenerate ringkasan ketepatan simpangan AI / varians deviasi (`report.md`).
- Mencadangkan *Log* kasar di `session_data.json` persis pada masing-masing iterasi frame.
