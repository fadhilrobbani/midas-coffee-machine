/**
 * @file cup_volume_estimator.cpp
 * @brief Implementasi CupVolumeEstimator — volume gelas dari raw fisheye frame.
 *
 * Pipeline per-frame:
 *   raw_fisheye_frame
 *     ↓ [MoilUndistorter] — hardcoded: pitch=-15°, zoom=2, mode=2, INTER_LINEAR
 *   undistorted_frame
 *     ↓ [measure_rim_width_px] — Otsu strip detection di bagian atas bbox
 *   rim_w_px
 *     ↓ [calc_diameter] — pinhole model: d = (rim_w × z_rim) / focal
 *   diameter_cm
 *     ↓ [calc_volume] — silinder: V = π × (d/2)² × h
 *   volume_ml
 *
 * Referensi:
 *   - Python: 07_midas_aruco_fusion/core/volume_math.py
 *   - Python: 07_midas_aruco_fusion/core/moil_undistorter.py
 *   - C++ kakip: Model_kakip/07_midas_aruco_fusion/core/moil_undistorter.hpp
 */

#include "cup_volume_estimator.h"
#include "volume_config.h"
#include "moil_undistorter.h"    // src/fisheye/moil_undistorter.h
#include "volume_math.h"          // src/math/volume_math.h

#include <opencv2/videoio.hpp>   // cv::VideoCapture
#include <iostream>
#include <stdexcept>

namespace fusion {

// ─────────────────────────────────────────────────────────────────────────────
// Constructor / Destructor
// ─────────────────────────────────────────────────────────────────────────────

CupVolumeEstimator::CupVolumeEstimator(
    const std::string& camera_params_json,
    const std::string& camera_name,
    int frame_width,
    int frame_height
)
    : frame_w_(frame_width), frame_h_(frame_height)
{
    std::cout << "[CupVol] Initializing MoilUndistorter...\n";
    std::cout << "[CupVol]   JSON  : " << camera_params_json << "\n";
    std::cout << "[CupVol]   Profil: " << camera_name        << "\n";
    std::cout << "[CupVol]   Mode  : " << volume_config::MOIL_MODE      << "\n";
    std::cout << "[CupVol]   Pitch : " << volume_config::MOIL_PITCH_DEG << "°\n";
    std::cout << "[CupVol]   Zoom  : " << volume_config::MOIL_ZOOM      << "x\n";
    std::cout << "[CupVol]   Stream: " << frame_width << "×" << frame_height << "\n";

    try {
        // Inisialisasi MoilUndistorter dengan mode dari volume_config.h.
        // Constructor di src/fisheye/moil_undistorter.h:
        //   MoilUndistorter(json_path, camera_name, mode)
        // lalu panggil update_maps() untuk set pitch/zoom.
        moil_ = std::make_unique<MoilUndistorter>(
            camera_params_json,
            camera_name,
            volume_config::MOIL_MODE
        );

        // Set pitch/yaw/zoom hardcoded via update_maps()
        // (sama dengan pola kakip: moil_undistorter = make_unique<>(json, name, pitch, yaw, roll, zoom, mode))
        moil_->update_maps(
            volume_config::MOIL_PITCH_DEG,
            volume_config::MOIL_YAW_DEG,
            volume_config::MOIL_ROLL_DEG,
            volume_config::MOIL_ZOOM
        );

        if (!moil_->is_ready()) {
            throw std::runtime_error(
                "[CupVol] MoilUndistorter failed to initialize — "
                "cek path JSON dan nama profil kamera."
            );
        }

        ready_ = true;
        std::cout << "[CupVol] Ready. Adjusted focal: "
                  << moil_->adjusted_focal_length() << " px\n";

    } catch (const std::exception& e) {
        std::cerr << "[CupVol] INIT ERROR: " << e.what() << "\n";
        ready_ = false;
    }
}

CupVolumeEstimator::~CupVolumeEstimator() = default;

// ─────────────────────────────────────────────────────────────────────────────
// Core Estimate
// ─────────────────────────────────────────────────────────────────────────────

VolumeResult CupVolumeEstimator::estimate(const VolumeInput& input) {
    VolumeResult result;

    // ── Guard: input validation ──────────────────────────────────────────────
    if (!ready_ || input.frame.empty()) {
        return result;
    }
    if (input.h_cup_cm <= 0.0 || input.z_tray_cm <= 0.0 || input.focal_px <= 0.0) {
        return result;
    }

    // Pastikan bbox valid
    const BBox& b = input.bbox;
    if (b.x2 <= b.x1 || b.y2 <= b.y1) {
        return result;
    }

    // ── Stage 1: Moildev undistortion ────────────────────────────────────────
    // PENTING: selalu INTER_LINEAR — bukan CUBIC/LANCZOS4 (crash di OpenCL)
    // MoilUndistorter::undistort() sudah menggunakan INTER_LINEAR + BORDER_CONSTANT
    // sesuai implementasi di src/fisheye/moil_undistorter.cpp
    cv::Mat undistorted = moil_->undistort(input.frame);

    if (undistorted.empty()) {
        std::cerr << "[CupVol] Undistort returned empty frame!\n";
        return result;
    }

    // ── Stage 2: Rim width detection (Otsu strip) ────────────────────────────
    // measure_rim_width_px() dari src/math/volume_math.h:
    //   - Ambil strip 10% dari atas bbox (rim level)
    //   - Grayscale + Otsu threshold
    //   - Cari kolom kiri-kanan yang ada piksel gelas
    //   - Fallback ke 50% bbox_w jika tidak ada piksel terdeteksi
    double rim_w_px = measure_rim_width_px(undistorted, input.bbox);
    result.rim_w_px = rim_w_px;

    // ── Stage 3: Diameter calculation ────────────────────────────────────────
    // z_rim = jarak kamera ke bibir gelas = z_tray - h_cup
    // Formula: diameter = (rim_w_px × z_rim) / focal_px
    // Self-compensating: kamera naik → z_rim besar, rim_w_px kecil → diameter tetap
    double z_rim_cm = std::max(0.0, input.z_tray_cm - input.h_cup_cm);
    result.z_rim_cm = z_rim_cm;

    double diameter_cm = calc_diameter(rim_w_px, z_rim_cm, input.focal_px);
    result.diameter_cm = diameter_cm;

    // ── Stage 4: Volume calculation ──────────────────────────────────────────
    // Formula: V = π × (d/2)² × h   (1 cm³ = 1 mL)
    double volume_ml = calc_volume(input.h_cup_cm, diameter_cm);
    result.volume_ml = volume_ml;

    // Tandai valid jika semua tahap menghasilkan nilai positif
    result.valid = (rim_w_px > 0.0 && diameter_cm > 0.0 && volume_ml > 0.0);

    return result;
}

// ─────────────────────────────────────────────────────────────────────────────
// Utility Methods
// ─────────────────────────────────────────────────────────────────────────────

double CupVolumeEstimator::adjusted_focal_px() const {
    if (!moil_ || !ready_) return 0.0;
    // build_aruco_camera_matrix(w, h) → K[0,0] = focal length yang sudah
    // disesuaikan dengan zoom (sama seperti Python: moil.build_aruco_camera_matrix())
    auto K = moil_->build_aruco_camera_matrix(frame_w_, frame_h_);
    return K(0, 0);   // fx
}

double CupVolumeEstimator::from_height_diameter(double h_cup_cm, double diameter_cm) {
    // Delegasikan ke pure-math function di volume_math.h
    return calc_volume(h_cup_cm, diameter_cm);
}

void CupVolumeEstimator::apply_exposure(cv::VideoCapture& cap) {
    if (!cap.isOpened()) {
        std::cerr << "[CupVol] apply_exposure: VideoCapture tidak terbuka!\n";
        return;
    }

    // Nonaktifkan auto-exposure (V4L2: mode 1 = manual)
    // CAP_PROP_AUTO_EXPOSURE: 0.25 = manual, 0.75 = auto (OpenCV normalization)
    cap.set(cv::CAP_PROP_AUTO_EXPOSURE, 0.25);

    // Set nilai exposure hardcoded
    // Nilai V4L2_EXPOSURE = 5000 ekivalen dengan smart_exposure=5.0 × 1000
    cap.set(cv::CAP_PROP_EXPOSURE, static_cast<double>(volume_config::V4L2_EXPOSURE));

    std::cout << "[CupVol] Exposure set: V4L2=" << volume_config::V4L2_EXPOSURE
              << " (smart_exposure=5.0, auto=OFF)\n";
}

}  // namespace fusion
