/**
 * @file aruco_detector.cpp
 * @brief ArUco marker detection and pose estimation implementation.
 *
 * Port of Python 06_aruco_marker/aruco_detector.py.
 */

#include "aruco_detector.h"
#include "image_preprocess.h"
#include <opencv2/imgproc.hpp>
#include <opencv2/calib3d.hpp>
#include <algorithm>
#include <cmath>
#include <iostream>

namespace fusion {

ArucoDetector::ArucoDetector(const cv::Mat& camera_matrix,
                             const cv::Mat& dist_coeffs,
                             double marker_size_cm,
                             double max_reproj_error)
    : camera_matrix_(camera_matrix.clone()),
      dist_coeffs_(dist_coeffs.empty() ? cv::Mat::zeros(5, 1, CV_64F) : dist_coeffs.clone()),
      marker_size_cm_(marker_size_cm),
      max_reproj_error_(max_reproj_error)
{
    dictionary_ = cv::aruco::getPredefinedDictionary(cv::aruco::DICT_4X4_50);
    params_ = cv::aruco::DetectorParameters();

    // Optimized detection parameters (same as Python)
    params_.adaptiveThreshWinSizeMin = 3;
    params_.adaptiveThreshWinSizeMax = 23;
    params_.adaptiveThreshWinSizeStep = 5;
    params_.minMarkerPerimeterRate = 0.02;
    params_.maxMarkerPerimeterRate = 4.0;
    params_.polygonalApproxAccuracyRate = 0.05;
    params_.cornerRefinementMethod = cv::aruco::CORNER_REFINE_SUBPIX;
}

std::vector<ArucoResult> ArucoDetector::detect(const cv::Mat& frame) const {
    if (frame.empty()) return {};

    cv::Mat gray;
    if (frame.channels() == 3) {
        cv::cvtColor(frame, gray, cv::COLOR_BGR2GRAY);
    } else {
        gray = frame;
    }

    std::vector<int> ids;
    std::vector<std::vector<cv::Point2f>> corners, rejected;
    cv::aruco::ArucoDetector aruco_det(dictionary_, params_);
    aruco_det.detectMarkers(gray, corners, ids, rejected);

    std::vector<ArucoResult> results;
    results.reserve(ids.size());

    for (size_t i = 0; i < ids.size(); ++i) {
        auto result = estimate_pose(corners[i], ids[i]);
        if (result.reprojection_error <= max_reproj_error_) {
            results.push_back(std::move(result));
        }
    }

    return results;
}

std::vector<ArucoResult> ArucoDetector::detect_with_fallback(
    const cv::Mat& frame, int max_scale) const
{
    // Strategy 1: Raw frame
    auto results = detect(frame);
    if (!results.empty()) return results;

    // Strategy 2: CLAHE enhanced
    cv::Mat enhanced = apply_clahe(frame);
    results = detect(enhanced);
    if (!results.empty()) return results;

    // Strategy 3: Histogram equalized
    cv::Mat gray;
    if (frame.channels() == 3) {
        cv::cvtColor(frame, gray, cv::COLOR_BGR2GRAY);
    } else {
        gray = frame.clone();
    }
    cv::equalizeHist(gray, gray);
    results = detect(gray);
    if (!results.empty()) return results;

    // Strategy 4: Multi-scale upscale
    for (int scale = 2; scale <= max_scale; ++scale) {
        cv::Mat upscaled;
        cv::resize(frame, upscaled, cv::Size(), scale, scale, cv::INTER_CUBIC);
        results = detect(upscaled);
        if (!results.empty()) {
            // Scale corners back to original resolution
            for (auto& r : results) {
                for (auto& pt : r.corners) {
                    pt.x /= scale;
                    pt.y /= scale;
                }
                // Re-estimate pose at original resolution
                r = estimate_pose(r.corners, r.id);
            }
            return results;
        }
    }

    return {};
}

ArucoResult ArucoDetector::estimate_pose(
    const std::vector<cv::Point2f>& corners, int id) const
{
    ArucoResult result;
    result.id = id;
    result.corners = corners;

    // 3D object points (marker corners in marker frame)
    float half = static_cast<float>(marker_size_cm_ / 2.0);
    std::vector<cv::Point3f> obj_pts = {
        {-half,  half, 0},
        { half,  half, 0},
        { half, -half, 0},
        {-half, -half, 0}
    };

    cv::Vec3d rvec, tvec;
    cv::solvePnP(obj_pts, corners, camera_matrix_, dist_coeffs_, rvec, tvec);

    result.rvec = rvec;
    result.tvec = tvec;
    result.distance_cm = cv::norm(tvec);
    result.euler_deg = rvec_to_euler(rvec);
    result.reprojection_error = compute_reprojection_error(corners, rvec, tvec);

    return result;
}

double ArucoDetector::compute_reprojection_error(
    const std::vector<cv::Point2f>& corners,
    const cv::Vec3d& rvec, const cv::Vec3d& tvec) const
{
    float half = static_cast<float>(marker_size_cm_ / 2.0);
    std::vector<cv::Point3f> obj_pts = {
        {-half,  half, 0},
        { half,  half, 0},
        { half, -half, 0},
        {-half, -half, 0}
    };

    std::vector<cv::Point2f> projected;
    cv::projectPoints(obj_pts, rvec, tvec, camera_matrix_, dist_coeffs_, projected);

    double total_error = 0;
    for (size_t i = 0; i < 4; ++i) {
        total_error += cv::norm(corners[i] - projected[i]);
    }
    return total_error / 4.0;
}

cv::Vec3d ArucoDetector::rvec_to_euler(const cv::Vec3d& rvec) {
    cv::Mat rot_mat;
    cv::Rodrigues(rvec, rot_mat);

    double sy = std::sqrt(rot_mat.at<double>(0, 0) * rot_mat.at<double>(0, 0) +
                          rot_mat.at<double>(1, 0) * rot_mat.at<double>(1, 0));

    double roll, pitch, yaw;
    if (sy > 1e-6) {
        roll  = std::atan2(rot_mat.at<double>(2, 1), rot_mat.at<double>(2, 2));
        pitch = std::atan2(-rot_mat.at<double>(2, 0), sy);
        yaw   = std::atan2(rot_mat.at<double>(1, 0), rot_mat.at<double>(0, 0));
    } else {
        roll  = std::atan2(-rot_mat.at<double>(1, 2), rot_mat.at<double>(1, 1));
        pitch = std::atan2(-rot_mat.at<double>(2, 0), sy);
        yaw   = 0;
    }

    return {roll * 180.0 / CV_PI, pitch * 180.0 / CV_PI, yaw * 180.0 / CV_PI};
}

cv::Mat ArucoDetector::annotate_frame(const cv::Mat& frame,
                                       const std::vector<ArucoResult>& results) const {
    cv::Mat out = frame.clone();

    for (const auto& r : results) {
        // Draw marker outline
        std::vector<std::vector<cv::Point2f>> marker_corners = {r.corners};
        std::vector<int> marker_ids = {r.id};
        cv::aruco::drawDetectedMarkers(out, marker_corners, marker_ids);

        // Draw distance text
        cv::Point2f center(0, 0);
        for (const auto& pt : r.corners) center += pt;
        center *= 0.25f;

        char buf[64];
        std::snprintf(buf, sizeof(buf), "ID:%d %.1fcm", r.id, r.distance_cm);
        cv::putText(out, buf, cv::Point(center.x, center.y - 10),
                    cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 255, 0), 2);
    }

    return out;
}

std::optional<BestDistance> ArucoDetector::get_best_distance(
    const std::vector<ArucoResult>& results) const
{
    if (results.empty()) return std::nullopt;

    // Find marker with lowest reprojection error
    const auto& best = *std::min_element(results.begin(), results.end(),
        [](const ArucoResult& a, const ArucoResult& b) {
            return a.reprojection_error < b.reprojection_error;
        });

    return BestDistance{best.distance_cm, best.id, best.reprojection_error};
}

void ArucoDetector::set_camera_matrix(const cv::Mat& camera_matrix) {
    camera_matrix_ = camera_matrix.clone();
}

} // namespace fusion
