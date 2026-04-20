#pragma once
/**
 * config.h — Konfigurasi & loading parameter kalibrasi.
 *
 * Memuat parameter kamera dari calibration_params.yml
 * dan kalibrasi tray dari tray_calibration.yaml.
 */

#include <string>
#include <opencv2/core.hpp>

namespace tray {

struct TrayConfig {
    // Camera calibration
    cv::Mat camera_matrix;   // 3x3
    cv::Mat dist_coeffs;     // 1x5
    double f_pixel = 0.0;

    // Physical dimensions
    double P_real_cm      = 0.69;
    double W_tray_cm      = 12.5;
    double L_tray_cm      = 22.0;
    double theta_tilt_deg = 20.0;
    double theta_tilt_rad = 0.0;
    int    ref_slats      = 27;
    double D_known_cm     = 0.0;

    // Validation range
    double D_min_cm = 2.0;
    double D_max_cm = 100.0;

    // Hough Lines parameters
    int    canny_low              = 20;
    int    canny_high             = 80;
    int    hough_threshold        = 25;
    int    hough_min_line_length  = 25;
    int    hough_max_line_gap     = 15;
    double horizontal_angle_tol_deg = 10.0;
    int    min_lines_per_zone     = 3;

    // Paths
    std::string weights_path;
};

/**
 * Load konfigurasi lengkap dari YAML files.
 * @param calib_path   Path ke calibration_params.yml
 * @param tray_calib_path  Path ke tray_calibration.yaml (opsional)
 * @param weights_path  Path ke ONNX weights (opsional override)
 */
TrayConfig load_config(const std::string& calib_path = "",
                       const std::string& tray_calib_path = "",
                       const std::string& weights_path = "");

} // namespace tray
