/**
 * @file volume_config.h
 * @brief Hardcoded operational parameters for the Cup Volume Estimator.
 *
 * Semua konstanta konfigurasi dikumpulkan di satu tempat agar mudah diubah.
 *
 * Parameter ini mencerminkan setup fisik kamera yang sudah dikalibrasi:
 *   - Moildev Mode 2 (Pitch/Yaw/Roll), pitch -15° untuk kamera miring ke bawah
 *   - Zoom 2.0 (hybrid: moil_zoom=1.5 + digital_zoom=1.33 via center-crop)
 *   - V4L2 exposure 5000 (ekivalen dengan smart_exposure 5.0 pada skala 1-10)
 *
 * CATATAN PENTING — JANGAN ganti interpolasi ke INTER_CUBIC / INTER_LANCZOS4:
 *   INTER_CUBIC/LANCZOS4 menyebabkan crash (std::terminate / SIGABRT) yang
 *   TIDAK BISA di-catch saat OpenCL kernel berjalan bersamaan dengan upload
 *   frame transisi pasca-perubahan exposure (race condition di device memory).
 *   INTER_LINEAR sudah merupakan bilinear interpolation = built-in anti-aliasing,
 *   dan secara visual tidak ada perbedaan yang terlihat di resolusi 2592×1944.
 */

#pragma once

#include <opencv2/imgproc.hpp>   // cv::INTER_LINEAR

namespace fusion {
namespace volume_config {

// ── ArUco Marker ────────────────────────────────────────────────────────────
/// Ukuran fisik sisi marker ArUco (cm)
constexpr double MARKER_SIZE_CM = 2.5;

// ── Moildev Anypoint Parameters ──────────────────────────────────────────────
/// Total zoom (hybrid: moil_zoom = min(zoom, 1.5) + digital_zoom = zoom/moil_zoom)
constexpr double MOIL_ZOOM      = 2.0;

/// Mode Moildev: 2 = AnyPointM2 (Pitch/Yaw/Roll), 1 = AnyPointM (Alpha/Beta)
constexpr int    MOIL_MODE      = 2;

/// Pitch dalam derajat — kamera miring ke bawah 15°
constexpr double MOIL_PITCH_DEG = -15.0;

/// Yaw dalam derajat — lurus horizontal
constexpr double MOIL_YAW_DEG  = 0.0;

/// Roll dalam derajat — tidak ada rotasi
constexpr double MOIL_ROLL_DEG = 0.0;

/// Batas aman zoom Moildev sebelum polynomial kalibrasi wrap-around
constexpr double MAX_MOIL_ZOOM  = 1.5;

// ── Camera Exposure ──────────────────────────────────────────────────────────
/// Nilai V4L2 exposure (= smart_exposure 5.0 × 1000)
constexpr int    V4L2_EXPOSURE  = 5000;

// ── Remap Interpolation ──────────────────────────────────────────────────────
/// SELALU gunakan INTER_LINEAR — aman dari race condition OpenCL.
/// JANGAN ganti ke INTER_CUBIC atau INTER_LANCZOS4 (lihat catatan di atas).
constexpr int    REMAP_INTERP   = cv::INTER_LINEAR;

// ── EMA Smoothing ────────────────────────────────────────────────────────────
/// Alpha untuk Exponential Moving Average pada output volume (0 = freeze, 1 = raw)
constexpr double EMA_ALPHA      = 0.35;

}  // namespace volume_config
}  // namespace fusion
