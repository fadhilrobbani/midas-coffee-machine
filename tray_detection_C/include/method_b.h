#pragma once
/**
 * method_b.h — Metode B: Horizontal Slat Pitch (PRIMARY)
 *
 * Pipeline: mask → CLAHE → Canny → HoughLinesP → cluster → pitch → D_tray
 * Formula: D_tray = (f_pixel × P_real_cm × cos(θ)) / p_avg_pixel
 */

#include <vector>
#include <string>
#include <optional>
#include <opencv2/core.hpp>

namespace tray {

struct MethodBResult {
    double D_tray_cm   = 0.0;
    double confidence  = 0.0;
    std::string status = "INSUFFICIENT_DATA";
    double D_left_cm   = 0.0;
    double D_right_cm  = 0.0;
    int lines_left     = 0;
    int lines_right    = 0;
    std::string notes;
    double pitch_px    = 0.0;
    int num_slats      = 0;

    // Debug visualization data
    std::vector<cv::Vec4i> debug_lines;
    std::vector<cv::Vec4i> debug_clustered;

    bool valid = false;  // Helper: apakah D_tray_cm terisi
};

/**
 * Estimasi jarak berdasarkan pitch sekat horizontal tray.
 */
MethodBResult estimate_D_tray_method_B(
    const cv::Mat& frame,
    const cv::Mat& tray_mask,
    const int* glass_bbox,    // nullptr or int[4] {x1,y1,x2,y2}
    double f_pixel,
    double P_real_cm,
    double theta_tilt_rad,
    int canny_low = 20, int canny_high = 80,
    int hough_threshold = 25,
    int hough_min_line_length = 25,
    int hough_max_line_gap = 15,
    double angle_tol_deg = 10.0,
    int min_lines = 3,
    double D_min = 5.0, double D_max = 100.0,
    int ref_slats = 27);

} // namespace tray
