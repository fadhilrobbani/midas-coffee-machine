/**
 * @file aruco_detector.h
 * @brief ArUco marker detection and pose estimation.
 *
 * Port of Python 06_aruco_marker/aruco_detector.py.
 * Features: multi-scale fallback, solvePnP distance, reprojection error.
 */

#pragma once

#include <opencv2/core.hpp>
#include <opencv2/aruco.hpp>
#include <opencv2/calib3d.hpp>
#include <vector>
#include <optional>
#include <string>

namespace fusion {

/**
 * @brief Result from detecting a single ArUco marker.
 */
struct ArucoResult {
    int id = -1;
    std::vector<cv::Point2f> corners;
    double distance_cm = 0.0;
    cv::Vec3d rvec, tvec;
    double reprojection_error = 0.0;
    cv::Vec3d euler_deg;  // roll, pitch, yaw
};

/**
 * @brief Best distance result with associated marker info.
 */
struct BestDistance {
    double distance_cm = 0.0;
    int marker_id = -1;
    double reprojection_error = 0.0;
};

/**
 * @brief ArUco marker detector with multi-scale fallback and pose estimation.
 */
class ArucoDetector {
public:
    /**
     * @brief Construct detector with camera calibration.
     * @param camera_matrix 3x3 camera intrinsics
     * @param dist_coeffs Distortion coefficients (can be empty)
     * @param marker_size_cm Physical marker side length in cm
     * @param max_reproj_error Max reprojection error threshold
     */
    ArucoDetector(const cv::Mat& camera_matrix, const cv::Mat& dist_coeffs,
                  double marker_size_cm = 5.0, double max_reproj_error = 3.0);

    /// Detect markers in frame
    std::vector<ArucoResult> detect(const cv::Mat& frame) const;

    /// Detect with multi-scale fallback (scale 1x, 2x, 3x, ...)
    std::vector<ArucoResult> detect_with_fallback(const cv::Mat& frame,
                                                   int max_scale = 4) const;

    /// Draw detected markers and distance info on frame
    cv::Mat annotate_frame(const cv::Mat& frame,
                           const std::vector<ArucoResult>& results) const;

    /// Get the closest marker with lowest reprojection error
    std::optional<BestDistance> get_best_distance(
        const std::vector<ArucoResult>& results) const;

    /// Override camera matrix (used when Moildev generates new intrinsics)
    void set_camera_matrix(const cv::Mat& camera_matrix);

    /// Get current camera matrix
    cv::Mat get_camera_matrix() const { return camera_matrix_.clone(); }

private:
    cv::Mat camera_matrix_;
    cv::Mat dist_coeffs_;
    double marker_size_cm_;
    double max_reproj_error_;
    cv::aruco::Dictionary dictionary_;
    cv::aruco::DetectorParameters params_;

    /// Estimate pose (solvePnP) for a detected marker
    ArucoResult estimate_pose(const std::vector<cv::Point2f>& corners,
                              int id) const;

    /// Compute reprojection error for a pose estimate
    double compute_reprojection_error(const std::vector<cv::Point2f>& corners,
                                      const cv::Vec3d& rvec,
                                      const cv::Vec3d& tvec) const;

    /// Convert rotation vector to euler angles (degrees)
    static cv::Vec3d rvec_to_euler(const cv::Vec3d& rvec);
};

} // namespace fusion
