# `libcup_volume` — Cup Volume Estimator Library

> **Konteks untuk AI Agent:** Library ini adalah modul C++ mandiri yang menghitung **volume gelas kopi** (dalam mL) dari frame kamera fisheye. Library ini adalah bagian dari sistem coffee machine vision pipeline. Ia menerima raw fisheye frame + metadata dari pipeline AI (YOLO, ArUco, MiDaS) dan menghasilkan estimasi volume.

---

## Deskripsi Singkat

`libcup_volume.so` adalah shared library C++ yang mengenkapsulasi seluruh logika estimasi volume gelas:

1. **Undistort** frame fisheye menggunakan Moildev (hardcoded: pitch=-15°, zoom=2.0, mode=2)
2. **Deteksi lebar rim** gelas dari strip atas bounding box via Otsu thresholding
3. **Hitung diameter** gelas menggunakan pinhole camera model
4. **Hitung volume** menggunakan model silinder (V = π × r² × h)

Library ini **tidak melakukan** deteksi AI (YOLO/MiDaS/ArUco). Data tersebut harus sudah tersedia dari pipeline upstream pemanggil.

---

## Struktur File Library

```
install_lib/
├── lib/
│   └── libcup_volume.so          ← shared library utama
└── include/
    └── fusion/
        ├── cup_volume_estimator.h ← header utama (satu-satunya yang perlu di-include)
        ├── volume_config.h        ← konstanta hardcoded
        ├── volume_math.h          ← fungsi math pure (opsional)
        └── height_math.h          ← definisi struct BBox (wajib diketahui caller)
```

---

## File Runtime yang Dibutuhkan

Saat program berjalan, pastikan file ini ada di direktori kerja atau path yang disediakan:

| File | Keterangan | Wajib? |
|------|------------|--------|
| `libcup_volume.so` | Library utama | ✅ Ya |
| `camera_parameters.json` | Konfigurasi lensa Moildev | ✅ Ya |
| `weights/moil/libmoildev.a` | Moildev static lib (link saat compile) | ✅ Ya (link time) |

> **Catatan `libmoildev.a`:** Library ini harus di-link secara **terpisah** oleh proyek pemanggil karena tidak di-compile dengan `-fPIC` (sehingga tidak bisa di-embed ke dalam `.so`).

---

## Cara Integrasi ke Proyek C++ Lain

### CMakeLists.txt Proyek Anda

```cmake
cmake_minimum_required(VERSION 3.15)
project(your_project)

# Tambahkan include path library cup_volume
set(CUP_VOLUME_DIR "/path/to/install_lib")

target_include_directories(your_target PUBLIC
    ${CUP_VOLUME_DIR}/include/fusion
)

target_link_libraries(your_target PUBLIC
    ${CUP_VOLUME_DIR}/lib/libcup_volume.so
    /path/to/weights/moil/libmoildev.a   # Moildev harus di-link TERPISAH
    ${OpenCV_LIBS}
)
```

---

## API Reference

### Struct `VolumeInput`

Input yang harus disediakan oleh caller **per-frame**:

```cpp
struct VolumeInput {
    cv::Mat frame;       // Raw fisheye frame (BELUM di-undistort)
    BBox    bbox;        // Bounding box gelas dari YOLO {x1, y1, x2, y2}
    double  h_cup_cm;   // Tinggi gelas dalam cm (dari pipeline MiDaS/ArUco)
    double  z_tray_cm;  // Jarak kamera ke meja/tray via ArUco (cm)
    double  focal_px;   // Focal length efektif dalam piksel
};
```

### Struct `VolumeResult`

Output dari `estimate()`:

```cpp
struct VolumeResult {
    double rim_w_px;    // Lebar rim dalam piksel (debug info)
    double z_rim_cm;    // Jarak kamera ke bibir gelas = z_tray - h_cup (cm)
    double diameter_cm; // Diameter fisik gelas (cm)
    double volume_ml;   // Volume estimasi dalam mL (= cm³)
    bool   valid;       // true jika estimasi berhasil
};
```

### Struct `BBox` (dari `height_math.h`)

```cpp
struct BBox {
    int x1, y1, x2, y2;  // pixel coordinates dari YOLO output
};
```

### Class `CupVolumeEstimator`

```cpp
class CupVolumeEstimator {
public:
    // Konstruktor — init MoilUndistorter sekali di startup
    CupVolumeEstimator(
        const std::string& camera_params_json,  // path ke camera_parameters.json
        const std::string& camera_name,         // nama profil kamera di JSON
        int frame_width  = 2592,                // resolusi stream (default sensor penuh)
        int frame_height = 1944
    );

    // Estimasi volume dari satu frame
    VolumeResult estimate(const VolumeInput& input);

    // Focal length yang sudah disesuaikan dengan Moildev zoom
    // Gunakan ini untuk override ArUco camera matrix
    double adjusted_focal_px() const;

    // Set V4L2 exposure hardcoded (5000) ke VideoCapture
    static void apply_exposure(cv::VideoCapture& cap);

    bool is_ready() const;
};
```

---

## Konfigurasi Hardcoded (Tidak Perlu Diubah)

Semua parameter ini sudah di-hardcode di `volume_config.h` dan sesuai dengan setup fisik kamera yang telah dikalibrasi:

| Parameter | Nilai | Keterangan |
|-----------|-------|------------|
| `MARKER_SIZE_CM` | `2.5` cm | Ukuran fisik sisi ArUco marker |
| `MOIL_ZOOM` | `2.0x` | Hybrid: Moildev 1.5x + digital crop 1.33x |
| `MOIL_MODE` | `2` | AnyPointM2 = Pitch/Yaw/Roll |
| `MOIL_PITCH_DEG` | `-15.0°` | Kamera miring ke bawah |
| `V4L2_EXPOSURE` | `5000` | = smart_exposure 5.0 di Python pipeline |
| Interpolasi | `INTER_LINEAR` | **JANGAN ganti ke CUBIC/LANCZOS** (crash OpenCL) |

---

## Contoh Penggunaan Lengkap

```cpp
#include <fusion/cup_volume_estimator.h>
#include <opencv2/opencv.hpp>

int main() {
    // ── 1. Inisialisasi library (SEKALI di startup) ─────────────────────
    fusion::CupVolumeEstimator estimator(
        "camera_parameters.json",  // path ke JSON Moildev
        "syue_7730v1_6"            // nama profil kamera
        // frame_width=2592, frame_height=1944 (default, sesuai resolusi sensor)
    );

    if (!estimator.is_ready()) {
        std::cerr << "Gagal init estimator!\n";
        return 1;
    }

    // ── 2. Set exposure kamera (opsional, SEKALI setelah open) ──────────
    cv::VideoCapture cap(0);
    cap.set(cv::CAP_PROP_FRAME_WIDTH,  2592);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, 1944);
    fusion::CupVolumeEstimator::apply_exposure(cap);  // V4L2 = 5000

    // ── 3. Ambil focal_px untuk pipeline ArUco Anda ─────────────────────
    // Inject ke ArUco detector agar focal length-nya konsisten dengan Moildev zoom
    double focal_px = estimator.adjusted_focal_px();

    // ── 4. Loop per-frame ────────────────────────────────────────────────
    while (true) {
        cv::Mat raw_frame;
        cap >> raw_frame;
        if (raw_frame.empty()) continue;

        // == Data dari pipeline Anda (YOLO, ArUco, MiDaS) ==
        // Contoh: hasil dari YOLO cup detector
        fusion::BBox bbox;
        bbox.x1 = 800;  // dari YOLO detection
        bbox.y1 = 400;
        bbox.x2 = 1400;
        bbox.y2 = 1400;

        double z_tray_cm = 28.5;   // dari ArUco marker distance
        double h_cup_cm  = 9.5;    // dari MiDaS + height pipeline

        // == Panggil estimator ==
        fusion::VolumeInput in;
        in.frame     = raw_frame;   // ← raw fisheye, library yang undistort
        in.bbox      = bbox;
        in.h_cup_cm  = h_cup_cm;
        in.z_tray_cm = z_tray_cm;
        in.focal_px  = focal_px;    // dari adjusted_focal_px()

        fusion::VolumeResult res = estimator.estimate(in);

        if (res.valid) {
            printf("┌─────────────────────────┐\n");
            printf("│ Volume  : %6.0f mL      │\n", res.volume_ml);
            printf("│ Diameter: %5.1f cm       │\n", res.diameter_cm);
            printf("│ Z_rim   : %5.1f cm       │\n", res.z_rim_cm);
            printf("│ Rim_w   : %5.0f px       │\n", res.rim_w_px);
            printf("└─────────────────────────┘\n");
        } else {
            printf("[Volume] Estimasi tidak valid (pastikan gelas terdeteksi)\n");
        }
    }

    return 0;
}
```

---

## Cara Build Proyek yang Menggunakan Library Ini

```bash
# Install library dulu (dari 08_midas_aruco_fusion_cpp/build):
cd /path/to/08_midas_aruco_fusion_cpp/build
cmake .. -DBUILD_SHARED_VOLUME_LIB=ON -DCMAKE_INSTALL_PREFIX=../../install_lib
cmake --build . --target cup_volume -j$(nproc)
cmake --install .

# Build proyek Anda:
cd /path/to/your_project/build
cmake .. \
  -DCUP_VOLUME_DIR=/path/to/install_lib \
  -DMOILDEV_LIB=/path/to/weights/moil/libmoildev.a
cmake --build . -j$(nproc)
```

---

## Hubungan dengan Pipeline Python (`07_midas_aruco_fusion`)

Library ini adalah port C++ dari fungsi-fungsi di:

| Python (original) | C++ (library ini) |
|---|---|
| `core/volume_math.py` → `measure_rim_width_px()` | `fusion::measure_rim_width_px()` |
| `core/volume_math.py` → `calc_diameter()` | `fusion::calc_diameter()` |
| `core/volume_math.py` → `calc_volume()` | `fusion::calc_volume()` |
| `core/moil_undistorter.py` → `undistort()` | `fusion::MoilUndistorter::undistort()` |
| `run_fusion.py` → blok volume di live pipeline | `fusion::CupVolumeEstimator::estimate()` |

Parameter Moildev yang digunakan di Python dan library ini identik:
```python
# Python (run_fusion.py):
--moil-pitch -15 --moil-zoom 2 --moil-mode 2

# C++ (volume_config.h):
MOIL_PITCH_DEG = -15.0
MOIL_ZOOM      = 2.0
MOIL_MODE      = 2
```

---

## Troubleshooting

| Masalah | Kemungkinan Penyebab | Solusi |
|---------|---------------------|--------|
| `estimator.is_ready()` = false | `camera_parameters.json` tidak ditemukan atau nama profil salah | Pastikan path JSON benar dan nama profil ada di JSON |
| `VolumeResult.valid` = false | `h_cup_cm <= 0` atau `bbox` tidak valid | Pastikan pipeline height dan YOLO sudah menghasilkan data |
| `volume_ml` terlalu besar/kecil | `focal_px` salah | Gunakan `adjusted_focal_px()` dari estimator, jangan hardcode |
| Crash saat link | `libmoildev.a` tidak ter-link | Tambahkan `libmoildev.a` ke `target_link_libraries` proyek Anda |
| Crash saat runtime | `.so` tidak ditemukan | Set `LD_LIBRARY_PATH` atau copy `.so` ke folder binary |

---

## Catatan Penting untuk AI Agent

1. **Library ini TIDAK melakukan deteksi AI** — YOLO, MiDaS, dan ArUco harus dijalankan oleh proyek pemanggil. Library hanya menerima hasilnya.
2. **`raw_frame` yang diberikan ke `estimate()` adalah frame fisheye MENTAH** — library yang akan melakukan undistortion secara internal. Jangan berikan frame yang sudah di-undistort.
3. **`focal_px` harus dari `adjusted_focal_px()`** — nilai ini sudah mempertimbangkan zoom Moildev. Menggunakan focal length kalibrasi awal (tanpa zoom adjustment) akan menghasilkan diameter dan volume yang salah.
4. **Inisialisasi `CupVolumeEstimator` MAHAL** (loads Moildev maps) — lakukan hanya sekali di startup, bukan per-frame.
5. **`libmoildev.a` tidak bisa di-embed ke `.so`** karena tidak di-compile dengan `-fPIC`. Ini keterbatasan bawaan library Moildev pihak ketiga.
