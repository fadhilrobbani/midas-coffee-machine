/**
 * config.cpp — Implementasi loading konfigurasi dari YAML
 */

#include "config.h"
#include <cmath>
#include <iostream>
#include <fstream>
#include <yaml-cpp/yaml.h>

namespace tray {

namespace {

// Default paths (relative to executable)
const std::string DEFAULT_CALIB_PATH      = "../calibration_params.yml";
const std::string DEFAULT_TRAY_CALIB_PATH = "../tray_detector/tray_calibration.yaml";
const std::string DEFAULT_WEIGHTS_PATH    = "../weights/cup_detection_v3_12_s_best.onnx";

// Default physical dimensions
constexpr double DEF_P_REAL_CM       = 0.69;
constexpr double DEF_W_TRAY_CM       = 12.5;
constexpr double DEF_L_TRAY_CM       = 22.0;
constexpr double DEF_THETA_TILT_DEG  = 20.0;

} // anonymous namespace


TrayConfig load_config(const std::string& calib_path,
                       const std::string& tray_calib_path,
                       const std::string& weights_path) {
    TrayConfig cfg;

    // ── 1. Load camera calibration ──────────────────────────────────────
    std::string cam_path = calib_path.empty() ? DEFAULT_CALIB_PATH : calib_path;

    try {
        YAML::Node root = YAML::LoadFile(cam_path);

        // Camera matrix (3x3)
        auto cm = root["camera_matrix_left"];
        cfg.camera_matrix = cv::Mat::zeros(3, 3, CV_64F);
        for (int r = 0; r < 3; r++)
            for (int c = 0; c < 3; c++)
                cfg.camera_matrix.at<double>(r, c) = cm[r][c].as<double>();

        // Distortion coefficients
        auto dc = root["dist_coeff_left"];
        cfg.dist_coeffs = cv::Mat::zeros(1, 5, CV_64F);
        for (int c = 0; c < 5; c++)
            cfg.dist_coeffs.at<double>(0, c) = dc[0][c].as<double>();

        // Focal length (average fx, fy)
        double fx = cfg.camera_matrix.at<double>(0, 0);
        double fy = cfg.camera_matrix.at<double>(1, 1);
        cfg.f_pixel = (fx + fy) / 2.0;

        std::cout << "[CONFIG] Camera calibration loaded: f_pixel="
                  << cfg.f_pixel << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "[CONFIG] ERROR: Cannot load camera calibration: "
                  << cam_path << " (" << e.what() << ")" << std::endl;
        // Use identity matrix as fallback
        cfg.camera_matrix = cv::Mat::eye(3, 3, CV_64F);
        cfg.dist_coeffs = cv::Mat::zeros(1, 5, CV_64F);
        cfg.f_pixel = 660.0;  // Reasonable default
    }

    // ── 2. Set physical defaults ────────────────────────────────────────
    cfg.P_real_cm = DEF_P_REAL_CM;
    cfg.W_tray_cm = DEF_W_TRAY_CM;
    cfg.L_tray_cm = DEF_L_TRAY_CM;
    cfg.theta_tilt_deg = DEF_THETA_TILT_DEG;
    cfg.ref_slats = 27;

    // ── 3. Load tray calibration (override if exists) ───────────────────
    std::string tray_path = tray_calib_path.empty()
                            ? DEFAULT_TRAY_CALIB_PATH
                            : tray_calib_path;

    try {
        std::ifstream fs(tray_path);
        if (fs.good()) {
            YAML::Node tray = YAML::LoadFile(tray_path);
            if (tray["P_real_cm"])
                cfg.P_real_cm = tray["P_real_cm"].as<double>();
            if (tray["theta_tilt_deg"])
                cfg.theta_tilt_deg = tray["theta_tilt_deg"].as<double>();
            if (tray["ref_slats"])
                cfg.ref_slats = tray["ref_slats"].as<int>();
            if (tray["D_known_cm"])
                cfg.D_known_cm = tray["D_known_cm"].as<double>();

            std::cout << "[CONFIG] Tray calibration loaded: P_real="
                      << cfg.P_real_cm << ", ref_slats=" << cfg.ref_slats
                      << ", theta=" << cfg.theta_tilt_deg << "deg"
                      << ", D_known=" << cfg.D_known_cm << "cm"
                      << std::endl;
        } else {
            std::cout << "[CONFIG] Tray calibration not found, using defaults."
                      << std::endl;
        }
    } catch (const std::exception& e) {
        std::cerr << "[CONFIG] Warning: Cannot load tray calibration: "
                  << e.what() << std::endl;
    }

    // ── 4. Compute derived values ───────────────────────────────────────
    cfg.theta_tilt_rad = cfg.theta_tilt_deg * M_PI / 180.0;

    // ── 5. Weights path ─────────────────────────────────────────────────
    cfg.weights_path = weights_path.empty() ? DEFAULT_WEIGHTS_PATH : weights_path;

    return cfg;
}

} // namespace tray
