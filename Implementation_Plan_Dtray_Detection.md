# Implementation Plan — Pipeline Deteksi Jarak Kamera ke Tray
**Mesin Kopi Jura — Computer Vision Research Division**

| Versi | Status | Kategori | Target Platform |
|-------|--------|----------|-----------------|
| 1.0 | Draft | Computer Vision | Embedded / Edge |

---

## Daftar Isi
1. [Ringkasan Eksekutif](#1-ringkasan-eksekutif)
2. [Prasyarat & Persiapan](#2-prasyarat--persiapan)
3. [Implementasi Metode A — Apparent Width Tray](#3-implementasi-metode-a--apparent-width-tray)
4. [Implementasi Metode B — Horizontal Slat Pitch](#4-implementasi-metode-b--horizontal-slat-pitch)
5. [Implementasi Metode C — Homografi 4 Corner + PnP](#5-implementasi-metode-c--homografi-4-corner--pnp)
6. [Fusi Metode & Hierarki Eksekusi](#6-fusi-metode--hierarki-eksekusi)
7. [Rencana Kerja & Timeline](#7-rencana-kerja--timeline)
8. [Manajemen Risiko](#8-manajemen-risiko)
9. [Kriteria Penerimaan](#9-kriteria-penerimaan-acceptance-criteria)
10. [Approval & Sign-Off](#10-approval--sign-off)

---

## 1. Ringkasan Eksekutif

Pipeline menggunakan tiga metode computer vision yang berjalan secara hierarkis untuk memastikan robustness dan akurasi estimasi jarak dalam berbagai kondisi runtime.

### 1.1 Tujuan

- Mengimplementasikan sistem estimasi jarak kamera-ke-tray yang akurat dan robust
- Mendukung tiga metode deteksi (A, B, C) dengan fallback hierarkis
- Menghasilkan output `D_tray_cm` yang dapat diandalkan untuk kontrol nozzle mesin kopi
- Memastikan performa real-time pada hardware embedded

### 1.2 Tiga Metode Inti

| Metode | Nama | Dependensi | Akurasi | Prioritas |
|--------|------|------------|---------|-----------|
| A | Apparent Width Tray | Bounding box YOLO saja | Sedang | Fallback (Last Resort) |
| B | Horizontal Slat Pitch | Hough Lines di ROI tray | Tinggi | **UTAMA (Primary)** |
| C | Homografi 4 Corner + PnP | 4 corner tray visible | Sangat Tinggi | Backup Presisi |

### 1.3 Kondisi Runtime & Strategi Eksekusi

| Kondisi Runtime | Metode Aktif |
|----------------|--------------|
| Tray terdeteksi, sekat horizontal jelas | B utama + A sebagai cross-check |
| Sekat horizontal tidak cukup (< 3 garis) | C jika 4 corner visible, atau A |
| Gelas besar menutupi sebagian besar tray | C dari corner yang tersisa |
| Hanya bounding box tray yang tersedia | A saja sebagai last resort |
| Tidak ada data sama sekali | `INSUFFICIENT_DATA` — tidak output |

> **Prasyarat untuk semua metode:** frame sudah di-undistort menggunakan `K` dan `dist_coeffs` dari kalibrasi pabrik. Tanpa undistort, semua metode akan menghasilkan error sistematis.

---

## 2. Prasyarat & Persiapan

### 2.1 Kalibrasi Kamera (Dilakukan di Pabrik)

> Semua konstanta berikut diukur **SATU KALI** di lab/pabrik kemudian di-hardcode ke firmware. User tidak perlu melakukan pengukuran ulang.

| Konstanta | Cara Mengukur | Dipakai di |
|-----------|--------------|------------|
| `f_pixel` (focal length) | `cv2.calibrateCamera()` dengan checkerboard | Metode A, B, C |
| `dist_coeffs` (distorsi lensa) | `cv2.calibrateCamera()` dengan checkerboard | A, B, C (undistort) |
| `P_real_cm` (pitch antar sekat) | Kaliper: tengah sekat ke sekat berikutnya | Metode B |
| `W_tray_cm` (lebar tray) | Kaliper / penggaris, arah pendek tray | Metode A, C |
| `L_tray_cm` (panjang tray) | Kaliper / penggaris, arah panjang tray | Metode C |
| `theta_tilt_deg` (sudut kamera) | Inclinometer app atau dari homografi tray | Metode A, B, C |

### 2.2 Template `config.py`

```python
import numpy as np

# ── Kalibrasi kamera (dari calibrateCamera di pabrik) ───────────────
CAMERA_MATRIX = np.array([
    [f_x,  0,  cx],
    [  0, f_y,  cy],
    [  0,   0,   1]
], dtype=np.float64)

DIST_COEFFS = np.array([k1, k2, p1, p2, k3], dtype=np.float64)

# ── Dimensi fisik tray (ukur dari unit Jura) ─────────────────────────
P_REAL_CM      = 0.8    # jarak antar sekat horizontal (cm)
W_TRAY_CM      = 12.5   # lebar tray (cm)
L_TRAY_CM      = 22.0   # panjang tray (cm)
THETA_TILT_DEG = 20.0   # sudut condong kamera dari vertikal
```

### 2.3 Dependensi Software

| Library | Versi Minimum | Kegunaan | Instalasi |
|---------|--------------|----------|-----------|
| OpenCV (`cv2`) | 4.5+ | undistort, Canny, HoughLinesP, solvePnP | `pip install opencv-python` |
| NumPy | 1.21+ | array ops, IQR filtering, median | `pip install numpy` |
| YOLOv8 (`ultralytics`) | 8.0+ | deteksi tray + segmentasi mask | `pip install ultralytics` |
| `math` (stdlib) | — | `cos()`, trigonometri | Built-in Python |

---

## 3. Implementasi Metode A — Apparent Width Tray

> 🔴 **FALLBACK — Last resort jika metode lain gagal**

### 3.1 Prinsip & Formula

Memanfaatkan hubungan perspektif antara lebar fisik tray yang diketahui dan lebar tray dalam piksel. Semakin jauh tray dari kamera, semakin kecil tray terlihat di frame.

```
D_tray = (f_pixel × W_real_cm) / W_pixel
```

| Variabel | Deskripsi | Sumber |
|----------|-----------|--------|
| `f_pixel` | Focal length kamera dalam piksel | Hardcode dari kalibrasi pabrik |
| `W_real_cm` | Lebar fisik tray Jura dalam cm | Diukur sekali dari unit fisik |
| `W_pixel` | Lebar bounding box tray di frame (`x2 - x1`) | Output YOLOv8-seg per frame |
| `D_tray` | Jarak vertikal kamera ke tray dalam cm | Hasil kalkulasi |

### 3.2 Asumsi & Limitasi

- **Asumsi:** kamera melihat tray dari atas tegak lurus — lebar yang terlihat adalah lebar sebenarnya
- **Limitasi:** kamera condong (`theta_tilt`) membuat lebar proyeksi sedikit lebih kecil dari lebar asli
- **Koreksi:** tambahkan faktor `1/cos(theta_tilt)` pada `W_pixel` untuk kompensasi sudut pandang
- **Akurasi turun** jika tray terpotong di tepi frame — bounding box tidak merepresentasikan lebar penuh

### 3.3 Pipeline Implementasi

| Step | Aksi | Detail |
|------|------|--------|
| 1 | Undistort frame | `cv2.undistort(frame, K, dist_coeffs)` |
| 2 | YOLO inference | Dapatkan bounding box tray: `[x1, y1, x2, y2]` |
| 3 | Hitung W_pixel | `W_pixel = x2 - x1` |
| 4 | Validasi edge | Pastikan `x1 > 5` dan `x2 < frame_width - 5` |
| 5 | Kalkulasi D_tray | `D_raw = (f_pixel × W_real_cm) / W_pixel`, lalu `D_tray = D_raw × cos(theta_tilt)` |
| 6 | Validasi range | `D_tray` harus dalam `[5.0, 40.0]` cm |

### 3.4 Kode Implementasi

```python
def estimate_D_tray_method_A(bbox, f_pixel, W_real_cm, theta_tilt_rad):
    x1, y1, x2, y2 = bbox
    W_pixel = x2 - x1

    if W_pixel < 20:
        return None  # bounding box terlalu kecil

    D_raw   = (f_pixel * W_real_cm) / W_pixel
    D_tray  = D_raw * math.cos(theta_tilt_rad)

    return round(D_tray, 2) if 5.0 <= D_tray <= 40.0 else None
```

### 3.5 Confidence Scoring

| Kondisi | Confidence Range |
|---------|-----------------|
| Bounding box penuh, tidak terpotong frame | 0.50 – 0.65 |
| Bounding box mepet tepi frame (< 10px) | 0.20 – 0.35 |
| `D_tray` di luar range 5–40 cm | 0.00 |

---

## 4. Implementasi Metode B — Horizontal Slat Pitch

> 🟢 **METODE UTAMA — Paling robust, digunakan sebagai primary**

### 4.1 Prinsip & Keunggulan

Sekat horizontal tray yang sejajar di dunia nyata akan terproyeksi ke kamera dengan jarak (pitch) yang berbeda-beda tergantung jarak ke kamera. Semakin jauh tray, semakin rapat proyeksi sekat di frame.

Sistem ini bersifat **overdetermined**: semakin banyak sekat terdeteksi, semakin akurat estimasinya karena menggunakan median dari banyak pengukuran.

### 4.2 Formula

```
D_tray = (f_pixel × P_real_cm × cos(theta_tilt_rad)) / p_avg_pixel
```

| Variabel | Deskripsi | Sumber |
|----------|-----------|--------|
| `f_pixel` | Focal length kamera dalam piksel | Hardcode kalibrasi pabrik |
| `P_real_cm` | Jarak fisik antar sekat horizontal dalam cm | Diukur dari tray fisik |
| `theta_tilt_rad` | Sudut condong kamera dari vertikal dalam radian | Hardcode dari mounting kamera |
| `p_avg_pixel` | Median jarak antar sekat di frame dalam piksel | Hough Lines + median per zona |
| `D_tray` | Jarak vertikal kamera ke tray dalam cm | Hasil kalkulasi |

### 4.3 Logika Split ROI — Mengatasi Oklusi Gelas

Gelas menutupi area tengah tray. Sistem membagi area tray menjadi dua zona independen:

| Zona | Kolom Frame | Kondisi |
|------|-------------|---------|
| Kiri | `0` hingga `glass_x1 - 10px` | Area sekat di kiri gelas |
| Kanan | `glass_x2 + 10px` hingga `frame_width` | Area sekat di kanan gelas |
| Tanpa gelas | Kiri = separuh kiri, Kanan = separuh kanan | Saat tray kosong |

> Setiap zona membutuhkan **minimal 3 garis horizontal valid**. Jika hanya satu zona yang memenuhi, status `SINGLE_ZONE` dengan confidence lebih rendah.

### 4.4 Algoritma IQR Filtering

Menggunakan median (bukan mean) untuk robustness terhadap garis palsu dari noise atau bayangan:

```python
# 1. Urutkan y-coordinate garis dari atas ke bawah
y_sorted = sorted([(y1 + y2) / 2 for each line])

# 2. Hitung jarak antar garis berurutan
gaps = np.diff(y_sorted)

# 3. Buang outlier dengan IQR
q1, q3 = np.percentile(gaps, [25, 75])
iqr     = q3 - q1
valid   = gaps[(gaps >= q1 - 1.5 * iqr) & (gaps <= q3 + 1.5 * iqr)]

# 4. Median dari gap yang valid
p_avg = np.median(valid)  # dalam piksel
```

### 4.5 Pipeline Implementasi

| Step | Aksi | Detail |
|------|------|--------|
| 1 | Undistort frame | `cv2.undistort(frame, K, dist_coeffs)` |
| 2 | YOLO inference | Dapatkan mask tray (H×W binary) dan bbox gelas `[x1,y1,x2,y2]` |
| 3 | Validasi mask | `np.count_nonzero(mask) > 500 px` |
| 4 | Apply mask ke frame | `roi = cv2.bitwise_and(frame, frame, mask=tray_mask)` |
| 5 | Edge detection | `gray → GaussianBlur(5,5) → Canny(30, 100)` |
| 6 | Hough Lines | `HoughLinesP(edges, rho=1, theta=π/180, threshold=50, minLineLength=40, maxLineGap=10)` |
| 7 | Filter horizontal | Pertahankan garis dengan angle < 10° dari horizontal |
| 8 | Split ROI | Pisahkan garis ke zona kiri dan kanan berdasarkan `glass_bbox` |
| 9 | Validasi per zona | Minimal 3 garis per zona — tandai `UNRELIABLE` jika kurang |
| 10 | Hitung pitch median | `gaps = diff(y_sorted)` → IQR filter → `p_avg = median(valid_gaps)` |
| 11 | Kalkulasi D per zona | `D_zone = (f_pixel × P_real_cm × cos(theta_tilt_rad)) / p_avg` |
| 12 | Fusi zona | Kedua reliabel: `mean(D_left, D_right)` \| Satu: gunakan yang ada \| Nihil: `INSUFFICIENT_DATA` |
| 13 | Validasi range | `D_tray` dalam `[5.0, 40.0]` cm — jika tidak: `OUT_OF_RANGE` |

### 4.6 Confidence Scoring

| Kondisi | Confidence Range |
|---------|-----------------|
| Kedua zona valid, 5+ garis masing-masing | 0.90 – 1.00 |
| Kedua zona valid, 3–4 garis masing-masing | 0.70 – 0.89 |
| Satu zona saja, 5+ garis | 0.50 – 0.69 |
| Satu zona saja, 3–4 garis | 0.30 – 0.49 |
| `INSUFFICIENT_DATA` atau `OUT_OF_RANGE` | 0.00 |

---

## 5. Implementasi Metode C — Homografi 4 Corner + PnP

> 🟣 **BACKUP PRESISI — Akurasi tertinggi jika 4 corner terlihat**

### 5.1 Prinsip

Menggunakan 4 titik sudut tray sebagai correspondences antara koordinat 2D di frame dan koordinat 3D dunia nyata. Solver PnP (Perspective-n-Point) menghitung pose kamera secara penuh (rotasi R dan translasi T), dari mana jarak kamera ke tray didapat langsung dari komponen translasi.

- **Keunggulan:** menghasilkan pose 6DoF lengkap (posisi XYZ + rotasi), memungkinkan koreksi perspektif sempurna
- **Keterbatasan:** membutuhkan keempat corner tray terlihat di frame — bisa gagal saat nozzle posisi sangat rendah

### 5.2 Sistem Koordinat Dunia

| Titik | Koordinat Dunia (cm) | Posisi di Tray |
|-------|---------------------|----------------|
| P1 — corner kiri atas | `(0, 0, 0)` | Sudut kiri atas tray |
| P2 — corner kanan atas | `(W_tray, 0, 0)` | Sudut kanan atas tray |
| P3 — corner kanan bawah | `(W_tray, L_tray, 0)` | Sudut kanan bawah tray |
| P4 — corner kiri bawah | `(0, L_tray, 0)` | Sudut kiri bawah tray |

### 5.3 Formula

```
D_tray = |T[2]| × cos(theta_tilt_rad)
```

`T` adalah translation vector hasil `solvePnP`. `T[2]` merepresentasikan jarak sepanjang optical axis kamera.

### 5.4 Pipeline Implementasi

| Step | Aksi | Detail |
|------|------|--------|
| 1 | Undistort frame | `cv2.undistort(frame, K, dist_coeffs)` |
| 2 | YOLO inference | Dapatkan mask tray (H×W binary) dari YOLOv8-seg |
| 3 | Ekstrak contour | `findContours → approxPolyDP → validasi 4 titik` |
| 4 | Validasi 4 corner | Harus tepat 4 titik — jika tidak, fallback ke Metode B |
| 5 | Urutkan corner | Urutan: kiri-atas, kanan-atas, kanan-bawah, kiri-bawah (clockwise) |
| 6 | Definisi object points | 3D world coords: `(0,0,0), (W,0,0), (W,L,0), (0,L,0)` |
| 7 | solvePnP | `cv2.solvePnP(obj_pts, img_pts, K, dist)` → `rvec, tvec` |
| 8 | Ekstrak D_tray | `D_tray = abs(tvec[2][0]) × cos(theta_tilt_rad)` |
| 9 | Validasi range | `D_tray` dalam `[5.0, 40.0]` cm |

### 5.5 Kode Implementasi

```python
def estimate_D_tray_method_C(tray_mask, K, dist_coeffs,
                              W_tray_cm, L_tray_cm, theta_tilt_rad):
    # Ekstrak corner
    mask_u8 = (tray_mask > 0.5).astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    cnt   = max(contours, key=cv2.contourArea)
    approx = cv2.approxPolyDP(cnt, 0.02 * cv2.arcLength(cnt, True), True)
    if len(approx) != 4:
        return None

    # Sort corners: TL, TR, BR, BL
    pts   = approx.reshape(4, 2).astype(np.float32)
    srt   = pts[np.argsort(pts[:, 0])]
    left  = srt[:2][np.argsort(srt[:2, 1])]   # TL, BL
    right = srt[2:][np.argsort(srt[2:, 1])]   # TR, BR
    img_pts = np.array([left[0], right[0], right[1], left[1]], np.float32)

    # World points (Z=0 di permukaan tray)
    W, L = W_tray_cm, L_tray_cm
    obj_pts = np.array([[0,0,0],[W,0,0],[W,L,0],[0,L,0]], np.float32)

    # PnP solve
    ok, rvec, tvec = cv2.solvePnP(obj_pts, img_pts, K, dist_coeffs)
    if not ok:
        return None

    D_raw  = abs(float(tvec[2]))
    D_tray = D_raw * math.cos(theta_tilt_rad)
    return round(D_tray, 2) if 5.0 <= D_tray <= 40.0 else None
```

### 5.6 Confidence Scoring

| Kondisi | Confidence Range |
|---------|-----------------|
| 4 corner jelas, reprojection error < 2px | 0.92 – 1.00 |
| 4 corner terdeteksi, error 2–5px | 0.75 – 0.91 |
| 4 corner terdeteksi, error > 5px | 0.50 – 0.74 |
| Kurang dari 4 corner — fallback ke B | N/A (tidak digunakan) |

---

## 6. Fusi Metode & Hierarki Eksekusi

### 6.1 Hierarki Prioritas per Frame

| Prioritas | Kondisi | Metode Dipakai | Confidence Range |
|-----------|---------|----------------|-----------------|
| 1 (tertinggi) | 4 corner visible + Hough Lines cukup | C untuk validasi, B sebagai primary | 0.85 – 1.00 |
| 2 | Hough Lines cukup, corner tidak lengkap | B saja | 0.30 – 1.00 |
| 3 | Hough tidak cukup, 4 corner ada | C saja | 0.50 – 1.00 |
| 4 (terendah) | Hanya bounding box tersedia | A saja | 0.20 – 0.65 |
| Gagal | Tidak ada data valid | `INSUFFICIENT_DATA` | 0.00 |

### 6.2 Formula Fusi Weighted Average

Jika lebih dari satu metode menghasilkan nilai valid, fusi menggunakan weighted average berdasarkan confidence:

```
D_tray_final = (D_B × conf_B + D_C × conf_C) / (conf_B + conf_C)
```

> Metode A **tidak** diikutkan dalam fusi jika B atau C tersedia — akurasinya terlalu jauh di bawah untuk di-average.

### 6.3 Output Schema

| Field | Tipe | Deskripsi |
|-------|------|-----------|
| `D_tray_cm` | `float \| null` | Jarak vertikal kamera ke tray dalam cm |
| `method_used` | `string` | `A`, `B`, `C`, atau `B+C` (fusi) |
| `confidence` | `float 0–1` | Skor kepercayaan hasil |
| `status` | `string` | `OK` / `SINGLE_ZONE` / `INSUFFICIENT_DATA` / `OUT_OF_RANGE` |
| `D_left_cm` | `float \| null` | D_tray dari zona kiri (Metode B) |
| `D_right_cm` | `float \| null` | D_tray dari zona kanan (Metode B) |
| `lines_left` | `int` | Jumlah sekat valid zona kiri |
| `lines_right` | `int` | Jumlah sekat valid zona kanan |
| `notes` | `string \| null` | Pesan error atau warning jika ada |

---

## 7. Rencana Kerja & Timeline

### 7.1 Fase Implementasi

| Fase | Aktivitas | Deliverable | Estimasi Durasi |
|------|-----------|-------------|-----------------|
| **Fase 0 — Setup** | Kalibrasi kamera, pengukuran fisik tray, setup `config.py` | `config.py` + checklist kalibrasi | 2–3 hari |
| **Fase 1 — Metode A** | Implementasi `estimate_D_tray_method_A()`, unit test | `method_a.py` + test suite | 2–3 hari |
| **Fase 2 — Metode B** | Pipeline 13 langkah: split ROI, IQR filtering, fusi zona | `method_b.py` + test suite | 5–7 hari |
| **Fase 3 — Metode C** | solvePnP pipeline, corner extraction, validasi reprojection error | `method_c.py` + test suite | 3–4 hari |
| **Fase 4 — Fusi & Hierarki** | Logika hierarki, weighted average fusion, output schema | `pipeline.py` (main) | 3–4 hari |
| **Fase 5 — Integrasi & Tuning** | Integrasi dengan YOLO, fine-tune threshold, stress test | `integrated_pipeline.py` | 5–7 hari |
| **Fase 6 — Validasi Lapangan** | Pengujian di unit Jura fisik, berbagai kondisi gelas dan jarak | Laporan validasi + sign-off | 3–5 hari |

**Total estimasi: 23–33 hari kerja**

### 7.2 Checklist Pengujian

#### Metode A
- [ ] Uji dengan bounding box berbagai ukuran (dekat, sedang, jauh)
- [ ] Edge case: tray terpotong di tepi frame
- [ ] Verifikasi confidence score sesuai kondisi
- [ ] Test dengan `theta_tilt` berbeda

#### Metode B
- [ ] Uji dengan tray kosong (tanpa gelas)
- [ ] Uji dengan gelas di berbagai posisi (kiri, tengah, kanan, sangat besar)
- [ ] Validasi IQR filtering membuang garis noise
- [ ] Uji skenario `SINGLE_ZONE` — hanya satu zona valid
- [ ] Verifikasi minimal 3 garis per zona
- [ ] Uji dengan pencahayaan berbeda (siang, redup, backlit)

#### Metode C
- [ ] Uji dengan 4 corner terlihat penuh
- [ ] Edge case: nozzle sangat rendah, corner atas terpotong
- [ ] Ukur reprojection error dan validasi confidence threshold
- [ ] Verifikasi corner sorting clockwise benar

#### Fusi & Pipeline Keseluruhan
- [ ] Test skenario fallback A → B → C
- [ ] Verifikasi weighted average menghasilkan nilai yang masuk akal
- [ ] Test skenario `INSUFFICIENT_DATA` — tidak ada data sama sekali
- [ ] Benchmarking performa: pipeline berjalan < 100ms per frame

---

## 8. Manajemen Risiko

| Risiko | Dampak | Mitigasi |
|--------|--------|----------|
| Kalibrasi kamera tidak akurat | 🔴 Tinggi — error sistematis semua metode | Kalibrasi ulang dengan checkerboard, validasi reprojection error < 0.5px |
| YOLO gagal deteksi tray | 🔴 Tinggi — tidak ada input untuk semua metode | Confidence threshold YOLO > 0.7, alert jika tray tidak terdeteksi > 3 frame |
| Pencahayaan buruk merusak Hough Lines | 🟡 Sedang — Metode B tidak bisa digunakan | Adaptive Canny threshold, fallback otomatis ke Metode C atau A |
| Gelas menutupi semua sekat (tray penuh) | 🟡 Sedang — Metode B `INSUFFICIENT_DATA` | Fallback ke Metode C, atau A jika corner tidak terlihat |
| Corner terpotong frame (nozzle rendah) | 🟡 Sedang — Metode C tidak bisa digunakan | Fallback otomatis ke Metode B |
| Performa lambat di embedded hardware | 🔴 Tinggi — tidak real-time | Optimalkan resolusi input, gunakan YOLO-nano, skip Metode C jika conf B > 0.85 |
| `theta_tilt` berubah karena getaran/aging | 🟡 Sedang — error sistematik semua metode | Tambahkan auto-calibration rutin berdasarkan homografi tray |

---

## 9. Kriteria Penerimaan (Acceptance Criteria)

### 9.1 Akurasi
- Metode B: error rata-rata **< 2 cm** pada jarak 10–35 cm dengan minimum 3 garis per zona
- Metode C: error rata-rata **< 1 cm** pada jarak 10–35 cm dengan 4 corner terlihat jelas
- Metode A: error rata-rata **< 5 cm** pada jarak 10–35 cm dengan bounding box tidak terpotong
- Fusi B+C: error rata-rata **< 1.5 cm**

### 9.2 Robustness
- Pipeline tidak crash pada kondisi: tray terpotong sebagian, gelas sangat besar, pencahayaan redup
- Fallback antar metode berjalan otomatis tanpa intervensi manual
- Status output selalu konsisten (`OK` / `SINGLE_ZONE` / `INSUFFICIENT_DATA` / `OUT_OF_RANGE`)

### 9.3 Performa
- Total latency pipeline **< 100ms** per frame pada target hardware
- YOLO inference sudah termasuk dalam budget 100ms
- Memory footprint **< 500MB** termasuk model YOLO

### 9.4 Integrasi
- Output schema `D_tray_cm`, `method_used`, `confidence`, `status` terdefinisi dengan benar
- Unit test coverage **> 80%** untuk semua fungsi kalkulasi
- Logging tersedia untuk debugging (setiap keputusan fallback tercatat)

---

## 10. Approval & Sign-Off

| Peran | Nama | Tanda Tangan | Tanggal |
|-------|------|--------------|---------|
| Penulis Dokumen | | | |
| Tech Lead / Reviewer | | | |
| QA / Validation | | | |
| Project Manager | | | |

---

*— End of Document — v1.0 | CONFIDENTIAL — Internal Use Only*
