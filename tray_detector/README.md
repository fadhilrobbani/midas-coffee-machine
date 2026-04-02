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

```bash
# Penggunaan dasar (Auto-detect cup via YOLO + Gabungan Analisa)
python -m tray_detector.run_tray_detector --image test_tray25.0cm_rim17.9cm_1775104565.jpg

# Penggunaan Method B khusus (Sangat Disarankan karena Paling Akurat)
python -m tray_detector.run_tray_detector --image <nama_file.jpg> --method B

# Pengujian Gambar Tray Kosong tanpa YOLO sama sekali
python -m tray_detector.run_tray_detector --image <nama_file.jpg> --method B --no-yolo

# Mode Debug (Menampilkan window pop-up step-by-step thresholding)
python -m tray_detector.run_tray_detector --image <nama_file.jpg> --method B --debug
```

### Opsi Argumen
* `--image`: (Wajib) Path ke gambar uji.
* `--method`: (Opsional) Memaksa ekseskusi *backend math* tertentu: `A`, `B`, `C`, atau `auto`.
  * `A`: Deteksi pinggir bingkai (bergantung tinggi/rendah mask YOLO secara penuh).
  * `B`: Multi-Spatial Hough Lines (Mencari dan memetakan setiap celah sekat fisik tray yang terekspos). **Metode Terapik.**
  * `C`: Horizontal Profile IQR Canny (Pemindaian fluktuasi intensitas profil y-axis).
  * `auto`: Default, menggabungkan performa multi-estimasi.
* `--no-yolo`: (Opsional) Matikan fitur deteksi cangkir. Digunakan saat mengestimasi dari foto kerangka murni tanpa minuman.
* `--debug`: (Opsional) Buka jendela OpenCV untuk analisa visual *Canny* dan *Masking*.

## Konfigurasi Fisik (Kalibrasi)
Kualitas pengukuran *sepenuhnya bersandar pada Konstanta Fisik* pada `tray_detector/config.py`.

Untuk mengubah ketepatan ukuran sentimeter keluaran, sesuaikan nilai berikut di **baris 20-23** `config.py`:
```python
P_REAL_CM = 0.69         # Pitch Fisik aktual (jarak dari titik tengah Sekat-1 ke tengah Sekat-2 dalam satuan cm).
F_PIXEL = 662.17       # Focal length fisik Lensa Kamera Anda.
THETA_TILT_DEG = 20.0  # Kecondongan sudut kamera dalam derajat.
```
**Tips:** Jika output aplikasi menunjuk ke **29.1 cm** padahal Anda mengukur manual menggunakan penggaris bahwa jarak kamera ke tray adalah **25.0 cm**, Anda tinggal mengecilkan `P_REAL_CM` proporsional dengan faktor tersebut (`25.0/29.1 * angka_awal_P_REAL_CM`).

## Struktur Output (JSON)
Setiap kali selesai, pipeline selain memproduksi foto ber-anotasi ke dalam folder `tray_detector/results/`, ia juga mencetak data pengukuran tunggal berformat JSON di Terminal konsol (berguna bila Anda ingin mengikat skrip ini sebagai modul di API backend):

```json
{
  "D_tray_cm": 25.12,
  "method_used": "B",
  "confidence": 0.85,
  "status": "OK",
  "D_left_cm": 24.49,
  "D_right_cm": 25.74,
  "lines_left": 12,
  "lines_right": 13,
  "notes": null
}
```
* **"status":** Akan bernilai `"OK"` bila Pitch ditemukan. Jika objek kabur, tertutup sepenuhnya oleh cangkir, atau noise tinggi, ia akan merespons `"INSUFFICIENT_DATA"`.
* **"lines_left" / "lines_right":** Memastikan seberapa banyak sekat tray yang terbaca untuk membentuk jarak agregat di sisi kiri dan kanan gelas. Semakin banyak, semakin tinggi angka `confidence`.
