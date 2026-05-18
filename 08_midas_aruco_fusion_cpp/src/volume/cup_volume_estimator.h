/**
 * @file cup_volume_estimator.h
 * @brief Modular C++ library untuk estimasi volume gelas dari frame fisheye.
 *
 * Port dari 07_midas_aruco_fusion/core/volume_math.py — diperluas dengan
 * Moildev undistortion internal (Opsi A: modul menerima raw fisheye frame).
 *
 * Pipeline internal:
 *   raw_frame → [MoilUndistorter] → measure_rim_width_px() → calc_diameter() → calc_volume()
 *
 * Semua parameter Moildev di-hardcode via volume_config.h:
 *   pitch = -15°, zoom = 2.0, mode = 2, INTER_LINEAR (bukan CUBIC/LANCZOS4)
 *
 * Cara integrasi (mengikuti pola Model_kakip/run_fusion.cpp):
 * @code
 *   // Init SEKALI di startup:
 *   fusion::CupVolumeEstimator estimator("camera_parameters.json", "syue_7730v1_6");
 *
 *   // Override focal length ArUco (opsional tapi disarankan):
 *   double focal_px = estimator.adjusted_focal_px();
 *
 *   // Per-frame:
 *   fusion::VolumeInput in { raw_frame, bbox, h_cup_cm, z_tray_cm, focal_px };
 *   fusion::VolumeResult res = estimator.estimate(in);
 *   if (res.valid) printf("Volume: %.0f mL\n", res.volume_ml);
 * @endcode
 */

#pragma once

#include <opencv2/core.hpp>
#include <opencv2/videoio.hpp>   // cv::VideoCapture
#include <string>
#include <memory>

#include "height_math.h"   // for fusion::BBox

namespace fusion {

// Forward declaration — implementasi di moil_undistorter.h/cpp
class MoilUndistorter;

// ─────────────────────────────────────────────────────────────────────────────

/**
 * @brief Input untuk estimasi volume satu gelas per-frame.
 */
struct VolumeInput {
    cv::Mat frame;        ///< Raw fisheye frame (BELUM di-undistort)
    BBox    bbox;         ///< Bounding box gelas dari YOLO {x1, y1, x2, y2}
    double  h_cup_cm;     ///< Tinggi gelas dalam cm (sudah dihitung oleh caller)
    double  z_tray_cm;    ///< Jarak kamera ke tray/meja via ArUco (cm)
    double  focal_px;     ///< Focal length efektif dalam piksel (dari ArUco/Moildev)
};

/**
 * @brief Hasil estimasi volume untuk satu gelas.
 */
struct VolumeResult {
    double rim_w_px    = 0.0; ///< Lebar rim dalam piksel (dari Otsu strip detection)
    double z_rim_cm    = 0.0; ///< Jarak kamera ke bibir gelas (= z_tray - h_cup)
    double diameter_cm = 0.0; ///< Diameter fisik gelas (cm)
    double volume_ml   = 0.0; ///< Volume estimasi dalam mL (= cm³)
    bool   valid       = false;///< true jika semua tahap berhasil
};

// ─────────────────────────────────────────────────────────────────────────────

/**
 * @class CupVolumeEstimator
 * @brief Modul mandiri estimasi volume gelas dari raw fisheye frame.
 *
 * Menggabungkan:
 *  - Moildev undistortion (hardcoded params dari volume_config.h)
 *  - Otsu-based rim width measurement
 *  - Pinhole camera diameter calculation
 *  - Cylinder volume model
 *
 * Thread safety: estimate() TIDAK thread-safe (MoilUndistorter menggunakan
 * internal mutex, tetapi caller harus memastikan tidak ada panggilan paralel
 * pada instance yang sama). Buat instance terpisah per thread jika diperlukan.
 *
 * @note Mengikuti pola inisialisasi dari Model_kakip/run_fusion.cpp:
 *   moil_undistorter = std::make_unique<MoilUndistorter>(json, name, pitch, ...);
 */
class CupVolumeEstimator {
public:
    /**
     * @brief Konstruktor — init MoilUndistorter SEKALI dengan hardcoded params.
     *
     * @param camera_params_json  Path ke camera_parameters.json Moildev
     * @param camera_name         Nama profil kamera di JSON (mis. "syue_7730v1_6")
     * @param frame_width         Lebar resolusi stream aktual (default 2592)
     * @param frame_height        Tinggi resolusi stream aktual (default 1944)
     *
     * @throws std::runtime_error jika JSON tidak ditemukan atau profil tidak valid
     */
    explicit CupVolumeEstimator(
        const std::string& camera_params_json,
        const std::string& camera_name = "syue_7730v1_6",
        int frame_width  = 2592,
        int frame_height = 1944
    );

    ~CupVolumeEstimator();

    // Non-copyable (MoilUndistorter tidak copyable)
    CupVolumeEstimator(const CupVolumeEstimator&)            = delete;
    CupVolumeEstimator& operator=(const CupVolumeEstimator&) = delete;

    // Movable
    CupVolumeEstimator(CupVolumeEstimator&&)            = default;
    CupVolumeEstimator& operator=(CupVolumeEstimator&&) = default;

    // ── Core API ─────────────────────────────────────────────────────────────

    /**
     * @brief Estimasi volume dari satu raw fisheye frame.
     *
     * Pipeline:
     *   1. Undistort frame via Moildev (hardcoded pitch/zoom/mode)
     *   2. Deteksi lebar rim via Otsu strip (measure_rim_width_px)
     *   3. Hitung diameter via pinhole model (calc_diameter)
     *   4. Hitung volume via silinder (calc_volume)
     *
     * @param input  VolumeInput dengan frame mentah + metadata
     * @return       VolumeResult (valid=false jika input tidak cukup)
     */
    VolumeResult estimate(const VolumeInput& input);

    // ── Utility ──────────────────────────────────────────────────────────────

    /**
     * @brief Focal length (px) yang sudah disesuaikan dengan Moildev zoom.
     *
     * Gunakan nilai ini untuk meng-override aruco.camera_matrix[0,0] saat
     * menginisialisasi ArUco detector — sama seperti pola di run_fusion.cpp kakip:
     *   aruco.camera_matrix = moil.build_aruco_camera_matrix(w, h);
     *
     * @return focal length efektif dalam piksel
     */
    double adjusted_focal_px() const;

    /**
     * @brief Hitung volume langsung dari tinggi + diameter (tanpa frame/rim detection).
     *
     * Helper statis untuk kasus di mana diameter sudah diketahui dari kalibrasi.
     *
     * @param h_cup_cm    Tinggi gelas (cm)
     * @param diameter_cm Diameter gelas (cm)
     * @return Volume dalam mL (0.0 jika input tidak valid)
     */
    static double from_height_diameter(double h_cup_cm, double diameter_cm);

    /**
     * @brief Set V4L2 manual exposure ke nilai hardcoded (5000) pada VideoCapture.
     *
     * Menonaktifkan auto-exposure lalu set shutter ke V4L2_EXPOSURE dari config.
     * Panggil SEKALI setelah cap.open() — sama seperti pola Python
     * set_manual_exposure() dengan smart_exposure=5.0.
     *
     * @param cap  VideoCapture yang sudah open
     */
    static void apply_exposure(cv::VideoCapture& cap);

    /**
     * @brief true jika MoilUndistorter berhasil diinisialisasi.
     */
    bool is_ready() const { return ready_; }

private:
    bool ready_ = false;

    // MoilUndistorter dari src/fisheye/ — di-init di constructor dengan
    // params hardcoded dari volume_config.h (pitch=-15, zoom=2, mode=2)
    std::unique_ptr<MoilUndistorter> moil_;

    int frame_w_;
    int frame_h_;
};

}  // namespace fusion
