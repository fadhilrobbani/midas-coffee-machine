/**
 * method_b.cpp — Metode B: Horizontal Slat Pitch (PRIMARY)
 *
 * Direct port dari method_b.py — the core detection algorithm.
 */

#include "method_b.h"
#include <cmath>
#include <algorithm>
#include <numeric>
#include <opencv2/imgproc.hpp>

namespace tray {

namespace {

// ── Internal line struct ────────────────────────────────────────────────
struct HLine {
    int x1, y1, x2, y2;
    double y_mid, x_mid, length;
};

struct MergedLine {
    double y_mid, x_mid;
    int x1, x2, y1, y2;
    int count;
    double length;
};


// ── Filter horizontal lines ─────────────────────────────────────────────
std::vector<HLine> filter_horizontal(const std::vector<cv::Vec4i>& lines,
                                      double angle_tol_deg) {
    std::vector<HLine> result;
    for (const auto& l : lines) {
        int x1 = l[0], y1 = l[1], x2 = l[2], y2 = l[3];
        double angle = std::abs(std::atan2(y2 - y1, x2 - x1) * 180.0 / M_PI);
        if (angle < angle_tol_deg || angle > (180.0 - angle_tol_deg)) {
            HLine h;
            h.x1 = x1; h.y1 = y1; h.x2 = x2; h.y2 = y2;
            h.y_mid = (y1 + y2) / 2.0;
            h.x_mid = (x1 + x2) / 2.0;
            h.length = std::hypot(x2 - x1, y2 - y1);
            result.push_back(h);
        }
    }
    return result;
}


// ── Cluster nearby lines + NMS ──────────────────────────────────────────
std::vector<MergedLine> cluster_lines(const std::vector<HLine>& h_lines,
                                       double cluster_gap = 8.0) {
    if (h_lines.empty()) return {};

    // Sort by y_mid
    auto sorted = h_lines;
    std::sort(sorted.begin(), sorted.end(),
              [](const HLine& a, const HLine& b) { return a.y_mid < b.y_mid; });

    // Cluster
    std::vector<std::vector<const HLine*>> clusters;
    std::vector<const HLine*> current = {&sorted[0]};

    for (size_t i = 1; i < sorted.size(); i++) {
        if (sorted[i].y_mid - current[0]->y_mid <= cluster_gap) {
            current.push_back(&sorted[i]);
        } else {
            clusters.push_back(current);
            current = {&sorted[i]};
        }
    }
    clusters.push_back(current);

    // Merge clusters (weighted average)
    std::vector<MergedLine> merged;
    for (const auto& cluster : clusters) {
        double total_w = 0;
        for (const auto* l : cluster) total_w += l->length;
        if (total_w < 1e-6) continue;

        double y_avg = 0, x_avg = 0;
        for (const auto* l : cluster) {
            y_avg += l->y_mid * l->length;
            x_avg += l->x_mid * l->length;
        }
        y_avg /= total_w;
        x_avg /= total_w;

        // Find longest line for x extent
        const HLine* longest = *std::max_element(
            cluster.begin(), cluster.end(),
            [](const HLine* a, const HLine* b) { return a->length < b->length; });

        MergedLine m;
        m.y_mid = y_avg;
        m.x_mid = x_avg;
        m.x1 = longest->x1;
        m.x2 = longest->x2;
        m.y1 = static_cast<int>(std::round(y_avg));
        m.y2 = static_cast<int>(std::round(y_avg));
        m.count = static_cast<int>(cluster.size());
        m.length = total_w;
        merged.push_back(m);
    }

    // NMS — Suppress lines that are too close vertically
    if (merged.empty()) return {};

    std::sort(merged.begin(), merged.end(),
              [](const MergedLine& a, const MergedLine& b) {
                  return a.length > b.length;
              });

    std::vector<MergedLine> nms_result;
    constexpr double nms_thresh = 10.0;

    for (const auto& line : merged) {
        bool keep = true;
        for (const auto& kept : nms_result) {
            if (std::abs(line.y_mid - kept.y_mid) <= nms_thresh) {
                keep = false;
                break;
            }
        }
        if (keep) nms_result.push_back(line);
    }

    // Sort top-to-bottom
    std::sort(nms_result.begin(), nms_result.end(),
              [](const MergedLine& a, const MergedLine& b) {
                  return a.y_mid < b.y_mid;
              });

    return nms_result;
}


// ── Split lines by zone (left/right of glass) ───────────────────────────
void split_by_zone(const std::vector<HLine>& h_lines,
                   const int* glass_bbox, int frame_width,
                   std::vector<HLine>& left, std::vector<HLine>& right) {
    int left_boundary, right_boundary;

    if (glass_bbox) {
        left_boundary = glass_bbox[0] - 10;
        right_boundary = glass_bbox[2] + 10;
    } else {
        int mid = frame_width / 2;
        left_boundary = mid;
        right_boundary = mid;
    }

    for (const auto& line : h_lines) {
        if (glass_bbox) {
            if (line.x_mid < left_boundary) left.push_back(line);
            else if (line.x_mid > right_boundary) right.push_back(line);
        } else {
            if (line.x_mid < left_boundary) left.push_back(line);
            else right.push_back(line);
        }
    }
}


// ── Compute zone D via 1D Voting (Autocorrelation) ─────────────────────
struct ZoneResult {
    double D_tray = 0;
    int n_lines = 0;
    double pitch = 0;
    bool valid = false;
};

ZoneResult compute_zone_D(const std::vector<double>& y_mids,
                           double f_pixel, double P_real_cm,
                           double theta_tilt_rad,
                           double D_min, double D_max) {
    ZoneResult r;
    r.n_lines = static_cast<int>(y_mids.size());

    if (y_mids.size() < 2) return r;

    auto y_sorted = y_mids;
    std::sort(y_sorted.begin(), y_sorted.end());

    double constant = f_pixel * P_real_cm * std::cos(theta_tilt_rad);
    double pitch_min = constant / 45.0;
    double pitch_max = constant / 10.0;

    // Collect all valid diffs
    std::vector<double> all_diffs;
    for (size_t i = 0; i < y_sorted.size(); i++) {
        for (size_t j = i + 1; j < std::min(i + 8, y_sorted.size()); j++) {
            double d = y_sorted[j] - y_sorted[i];
            if (d >= pitch_min && d <= pitch_max)
                all_diffs.push_back(d);
        }
    }

    if (all_diffs.empty()) return r;

    // Voting for true pitch
    double best_candidate = 0;
    int max_votes = -1;

    for (double candidate : all_diffs) {
        int votes = 0;
        for (double d : all_diffs) {
            if (std::abs(d - candidate) <= 2.0) votes++;
        }
        if (votes > max_votes ||
            (votes == max_votes && candidate > best_candidate)) {
            max_votes = votes;
            best_candidate = candidate;
        }
    }

    // Refine with supporters
    double sum = 0;
    int count = 0;
    for (double d : all_diffs) {
        if (std::abs(d - best_candidate) <= 2.0) {
            sum += d;
            count++;
        }
    }
    double p_avg = (count > 0) ? sum / count : 0;

    if (p_avg < 1.0) { r.pitch = p_avg; return r; }

    double D_tray = constant / p_avg;
    if (D_tray < D_min || D_tray > D_max) { r.pitch = p_avg; return r; }

    r.D_tray = std::round(D_tray * 100.0) / 100.0;
    r.pitch = p_avg;
    r.valid = true;
    return r;
}


// ── IQR pitch compute (fallback) ────────────────────────────────────────
double compute_pitch_iqr(const std::vector<double>& y_mids, int& n_valid) {
    n_valid = 0;
    if (y_mids.size() < 3) return 0;

    auto y_sorted = y_mids;
    std::sort(y_sorted.begin(), y_sorted.end());

    std::vector<double> gaps;
    for (size_t i = 1; i < y_sorted.size(); i++)
        gaps.push_back(y_sorted[i] - y_sorted[i - 1]);

    if (gaps.empty()) return 0;

    // Percentiles for IQR
    auto sorted_gaps = gaps;
    std::sort(sorted_gaps.begin(), sorted_gaps.end());
    size_t n = sorted_gaps.size();

    double q1 = sorted_gaps[n / 4];
    double q3 = sorted_gaps[(3 * n) / 4];
    double iqr = q3 - q1;

    std::vector<double> valid;
    if (iqr < 1e-6) {
        valid = sorted_gaps;
    } else {
        double lower = q1 - 1.5 * iqr;
        double upper = q3 + 1.5 * iqr;
        for (double g : sorted_gaps) {
            if (g >= lower && g <= upper) valid.push_back(g);
        }
    }

    if (valid.empty()) valid = sorted_gaps;

    n_valid = static_cast<int>(valid.size());
    std::sort(valid.begin(), valid.end());
    return valid[valid.size() / 2];  // median
}

} // anonymous namespace


// ══════════════════════════════════════════════════════════════════════════
//  PUBLIC: estimate_D_tray_method_B
// ══════════════════════════════════════════════════════════════════════════

MethodBResult estimate_D_tray_method_B(
    const cv::Mat& frame,
    const cv::Mat& tray_mask,
    const int* glass_bbox,
    double f_pixel, double P_real_cm, double theta_tilt_rad,
    int canny_low, int canny_high,
    int hough_threshold, int hough_min_line_length, int hough_max_line_gap,
    double angle_tol_deg, int min_lines,
    double D_min, double D_max, int ref_slats) {

    MethodBResult empty;

    int h = frame.rows, w = frame.cols;

    // ── Apply mask → enhance → edges ────────────────────────────────────
    cv::Mat mask_u8;
    cv::threshold(tray_mask, mask_u8, 0, 255, cv::THRESH_BINARY);
    mask_u8.convertTo(mask_u8, CV_8U);

    cv::Mat roi;
    cv::bitwise_and(frame, frame, roi, mask_u8);

    cv::Mat gray;
    cv::cvtColor(roi, gray, cv::COLOR_BGR2GRAY);

    // CLAHE
    auto clahe = cv::createCLAHE(2.0, cv::Size(8, 8));
    cv::Mat enhanced;
    clahe->apply(gray, enhanced);

    cv::Mat blurred;
    cv::GaussianBlur(enhanced, blurred, cv::Size(3, 3), 0);

    // Adaptive Canny
    double med = 0;
    {
        cv::Mat flat = blurred.reshape(1, 1);
        std::vector<uchar> vals(flat.begin<uchar>(), flat.end<uchar>());
        std::sort(vals.begin(), vals.end());
        med = vals[vals.size() / 2];
    }
    int c_low  = std::min(canny_low, std::max(5, static_cast<int>(0.66 * med)));
    int c_high = std::min(canny_high, std::min(255, static_cast<int>(1.33 * med)));

    cv::Mat edges;
    cv::Canny(blurred, edges, c_low, c_high);

    // ── Directional Gradient Masking ────────────────────────────────────
    cv::Mat sobel_y;
    cv::Sobel(blurred, sobel_y, CV_64F, 0, 1, 3);
    for (int r = 0; r < h; r++) {
        const double* sy = sobel_y.ptr<double>(r);
        uchar* ep = edges.ptr<uchar>(r);
        for (int c = 0; c < w; c++) {
            if (sy[c] < 0) ep[c] = 0;
        }
    }

    // ── Strict ROI mask (wing zones) ────────────────────────────────────
    int box_y1 = static_cast<int>(h * 0.33);
    int box_y2 = static_cast<int>(h * 0.79);
    int mid_x  = w / 2;
    int skip_radius = 80;
    int lx1 = std::max(0, mid_x - skip_radius - 200);
    int lx2 = std::max(0, mid_x - skip_radius);
    int rx1 = std::min(w, mid_x + skip_radius);
    int rx2 = std::min(w, rx1 + 200);

    cv::Mat strict_mask = cv::Mat::zeros(h, w, CV_8U);
    if (lx2 > lx1)
        strict_mask(cv::Rect(lx1, box_y1, lx2 - lx1, box_y2 - box_y1)) = 255;
    if (rx2 > rx1)
        strict_mask(cv::Rect(rx1, box_y1, rx2 - rx1, box_y2 - box_y1)) = 255;

    // Punch-out glass bbox
    if (glass_bbox) {
        int gm = 15;
        int gx1 = std::max(0, glass_bbox[0] - gm);
        int gy1 = std::max(0, glass_bbox[1] - gm);
        int gx2 = std::min(w, glass_bbox[2] + gm);
        int gy2 = std::min(h, glass_bbox[3] + gm);
        strict_mask(cv::Rect(gx1, gy1, gx2 - gx1, gy2 - gy1)) = 0;
    }

    cv::bitwise_and(edges, strict_mask, edges);

    // ── Hough Lines ─────────────────────────────────────────────────────
    std::vector<cv::Vec4i> raw_lines;
    cv::HoughLinesP(edges, raw_lines, 1, CV_PI / 180,
                    hough_threshold, hough_min_line_length, hough_max_line_gap);

    // ── Filter horizontal ───────────────────────────────────────────────
    auto h_lines = filter_horizontal(raw_lines, angle_tol_deg);

    // Save debug raw lines
    std::vector<cv::Vec4i> debug_raw;
    for (const auto& l : h_lines)
        debug_raw.push_back({l.x1, l.y1, l.x2, l.y2});

    if (static_cast<int>(h_lines.size()) < min_lines) {
        empty.notes = "Only " + std::to_string(h_lines.size())
                      + " horizontal lines (min=" + std::to_string(min_lines) + ")";
        empty.debug_lines = debug_raw;
        return empty;
    }

    // ── Split then cluster ──────────────────────────────────────────────
    std::vector<HLine> left_raw, right_raw;
    split_by_zone(h_lines, glass_bbox, w, left_raw, right_raw);

    auto left_merged  = cluster_lines(left_raw, 6.0);
    auto right_merged = cluster_lines(right_raw, 6.0);

    // Debug clustered lines
    std::vector<cv::Vec4i> debug_clustered;
    for (const auto& l : left_merged)
        debug_clustered.push_back({l.x1, l.y1, l.x2, l.y2});
    for (const auto& l : right_merged)
        debug_clustered.push_back({l.x1, l.y1, l.x2, l.y2});

    int total_merged = static_cast<int>(left_merged.size() + right_merged.size());
    if (total_merged == 0) {
        empty.notes = "Tidak ada sekat valid setelah clustering";
        empty.debug_lines = debug_raw;
        empty.debug_clustered = debug_clustered;
        return empty;
    }

    // ── Compute zone D ──────────────────────────────────────────────────
    std::vector<double> left_y, right_y;
    for (const auto& l : left_merged) left_y.push_back(l.y_mid);
    for (const auto& l : right_merged) right_y.push_back(l.y_mid);

    auto zl = compute_zone_D(left_y, f_pixel, P_real_cm, theta_tilt_rad, D_min, D_max);
    auto zr = compute_zone_D(right_y, f_pixel, P_real_cm, theta_tilt_rad, D_min, D_max);

    bool left_valid  = zl.valid && static_cast<int>(left_y.size()) >= min_lines;
    bool right_valid = zr.valid && static_cast<int>(right_y.size()) >= min_lines;

    double D_tray = 0;
    double D_left = left_valid ? zl.D_tray : 0;
    double D_right = right_valid ? zr.D_tray : 0;
    std::string status, notes;

    if (left_valid && right_valid) {
        D_tray = std::round((D_left + D_right) / 2.0 * 100.0) / 100.0;
        status = "OK";
    } else if (left_valid) {
        D_tray = D_left;
        status = "SINGLE_ZONE";
        notes = "Only left zone valid";
    } else if (right_valid) {
        D_tray = D_right;
        status = "SINGLE_ZONE";
        notes = "Only right zone valid";
    } else {
        // Fallback: all lines combined
        auto all_merged = cluster_lines(h_lines, 6.0);
        std::vector<double> all_y;
        for (const auto& l : all_merged) all_y.push_back(l.y_mid);

        int n_valid = 0;
        double p_avg = compute_pitch_iqr(all_y, n_valid);
        if (p_avg > 1.0) {
            double D_all = (f_pixel * P_real_cm * std::cos(theta_tilt_rad)) / p_avg;
            if (D_all >= D_min && D_all <= D_max) {
                D_tray = std::round(D_all * 100.0) / 100.0;
                status = "FULL_FRAME";
                notes = std::to_string(all_merged.size()) + " sekat full-frame";
            } else {
                empty.notes = "D out of range";
                empty.debug_lines = debug_raw;
                empty.debug_clustered = debug_clustered;
                return empty;
            }
        } else {
            empty.notes = "Pitch tidak valid";
            empty.debug_lines = debug_raw;
            empty.debug_clustered = debug_clustered;
            return empty;
        }
    }

    if (D_tray == 0) {
        empty.notes = "Tidak ada zona valid";
        empty.debug_lines = debug_raw;
        empty.debug_clustered = debug_clustered;
        return empty;
    }

    // ── Slat-Count Correction ───────────────────────────────────────────
    int total_slats = static_cast<int>(left_merged.size() + right_merged.size());
    if (total_slats > 0 && total_slats != ref_slats) {
        double raw_ratio = static_cast<double>(ref_slats) / total_slats;
        double correction = (raw_ratio > 0) ? std::sqrt(raw_ratio) : 1.0;
        correction = std::clamp(correction, 0.7, 1.5);
        D_tray = std::round(D_tray * correction * 100.0) / 100.0;
        if (D_left > 0) D_left = std::round(D_left * correction * 100.0) / 100.0;
        if (D_right > 0) D_right = std::round(D_right * correction * 100.0) / 100.0;
    }

    // ── Range validation ────────────────────────────────────────────────
    if (D_tray < D_min || D_tray > D_max) {
        MethodBResult r;
        r.D_tray_cm = D_tray;
        r.D_left_cm = D_left;
        r.D_right_cm = D_right;
        r.lines_left = static_cast<int>(left_y.size());
        r.lines_right = static_cast<int>(right_y.size());
        r.status = "OUT_OF_RANGE";
        r.debug_lines = debug_raw;
        r.debug_clustered = debug_clustered;
        return r;
    }

    // ── Confidence scoring ──────────────────────────────────────────────
    double confidence;
    double p_avg_final = (zl.pitch > 0) ? zl.pitch : zr.pitch;

    if (left_valid && right_valid) {
        if (total_slats >= 10)
            confidence = 0.70 + 0.15 * std::min((total_slats - 10) / 10.0, 1.0);
        else if (total_slats >= 6)
            confidence = 0.60 + 0.10 * ((total_slats - 6) / 4.0);
        else
            confidence = 0.55;
    } else if (status == "FULL_FRAME") {
        if (total_slats >= 8)
            confidence = 0.55 + 0.10 * std::min((total_slats - 8) / 8.0, 1.0);
        else if (total_slats >= 5)
            confidence = 0.45 + 0.10 * ((total_slats - 5) / 3.0);
        else
            confidence = 0.40;
    } else {
        int zone_lines = left_valid ?
            static_cast<int>(left_y.size()) : static_cast<int>(right_y.size());
        if (zone_lines >= 5)
            confidence = 0.50 + 0.10 * std::min((zone_lines - 5) / 5.0, 1.0);
        else
            confidence = 0.40 + 0.10 * ((zone_lines - min_lines) /
                         std::max(5.0 - min_lines, 1.0));
    }
    confidence = std::min(confidence, 0.85);

    // ── Build result ────────────────────────────────────────────────────
    MethodBResult result;
    result.D_tray_cm  = D_tray;
    result.confidence = std::round(confidence * 1000.0) / 1000.0;
    result.status     = status;
    result.D_left_cm  = D_left;
    result.D_right_cm = D_right;
    result.lines_left = static_cast<int>(left_y.size());
    result.lines_right = static_cast<int>(right_y.size());
    result.notes      = notes;
    result.pitch_px   = std::round(p_avg_final * 10.0) / 10.0;
    result.num_slats  = total_slats;
    result.debug_lines = debug_raw;
    result.debug_clustered = debug_clustered;
    result.valid      = true;
    return result;
}

} // namespace tray
