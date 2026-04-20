/**
 * method_c.cpp — Metode C: Homografi 4 Corner + PnP (Backup)
 *
 * Direct port dari method_c.py.
 */

#include "method_c.h"
#include <cmath>
#include <algorithm>
#include <opencv2/imgproc.hpp>
#include <opencv2/calib3d.hpp>

namespace tray {

namespace {

// Sort 4 corners: TL, TR, BR, BL
std::vector<cv::Point2f> sort_corners_clockwise(
    const std::vector<cv::Point2f>& pts) {

    auto sorted = pts;

    // Sort by x
    std::sort(sorted.begin(), sorted.end(),
              [](const cv::Point2f& a, const cv::Point2f& b) {
                  return a.x < b.x;
              });

    // Left pair (first 2), right pair (last 2)
    cv::Point2f left[2]  = {sorted[0], sorted[1]};
    cv::Point2f right[2] = {sorted[2], sorted[3]};

    // Sort each pair by y (top first)
    if (left[0].y > left[1].y) std::swap(left[0], left[1]);
    if (right[0].y > right[1].y) std::swap(right[0], right[1]);

    return {left[0], right[0], right[1], left[1]};  // TL TR BR BL
}

double compute_reproj_error(
    const std::vector<cv::Point3f>& obj_pts,
    const std::vector<cv::Point2f>& img_pts,
    const cv::Mat& rvec, const cv::Mat& tvec,
    const cv::Mat& K, const cv::Mat& dist) {

    std::vector<cv::Point2f> projected;
    cv::projectPoints(obj_pts, rvec, tvec, K, dist, projected);

    double total = 0;
    for (size_t i = 0; i < projected.size(); i++) {
        double dx = img_pts[i].x - projected[i].x;
        double dy = img_pts[i].y - projected[i].y;
        total += std::sqrt(dx * dx + dy * dy);
    }
    return total / projected.size();
}

} // anonymous namespace


std::optional<MethodCResult> estimate_D_tray_method_C(
    const cv::Mat& tray_mask,
    const cv::Mat& K,
    const cv::Mat& dist_coeffs,
    double W_tray_cm, double L_tray_cm,
    double theta_tilt_rad,
    double D_min, double D_max) {

    if (tray_mask.empty() || cv::countNonZero(tray_mask) < 500)
        return std::nullopt;

    // ── Extract contour ─────────────────────────────────────────────────
    cv::Mat mask_u8;
    cv::threshold(tray_mask, mask_u8, 127, 255, cv::THRESH_BINARY);
    mask_u8.convertTo(mask_u8, CV_8U);

    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(mask_u8, contours, cv::RETR_EXTERNAL,
                     cv::CHAIN_APPROX_SIMPLE);
    if (contours.empty()) return std::nullopt;

    // Largest contour
    auto& cnt = *std::max_element(contours.begin(), contours.end(),
        [](const auto& a, const auto& b) {
            return cv::contourArea(a) < cv::contourArea(b);
        });

    double peri = cv::arcLength(cnt, true);

    // ── approxPolyDP → 4 points ─────────────────────────────────────────
    std::vector<cv::Point> approx;
    bool found = false;
    for (double eps : {0.02, 0.03, 0.04, 0.05, 0.015}) {
        cv::approxPolyDP(cnt, approx, eps * peri, true);
        if (approx.size() == 4) { found = true; break; }
    }
    if (!found || approx.size() != 4) return std::nullopt;

    // ── Sort corners ────────────────────────────────────────────────────
    std::vector<cv::Point2f> img_pts_raw;
    for (const auto& p : approx)
        img_pts_raw.emplace_back(static_cast<float>(p.x),
                                 static_cast<float>(p.y));

    auto img_pts = sort_corners_clockwise(img_pts_raw);

    // ── Object points 3D ────────────────────────────────────────────────
    float W = static_cast<float>(W_tray_cm);
    float L = static_cast<float>(L_tray_cm);
    std::vector<cv::Point3f> obj_pts = {
        {0, 0, 0}, {W, 0, 0}, {W, L, 0}, {0, L, 0}
    };

    // ── solvePnP ────────────────────────────────────────────────────────
    cv::Mat K64, dist64;
    K.convertTo(K64, CV_64F);
    dist_coeffs.convertTo(dist64, CV_64F);

    cv::Mat rvec, tvec;
    bool ok = cv::solvePnP(obj_pts, img_pts, K64, dist64, rvec, tvec);
    if (!ok) return std::nullopt;

    // ── Extract D_tray ──────────────────────────────────────────────────
    double D_raw  = std::abs(tvec.at<double>(2, 0));
    double D_tray = D_raw * std::cos(theta_tilt_rad);

    double reproj_err = compute_reproj_error(obj_pts, img_pts, rvec, tvec,
                                              K64, dist64);

    // ── Range validation ────────────────────────────────────────────────
    if (D_tray < D_min || D_tray > D_max) {
        MethodCResult r;
        r.D_tray_cm = std::round(D_tray * 100.0) / 100.0;
        r.confidence = 0.0;
        r.status = "OUT_OF_RANGE";
        r.reprojection_error = std::round(reproj_err * 100.0) / 100.0;
        r.corners = img_pts;
        r.notes = "D_tray out of range";
        return r;
    }

    // ── Confidence scoring ──────────────────────────────────────────────
    double confidence;
    if (reproj_err < 2.0)
        confidence = 0.92 + 0.08 * std::max(0.0, 1.0 - reproj_err / 2.0);
    else if (reproj_err < 5.0)
        confidence = 0.75 + 0.16 * std::max(0.0, 1.0 - (reproj_err - 2.0) / 3.0);
    else {
        confidence = 0.50 + 0.24 * std::max(0.0, 1.0 - (reproj_err - 5.0) / 10.0);
        confidence = std::max(0.50, confidence);
    }

    MethodCResult r;
    r.D_tray_cm = std::round(D_tray * 100.0) / 100.0;
    r.confidence = std::round(std::min(confidence, 1.0) * 1000.0) / 1000.0;
    r.status = "OK";
    r.reprojection_error = std::round(reproj_err * 100.0) / 100.0;
    r.corners = img_pts;
    r.valid = true;
    return r;
}

} // namespace tray
