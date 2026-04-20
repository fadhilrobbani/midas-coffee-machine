# Perbandingan Evaluasi Midas: Single-Glass vs. Multi-Glass

Laporan ini menganalisis perbedaan performa sistem kalibrasi MiDaS antara pengujian pada **02 April 2026** dan **14 April 2026**.

## 1. Ringkasan Metrik Performa

| Pengujian | Skenario | MAE (Error) | RMSE | Akurasi <1cm |
| :--- | :--- | :--- | :--- | :--- |
| **02 April** | 1 Jenis Gelas (10 Foto) | **0.41 cm** | **0.54 cm** | **90.0%** |
| **14 April** | 3 Jenis Gelas (14 Foto) | **1.35 cm** | **1.52 cm** | **35.7%** |

## 2. Analisis Teknis: Mengapa Hasil Terbaru Lebih Rendah?

### A. Kompleksitas Geometri Gelas (Faktor Utama)
Anda menyebutkan bahwa sekarang menggunakan **3 jenis gelas** berbeda dengan total 5 foto per gelas. 
- **Variasi Rim:** Setiap gelas memiliki ketebalan dan bentuk pinggiran (rim) yang berbeda. MiDaS menangkap nilai `M_rim` berdasarkan kontras visual. Gelas yang berbeda akan menghasilkan nilai `M_rim` yang berbeda pula meski diletakkan pada jarak fisik yang sama.
- **Ambiguity Scale:** Karena model regresi dipaksa untuk mencocokkan (fit) 3 geometri berbeda ke dalam satu formula linear tunggal, model harus mencari "jalan tengah". Hal ini secara matematis menurunkan presisi spesifik yang sebelumnya didapat saat hanya menggunakan satu jenis gelas.

### B. Rentang Jarak (Range)
- Pengujian **02 April** mencakup jarak yang lebih jauh (hingga 36cm), di mana MiDaS cenderung lebih stabil.
- Pengujian **14 April** berkonsentrasi pada jarak dekat (21cm - 25cm). Pada jarak sedekat ini, distorsi lensa dan fluktuasi nilai kedalaman AI menjadi lebih sensitif.

### C. Efek Peningkatan Jumlah Data
Meskipun jumlah foto meningkat, "kualitas" konsistensi antar data menurun karena perbedaan bentuk fisik gelas. Peningkatan error ini adalah indikasi bahwa model sedang mencoba menjadi **General (Universal)** tapi kehilangan kemampuan **Specialized (Presisi Tinggi)** pada satu jenis objek.

## 3. Kesimpulan & Saran

Error sebesar **1.35 cm** pada skenario multi-gelas sebenarnya masih termasuk dalam kategori **"Loose Accuracy" (Akurasi Longgar)** yang cukup baik untuk aplikasi robotika dasar. Namun, untuk mencapai presisi <5mm secara universal, kita membutuhkan:
1.  **Profil Kalibrasi Khusus:** Memisahkan konstanta `C1-C4` untuk setiap jenis gelas.
2.  **Penambahan Variabel:** Memasukkan parameter tambahan seperti diameter rim dalam piksel untuk membantu regresi membedakan jenis gelas secara matematis.

Laporan ini dibuat sebagai basis referensi untuk optimasi tuning kalibrasi berikutnya.
