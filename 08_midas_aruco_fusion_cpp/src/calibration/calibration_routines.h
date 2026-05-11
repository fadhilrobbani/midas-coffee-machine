/**
 * @file calibration_routines.h
 * @brief 7 calibration mode routines.
 * Port of Python core/calibration_routines.py.
 */

#pragma once

#include <opencv2/core.hpp>
#include <vector>
#include <string>
#include <functional>
#include "calibration_storage.h"
#include "aruco_detector.h"
#include "height_math.h"

namespace fusion {

/// Frame provider callback type
using FrameProvider = std::function<cv::Mat()>;
/// UI update callback type
using UICallback = std::function<void(const cv::Mat&)>;
/// Key provider callback type
using KeyProvider = std::function<int()>;

/// Polynomial fitting via Vandermonde matrix (replaces np.polyfit)
std::vector<double> polyfit(const std::vector<double>& x,
                            const std::vector<double>& y, int degree);

/// Remove outliers using IQR method
std::vector<double> remove_outliers_iqr(const std::vector<double>& data,
                                         double iqr_factor = 1.5);

/// Median of a vector
double median(std::vector<double> v);

// ── Calibration Routine Functions ──────────────────────────────────────

/// Type 1 & 2: 1-Point / 2-Point calibration
void run_calib_1p_2p(int type, double true_height,
                     FrameProvider get_frame, UICallback update_ui,
                     KeyProvider get_key, const ArucoDetector& aruco,
                     const std::string& save_path = "calibration.json",
                     int warmup_frames = 30, int sample_frames = 60);

/// Type 3: Z-Grid polynomial calibration
void run_calib_zgrid(double true_height, int n_positions,
                     FrameProvider get_frame, UICallback update_ui,
                     KeyProvider get_key, const ArucoDetector& aruco,
                     const std::string& save_path = "calibration.json");

/// Type 4: BBox area compensation calibration
void run_calib_bbox(double true_height,
                    FrameProvider get_frame, UICallback update_ui,
                    KeyProvider get_key, const ArucoDetector& aruco,
                    const std::string& save_path = "calibration.json");

/// Type 5: Geometric projection calibration
void run_calib_geom(double true_height, int n_positions,
                    FrameProvider get_frame, UICallback update_ui,
                    KeyProvider get_key, const ArucoDetector& aruco,
                    double focal_px = 500.0,
                    const std::string& save_path = "calibration.json");

/// Type 6: Bilateral Z-Grid calibration (2 cups)
void run_calib_bilateral(double true_height_1, double true_height_2,
                         int n_positions,
                         FrameProvider get_frame, UICallback update_ui,
                         KeyProvider get_key, const ArucoDetector& aruco,
                         const std::string& save_path = "calibration.json");

/// Type 7: Analytic Geometry calibration (2 cups)
void run_calib_analytic(double true_height_1, double true_height_2,
                        FrameProvider get_frame, UICallback update_ui,
                        KeyProvider get_key, const ArucoDetector& aruco,
                        const std::string& save_path = "calibration.json");

} // namespace fusion
