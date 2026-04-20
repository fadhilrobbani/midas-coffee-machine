/**
 * pipeline.cpp — Pipeline Orchestrator
 *
 * Main processing loop: undistort → YOLO → methods → fusion → smoothing.
 */

#include "pipeline.h"
#include "method_a.h"
#include "method_b.h"
#include "method_c.h"
#include "fusion.h"

#include <iostream>
#include <algorithm>
#include <numeric>
#include <cmath>
#include <opencv2/imgproc.hpp>
#include <opencv2/calib3d.hpp>

namespace tray {

TrayDistancePipeline::TrayDistancePipeline(
    const TrayConfig& cfg, bool no_yolo,
    const std::string& method, bool use_gpu)
    : cfg_(cfg), no_yolo_(no_yolo) {

    // Normalize method string
    method_ = method;
    for (auto& c : method_) c = static_cast<char>(std::toupper(c));

    if (method_ != "AUTO" && method_ != "A" && method_ != "B" && method_ != "C") {
        throw std::runtime_error("Method must be AUTO, A, B, or C");
    }

    // Initialize detector
    if (!no_yolo) {
        detector_ = IDetector::create(cfg_.weights_path, use_gpu);
    } else {
        std::cout << "[INFO] Mode --no-yolo: YOLO disabled, using full frame."
                  << std::endl;
    }

    std::cout << "[INFO] Active method: " << method_ << std::endl;
}


void TrayDistancePipeline::init_undistort_maps(int h, int w) {
    if (maps_initialized_) return;

    cv::Mat new_K = cv::getOptimalNewCameraMatrix(
        cfg_.camera_matrix, cfg_.dist_coeffs,
        cv::Size(w, h), 1, cv::Size(w, h));

    cv::initUndistortRectifyMap(
        cfg_.camera_matrix, cfg_.dist_coeffs,
        cv::Mat(), new_K, cv::Size(w, h), CV_16SC2,
        map1_, map2_);

    maps_initialized_ = true;
}


cv::Mat TrayDistancePipeline::undistort(const cv::Mat& frame) {
    init_undistort_maps(frame.rows, frame.cols);
    cv::Mat result;
    cv::remap(frame, result, map1_, map2_, cv::INTER_LINEAR);
    return result;
}


void TrayDistancePipeline::run_yolo(
    const cv::Mat& frame,
    int tray_bbox[4], cv::Mat& tray_mask,
    int glass_bbox[4],
    bool& found_tray, bool& found_glass) {

    found_tray = false;
    found_glass = false;

    if (!detector_) return;

    auto boxes = detector_->detect(frame);
    int h = frame.rows, w = frame.cols;

    if (boxes.empty()) return;

    // Sort by area (largest first)
    std::sort(boxes.begin(), boxes.end(),
              [](const DetectionBox& a, const DetectionBox& b) {
                  int area_a = (a.x2 - a.x1) * (a.y2 - a.y1);
                  int area_b = (b.x2 - b.x1) * (b.y2 - b.y1);
                  return area_a > area_b;
              });

    if (boxes.size() == 1) {
        // Single detection = cup; tray = full frame
        glass_bbox[0] = boxes[0].x1;
        glass_bbox[1] = boxes[0].y1;
        glass_bbox[2] = boxes[0].x2;
        glass_bbox[3] = boxes[0].y2;
        found_glass = true;

        tray_bbox[0] = 0; tray_bbox[1] = 0;
        tray_bbox[2] = w; tray_bbox[3] = h;
        found_tray = true;
    } else {
        // Largest = tray, second = glass
        tray_bbox[0] = boxes[0].x1;
        tray_bbox[1] = boxes[0].y1;
        tray_bbox[2] = boxes[0].x2;
        tray_bbox[3] = boxes[0].y2;
        found_tray = true;

        glass_bbox[0] = boxes[1].x1;
        glass_bbox[1] = boxes[1].y1;
        glass_bbox[2] = boxes[1].x2;
        glass_bbox[3] = boxes[1].y2;
        found_glass = true;
    }

    // Create tray mask from bbox
    if (found_tray) {
        tray_mask = cv::Mat::zeros(h, w, CV_8U);
        cv::rectangle(tray_mask,
                      cv::Point(tray_bbox[0], tray_bbox[1]),
                      cv::Point(tray_bbox[2], tray_bbox[3]),
                      cv::Scalar(255), cv::FILLED);
    }
}


FusedResult TrayDistancePipeline::process_frame(const cv::Mat& frame) {
    int h = frame.rows, w = frame.cols;

    // ── 1. Undistort ────────────────────────────────────────────────────
    cv::Mat frame_u = undistort(frame);

    // ── 2. ROI Detection ────────────────────────────────────────────────
    int tray_bbox[4] = {0, 0, w, h};
    int glass_bbox[4] = {0};
    cv::Mat tray_mask;
    bool found_tray = false, found_glass = false;

    if (no_yolo_) {
        tray_mask = cv::Mat(h, w, CV_8U, cv::Scalar(255));
        found_tray = true;
    } else {
        // YOLO caching
        frame_count_++;
        if (frame_count_ % yolo_interval_ == 1 || !has_cached_tray_) {
            run_yolo(frame_u, tray_bbox, tray_mask, glass_bbox,
                     found_tray, found_glass);

            // Cache results
            std::copy(std::begin(tray_bbox), std::end(tray_bbox),
                      std::begin(cached_tray_bbox_));
            std::copy(std::begin(glass_bbox), std::end(glass_bbox),
                      std::begin(cached_glass_bbox_));
            cached_tray_mask_ = tray_mask.clone();
            has_cached_tray_ = found_tray;
            has_cached_glass_ = found_glass;
        } else {
            std::copy(std::begin(cached_tray_bbox_), std::end(cached_tray_bbox_),
                      std::begin(tray_bbox));
            std::copy(std::begin(cached_glass_bbox_), std::end(cached_glass_bbox_),
                      std::begin(glass_bbox));
            tray_mask = cached_tray_mask_.clone();
            found_tray = has_cached_tray_;
            found_glass = has_cached_glass_;
        }

        if (!found_tray) {
            FusedResult fail;
            fail.method_used = "NONE";
            fail.status = "INSUFFICIENT_DATA";
            fail.notes = "YOLO tidak mendeteksi tray";
            return fail;
        }
    }

    // ── 3. Run methods ──────────────────────────────────────────────────
    std::optional<MethodAResult> result_a;
    MethodBResult result_b;
    std::optional<MethodCResult> result_c;

    int* glass_ptr = found_glass ? glass_bbox : nullptr;

    if (method_ == "AUTO" || method_ == "B") {
        result_b = estimate_D_tray_method_B(
            frame_u, tray_mask, glass_ptr,
            cfg_.f_pixel, cfg_.P_real_cm, cfg_.theta_tilt_rad,
            cfg_.canny_low, cfg_.canny_high,
            cfg_.hough_threshold, cfg_.hough_min_line_length,
            cfg_.hough_max_line_gap,
            cfg_.horizontal_angle_tol_deg, cfg_.min_lines_per_zone,
            cfg_.D_min_cm, cfg_.D_max_cm, cfg_.ref_slats);
    }

    if (method_ == "AUTO" || method_ == "C") {
        result_c = estimate_D_tray_method_C(
            tray_mask, cfg_.camera_matrix, cfg_.dist_coeffs,
            cfg_.W_tray_cm, cfg_.L_tray_cm, cfg_.theta_tilt_rad,
            cfg_.D_min_cm, cfg_.D_max_cm);
    }

    if (method_ == "AUTO" || method_ == "A") {
        result_a = estimate_D_tray_method_A(
            tray_bbox[0], tray_bbox[1], tray_bbox[2], tray_bbox[3],
            cfg_.f_pixel, cfg_.W_tray_cm, cfg_.theta_tilt_rad,
            w, cfg_.D_min_cm, cfg_.D_max_cm);
    }

    // ── 4. Fuse or single-method ────────────────────────────────────────
    FusedResult fused;
    if (method_ == "AUTO") {
        fused = fuse_results(result_a, result_b, result_c);
    } else {
        fused = build_single_result(method_, result_a, result_b, result_c);
    }

    // Store bbox info
    std::copy(std::begin(tray_bbox), std::end(tray_bbox),
              std::begin(fused.tray_bbox));
    fused.has_tray_bbox = found_tray;
    if (found_glass) {
        std::copy(std::begin(glass_bbox), std::end(glass_bbox),
                  std::begin(fused.glass_bbox));
        fused.has_glass = true;
    }

    // ── 5. Temporal smoothing & outlier rejection ───────────────────────
    double raw_d = fused.D_tray_cm;
    if (raw_d > 0) {
        // Spike rejection
        if (d_tray_history_.size() >= 3) {
            auto sorted = std::vector<double>(d_tray_history_.begin(),
                                               d_tray_history_.end());
            std::sort(sorted.begin(), sorted.end());
            double current_median = sorted[sorted.size() / 2];

            if (raw_d > current_median + SPIKE_THRESHOLD) {
                std::string note = fused.notes.empty() ? "" : fused.notes + " | ";
                note += "Spike detected (" + std::to_string(raw_d)
                        + "->" + std::to_string(current_median) + ")";
                fused.notes = note;
                raw_d = current_median;
            }
        }

        d_tray_history_.push_back(raw_d);
        if (d_tray_history_.size() > HISTORY_SIZE)
            d_tray_history_.pop_front();

        if (d_tray_history_.size() >= 3) {
            auto sorted = std::vector<double>(d_tray_history_.begin(),
                                               d_tray_history_.end());
            std::sort(sorted.begin(), sorted.end());
            double smoothed = sorted[sorted.size() / 2];
            fused.D_tray_cm = std::round(smoothed * 10.0) / 10.0;
        }
    }

    return fused;
}


cv::Mat TrayDistancePipeline::annotate_frame(
    const cv::Mat& frame, const FusedResult& result) {

    cv::Mat vis = frame.clone();
    int h = vis.rows, w = vis.cols;

    // ── Tray bbox ───────────────────────────────────────────────────────
    if (result.has_tray_bbox) {
        cv::rectangle(vis,
                      cv::Point(result.tray_bbox[0], result.tray_bbox[1]),
                      cv::Point(result.tray_bbox[2], result.tray_bbox[3]),
                      cv::Scalar(255, 200, 0), 2);
        cv::putText(vis, "TRAY",
                    cv::Point(result.tray_bbox[0], result.tray_bbox[1] - 8),
                    cv::FONT_HERSHEY_SIMPLEX, 0.6, cv::Scalar(255, 200, 0), 2);
    }

    // ── Glass bbox ──────────────────────────────────────────────────────
    if (result.has_glass) {
        cv::rectangle(vis,
                      cv::Point(result.glass_bbox[0], result.glass_bbox[1]),
                      cv::Point(result.glass_bbox[2], result.glass_bbox[3]),
                      cv::Scalar(0, 255, 255), 2);
        cv::putText(vis, "GLASS",
                    cv::Point(result.glass_bbox[0], result.glass_bbox[1] - 8),
                    cv::FONT_HERSHEY_SIMPLEX, 0.6, cv::Scalar(0, 255, 255), 2);
    }

    // ── Clustered lines (green) ─────────────────────────────────────────
    const auto& clustered = result.detail_b.debug_clustered;
    for (size_t i = 0; i < clustered.size(); i++) {
        cv::line(vis,
                 cv::Point(clustered[i][0], clustered[i][1]),
                 cv::Point(clustered[i][2], clustered[i][3]),
                 cv::Scalar(0, 255, 0), 2);
        cv::putText(vis, "#" + std::to_string(i + 1),
                    cv::Point(clustered[i][0] - 25, clustered[i][1] + 4),
                    cv::FONT_HERSHEY_SIMPLEX, 0.35, cv::Scalar(0, 255, 0), 1);
    }

    // ── Gap visualization ───────────────────────────────────────────────
    if (clustered.size() > 1) {
        std::vector<double> y_mids;
        for (const auto& l : clustered)
            y_mids.push_back((l[1] + l[3]) / 2.0);
        std::sort(y_mids.begin(), y_mids.end());

        for (size_t i = 0; i + 1 < y_mids.size(); i++) {
            double gap = y_mids[i + 1] - y_mids[i];
            int mid_y = static_cast<int>((y_mids[i] + y_mids[i + 1]) / 2);

            cv::line(vis, cv::Point(w - 50, static_cast<int>(y_mids[i])),
                     cv::Point(w - 50, static_cast<int>(y_mids[i + 1])),
                     cv::Scalar(0, 200, 255), 1);
            cv::circle(vis, cv::Point(w - 50, static_cast<int>(y_mids[i])),
                       3, cv::Scalar(0, 200, 255), -1);
            cv::circle(vis, cv::Point(w - 50, static_cast<int>(y_mids[i + 1])),
                       3, cv::Scalar(0, 200, 255), -1);

            char buf[32];
            std::snprintf(buf, sizeof(buf), "%.1fpx", gap);
            cv::putText(vis, buf, cv::Point(w - 48, mid_y + 4),
                        cv::FONT_HERSHEY_SIMPLEX, 0.35,
                        cv::Scalar(0, 200, 255), 1);
        }
    }

    // ── Corners from Method C ───────────────────────────────────────────
    for (const auto& pt : result.detail_c.corners) {
        cv::circle(vis, cv::Point(static_cast<int>(pt.x),
                                   static_cast<int>(pt.y)),
                   6, cv::Scalar(255, 0, 255), -1);
    }

    // ── Overlay text ────────────────────────────────────────────────────
    int y_off = 30;

    if (result.D_tray_cm > 0) {
        char buf[64];
        std::snprintf(buf, sizeof(buf), "D_tray: %.1f cm", result.D_tray_cm);
        cv::putText(vis, buf, cv::Point(10, y_off),
                    cv::FONT_HERSHEY_SIMPLEX, 0.8, cv::Scalar(0, 255, 0), 2);
    } else {
        cv::putText(vis, "D_tray: N/A", cv::Point(10, y_off),
                    cv::FONT_HERSHEY_SIMPLEX, 0.8, cv::Scalar(0, 0, 255), 2);
    }

    y_off += 30;
    {
        char buf[128];
        std::snprintf(buf, sizeof(buf), "Method: %s | Conf: %.2f",
                      result.method_used.c_str(), result.confidence);
        cv::putText(vis, buf, cv::Point(10, y_off),
                    cv::FONT_HERSHEY_SIMPLEX, 0.6,
                    cv::Scalar(200, 200, 200), 1);
    }

    y_off += 25;
    {
        auto color = (result.status == "OK")
                     ? cv::Scalar(0, 255, 0) : cv::Scalar(0, 165, 255);
        cv::putText(vis, "Status: " + result.status, cv::Point(10, y_off),
                    cv::FONT_HERSHEY_SIMPLEX, 0.6, color, 1);
    }

    y_off += 25;
    {
        char buf[128];
        std::snprintf(buf, sizeof(buf), "L: %.1fcm (%ds) | R: %.1fcm (%ds)",
                      result.D_left_cm, result.lines_left,
                      result.D_right_cm, result.lines_right);
        cv::putText(vis, buf, cv::Point(10, y_off),
                    cv::FONT_HERSHEY_SIMPLEX, 0.55,
                    cv::Scalar(255, 255, 0), 1);
    }

    if (!result.notes.empty()) {
        y_off += 25;
        std::string display_notes = result.notes.substr(0, 80);
        cv::putText(vis, display_notes, cv::Point(10, y_off),
                    cv::FONT_HERSHEY_SIMPLEX, 0.45,
                    cv::Scalar(100, 100, 255), 1);
    }

    return vis;
}

} // namespace tray
