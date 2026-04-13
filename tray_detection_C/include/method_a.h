#pragma once
/**
 * method_a.h — Metode A: Apparent Width Tray (Fallback)
 *
 * Formula: D_tray = (f_pixel × W_real_cm × cos(θ)) / W_pixel
 */

#include <optional>
#include <string>

namespace tray {

struct MethodAResult {
    double D_tray_cm   = 0.0;
    double confidence  = 0.0;
    std::string status = "INSUFFICIENT_DATA";
    std::string notes;
};

/**
 * Estimasi jarak berdasarkan apparent width bounding box.
 */
std::optional<MethodAResult> estimate_D_tray_method_A(
    int bbox_x1, int bbox_y1, int bbox_x2, int bbox_y2,
    double f_pixel,
    double W_real_cm,
    double theta_tilt_rad,
    int frame_width,
    double D_min = 5.0,
    double D_max = 40.0);

} // namespace tray
