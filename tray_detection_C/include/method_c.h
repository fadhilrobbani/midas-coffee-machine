#pragma once
/**
 * method_c.h — Metode C: Homografi 4 Corner + PnP (Backup)
 *
 * Formula: D_tray = |T[2]| × cos(θ)
 */

#include <vector>
#include <string>
#include <optional>
#include <opencv2/core.hpp>

namespace tray {

struct MethodCResult {
    double D_tray_cm   = 0.0;
    double confidence  = 0.0;
    std::string status = "INSUFFICIENT_DATA";
    double reprojection_error = 0.0;
    std::vector<cv::Point2f> corners;
    std::string notes;
    bool valid = false;
};

/**
 * Estimasi jarak menggunakan solvePnP dari 4 corner tray.
 */
std::optional<MethodCResult> estimate_D_tray_method_C(
    const cv::Mat& tray_mask,
    const cv::Mat& K,
    const cv::Mat& dist_coeffs,
    double W_tray_cm,
    double L_tray_cm,
    double theta_tilt_rad,
    double D_min = 5.0,
    double D_max = 40.0);

} // namespace tray
