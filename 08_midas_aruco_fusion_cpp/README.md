# MiDaS ArUco Fusion (C++ Edition)

Versi C++ dari pipeline **MiDaS ArUco Fusion** untuk estimasi tinggi dan volume gelas secara real-time. Porting ini difokuskan pada peningkatan performa (FPS), arsitektur *multi-threading* yang *lock-free*, dan integrasi langsung dengan AI via ONNX Runtime C++ API.

---

## 🚀 Fitur Utama

1. **Performa Tinggi (Zero-Copy Pipeline)**
   Arsitektur 3-stage thread (Kamera → Proses → MiDaS) yang dihubungkan melalui *lock-free ring buffer*. Hal ini mencegah antarmuka GUI atau tangkapan kamera mengalami *bottleneck* dari inferensi AI.
2. **Inferensi AI Asinkron**
   Depth estimation (MiDaS) dan Object Detection (YOLO) dijalankan secara asinkron menggunakan **ONNX Runtime C++ API**.
3. **Fisheye Undistortion (Moildev)**
   Transformasi gambar *fisheye* ke proyeksi *equidistant* secara efisien menggunakan `cv::remap` dengan dukungan AnyPoint controller (Pitch, Yaw, Roll, Zoom).
4. **7 Mode Kalibrasi Lanjutan**
   Tersedia 7 mode penghitungan matematika geometri dan polinomial yang canggih untuk estimasi tinggi (dari mode 1-Titik sederhana hingga *Bilateral Z-Grid* dan *Analytic Geometry*).
5. **Session Reporting**
   Secara otomatis menyimpan data pengukuran ke dalam format `JSON`, `Markdown`, dan grafik `PNG`.

---

## 🛠️ Persyaratan Sistem (Dependencies)

Aplikasi ini dikembangkan dan diuji pada sistem **CachyOS (Arch Linux)**.
Berikut adalah dependensi yang dibutuhkan:

- **Compiler**: C++17 atau lebih baru
- **Build System**: CMake (>= 3.15) & Ninja
- **Computer Vision**: OpenCV 4.x (termasuk modul aruco, dnn, dll)
- **GUI (Opsional tapi direkomendasikan)**: gtkmm3
- **AI Inference (Opsional tapi direkomendasikan)**: ONNX Runtime
- **JSON Parser**: nlohmann/json (Ter-download otomatis via CMake FetchContent)
- **CLI Parser**: CLI11 (Ter-download otomatis via CMake FetchContent)

---

## 📦 Cara Instalasi & Kompilasi

### 1. Instalasi Library di Arch Linux / CachyOS
Buka terminal dan jalankan perintah berikut untuk menginstal seluruh dependensi:
```bash
sudo pacman -S base-devel cmake ninja opencv gtkmm3 onnxruntime
```

### 2. Kompilasi Proyek
Masuk ke dalam folder proyek dan lakukan *build* menggunakan CMake dan Ninja:
```bash
cd 08_midas_aruco_fusion_cpp
mkdir -p build && cd build
cmake .. -G Ninja -DCMAKE_BUILD_TYPE=Release
ninja -j$(nproc)
```

> **Catatan Modul Opsional:**
> CMake secara otomatis mendeteksi keberadaan `gtkmm3` dan `onnxruntime`.
> - Jika `gtkmm3` tidak terinstal, aplikasi akan berjalan dalam mode *Headless* (CLI).
> - Jika `onnxruntime` tidak terinstal, model MiDaS dan YOLO tidak akan dieksekusi, tapi perhitungan matematika tetap berjalan menggunakan nilai fallback.

---

## 💻 Panduan Penggunaan

Aplikasi dieksekusi melalui terminal. Terdapat beberapa argumen (CLI flags) yang bisa digunakan untuk mengkonfigurasi pipeline.

### Menjalankan Versi Penuh (GUI + AI aktif)
Pastikan Anda berada di dalam folder `build`, lalu jalankan:

```bash
./fusion_app \
    --camera 0 \
    --midas ../../weights/midas_v21_small_256.onnx \
    --yolo ../../weights/cup_detection_v3_12_s_best.onnx \
    --calib calibration.json
```

### Menjalankan Tanpa Moildev (Kamera Standar)
Jika Anda menggunakan webcam standar (bukan fisheye), nonaktifkan Moildev dengan flag `--no-moil`:
```bash
./fusion_app --camera 0 --no-moil
```

### Menjalankan Mode Headless (Hanya Terminal)
Cocok untuk perangkat IoT yang tidak memiliki server tampilan (X11/Wayland):
```bash
./fusion_app --camera 0 --headless
```

### Opsi CLI Lengkap
Untuk melihat seluruh argumen yang didukung:
```bash
./fusion_app --help
```

---

## 🧪 Menjalankan Unit Tests (TDD)

Proyek ini dibangun menggunakan pendekatan *Test-Driven Development (TDD)* dengan `GoogleTest`. Kami menjamin 102 test lulus untuk memastikan paritas 100% dengan versi Python aslinya.

Untuk menjalankan seluruh *test suite*:
```bash
cd build
ctest --output-on-failure -j$(nproc)
```

---

## 🏗️ Struktur Folder Utama

- `src/`: Berisi kode sumber C++ utama (Pipeline, GUI, Math, Detectors).
- `tests/`: Kumpulan Unit Test dengan framework GoogleTest.
- `CMakeLists.txt`: Konfigurasi *build* yang dimodularisasi.
- `calibration.json`: File JSON (opsional) yang menyimpan state mode kalibrasi terakhir Anda.
