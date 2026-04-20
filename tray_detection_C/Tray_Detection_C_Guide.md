# Tray Detection C++ — System Guide

Versi C++ dari modul `tray_detector` Python, dioptimalkan untuk deployment di **PC** dan **Renesas RZ/V2H (Kakip)**.

## Daftar Isi
- [Prasyarat](#prasyarat)
- [Build untuk PC](#build-untuk-pc)
- [Build untuk Renesas RZ/V2H (Cross-Compile)](#build-untuk-renesas-rzv2h-cross-compile)
- [Cara Penggunaan](#cara-penggunaan)
- [Arsitektur Detector (YOLO)](#arsitektur-detector-yolo)
- [Catatan untuk RZ/V2H](#catatan-untuk-rzv2h)

---

## Prasyarat

### PC — Install Dependensi

**Arch Linux / CachyOS / Manjaro:**
```bash
sudo pacman -S cmake gcc opencv yaml-cpp
```

**Ubuntu / Debian:**
```bash
sudo apt update
sudo apt install -y cmake g++ libopencv-dev libyaml-cpp-dev
```

**Fedora:**
```bash
sudo dnf install cmake gcc-c++ opencv-devel yaml-cpp-devel
```

### Renesas RZ/V2H
- **Renesas RZ/V2H Yocto SDK** harus sudah terinstall (cross-compiler `aarch64-poky-linux-g++`)
- OpenCV 4.x dan yaml-cpp tersedia di sysroot SDK
- Biasanya SDK terinstall di `/opt/poky/3.1.x/`

---

## Build untuk PC

### Build standar (CPU)
```bash
cd tray_detection_C
mkdir build && cd build
cmake .. -DTARGET_PLATFORM=PC
make -j$(nproc)
```

### Build dengan CUDA GPU (opsional)
Jika OpenCV Anda di-build dengan CUDA support:
```bash
cmake .. -DTARGET_PLATFORM=PC
make -j$(nproc)
# Saat menjalankan, tambahkan flag --gpu
./tray_detector --camera 0 --gpu
```

### Build Release (optimized)
```bash
cmake .. -DTARGET_PLATFORM=PC -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

---

## Build untuk Renesas RZ/V2H (Cross-Compile)

### 1. Source SDK Environment
```bash
source /opt/poky/3.1.31/environment-setup-aarch64-poky-linux
```
> **Catatan:** Path `/opt/poky/3.1.31/` harus disesuaikan dengan versi SDK Anda.

### 2. Konfigurasi Toolchain
Edit file `toolchain_rzv2h.cmake` jika path SDK berbeda:
```cmake
set(SDK_ROOT "/opt/poky/3.1.31" CACHE PATH "Renesas Yocto SDK root")
```

### 3. Build
```bash
cd tray_detection_C
mkdir build_rzv2h && cd build_rzv2h
cmake .. -DTARGET_PLATFORM=RZV2H \
         -DCMAKE_TOOLCHAIN_FILE=../toolchain_rzv2h.cmake \
         -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

### 4. Deploy ke Board
```bash
# Copy binary ke board (via SCP)
scp tray_detector root@<KAKIP_IP>:/home/root/

# Copy file konfigurasi yang diperlukan
scp ../../calibration_params.yml root@<KAKIP_IP>:/home/root/
scp ../../tray_detector/tray_calibration.yaml root@<KAKIP_IP>:/home/root/tray_detector/
scp ../../weights/cup_detection_v3_12_s_best.onnx root@<KAKIP_IP>:/home/root/weights/
```

### 5. Jalankan di Board
```bash
ssh root@<KAKIP_IP>
cd /home/root
./tray_detector --camera 0 --method B --no-yolo --lock-focus
```

---

## Cara Penggunaan

### 1. Mode Gambar Tunggal
```bash
# Default (auto fusion)
./tray_detector --image test_tray25.0cm.jpg

# Method B (disarankan)
./tray_detector --image test.jpg --method B

# Tanpa YOLO
./tray_detector --image test.jpg --no-yolo
```

### 2. Mode Batch (Direktori)
```bash
./tray_detector --input_dir images/ --output_dir results/batch/
```

### 3. Mode Live Camera
```bash
# Kamera default
./tray_detector --camera 0

# Kamera spesifik + lock focus (DISARANKAN)
./tray_detector --camera 2 --method B --lock-focus --focus-value 0

# Tanpa YOLO + lock focus (untuk tray kosong)
./tray_detector --camera 0 --no-yolo --lock-focus

# Dengan GPU (PC only, jika OpenCV CUDA tersedia)
./tray_detector --camera 0 --method B --gpu
```

### Shortcut Keyboard (Live Mode)
| Tombol | Fungsi |
|---|---|
| `q` | Keluar dari aplikasi |
| `s` | Ambil screenshot |
| `r` | Mulai / Berhenti merekam video |
| `p` | Pause / Resume rekaman |

### Session Report
Setelah keluar dari mode live (`q`), sistem mencetak ringkasan:
- Total frames diproses
- Persentase frame valid
- Rata-rata, min, max jarak
- Jumlah spike yang ditolak

---

## Opsi Argumen Lengkap

| Argumen | Deskripsi |
|---|---|
| `--image PATH` | Proses satu file gambar |
| `--input_dir PATH` | Direktori gambar untuk batch |
| `--camera [INDEX]` | Mode live camera (default: 0) |
| `--output_dir PATH` | Folder output (default: `tray_detector/results`) |
| `--method METHOD` | `auto`, `A`, `B`, `C` (default: `auto`) |
| `--no-yolo` | Matikan YOLO, gunakan full frame |
| `--weights PATH` | Path ke model ONNX |
| `--params PATH` | Path ke `calibration_params.yml` |
| `--lock-focus` | Kunci auto-focus kamera |
| `--focus-value N` | Nilai fokus 0-255 (default: 0) |
| `--gpu` | Gunakan CUDA GPU backend (PC only) |
| `--help` | Tampilkan bantuan |

---

## Arsitektur Detector (YOLO)

Sistem menggunakan **abstract interface `IDetector`** dengan 2 backend:

| Platform | Backend | Compile Flag |
|---|---|---|
| PC | `OnnxDetector` (OpenCV DNN, CPU/GPU) | `-DTARGET_PLATFORM=PC` |
| RZ/V2H | `DrpaiDetector` (NPU DRP-AI) | `-DTARGET_PLATFORM=RZV2H` |

CMake secara otomatis memilih backend yang benar berdasarkan `TARGET_PLATFORM`.

---

## Catatan untuk RZ/V2H

### DRP-AI Integration
File `src/drpai_detector.cpp` saat ini adalah **stub/placeholder**. Untuk mengaktifkan inferensi NPU:

1. Install Renesas DRP-AI TVM SDK
2. Konversi model ONNX ke format DRP-AI:
   ```bash
   # Menggunakan DRP-AI TVM compiler di PC host
   python3 drpai_tvm_compiler.py \
     --onnx cup_detection_v3_12_s_best.onnx \
     --output ./drpai_model/
   ```
3. Edit `drpai_detector.cpp`:
   - Buka `/dev/drpai0`
   - Load model dari direktori output
   - Implementasi pre/post-processing
4. Update `CMakeLists.txt`:
   ```cmake
   target_include_directories(tray_detector PRIVATE ${DRPAI_INCLUDE_DIR})
   target_link_libraries(tray_detector PRIVATE ${DRPAI_LIBRARIES})
   ```

### Camera MIPI-CSI
Jika KAKIP menggunakan kamera MIPI-CSI (bukan USB), gunakan GStreamer pipeline:
```bash
# Contoh: edit camera_utils.cpp untuk menggunakan GStreamer
# cv::VideoCapture cap("v4l2src device=/dev/video0 ! ...", cv::CAP_GSTREAMER);
```

### Headless Mode (Tanpa Display)
Untuk deployment produksi tanpa monitor, hapus pemanggilan `cv::imshow()` dan `cv::waitKey()` dari `main.cpp`. Ganti dengan loop yang langsung mencetak hasil JSON ke stdout atau mengirim via serial/MQTT.
