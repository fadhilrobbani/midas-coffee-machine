/**
 * method_a.cpp — Metode A: Apparent Width Tray (Fallback)
 *
 * Direct port dari method_a.py.
 */

#include "method_a.h"
#include <cmath>
#include <algorithm>

namespace tray {

std::optional<MethodAResult> estimate_D_tray_method_A(
    int x1, int y1, int x2, int y2,
    double f_pixel,
    double W_real_cm,
    double theta_tilt_rad,
    int frame_width,
    double D_min, double D_max) {

    int W_pixel = x2 - x1;
    if (W_pixel < 20) return std::nullopt;

    // ── Kalkulasi D_tray ────────────────────────────────────────────────
    double D_raw = (f_pixel * W_real_cm) / static_cast<double>(W_pixel);
    double D_tray = D_raw * std::cos(theta_tilt_rad);

    // ── Validasi range ──────────────────────────────────────────────────
    if (D_tray < D_min || D_tray > D_max) {
        MethodAResult r;
        r.D_tray_cm  = std::round(D_tray * 100.0) / 100.0;
        r.confidence = 0.0;
        r.status     = "OUT_OF_RANGE";
        r.notes      = "D_tray=" + std::to_string(D_tray)
                       + "cm out of range";
        return r;
    }

    // ── Confidence scoring ──────────────────────────────────────────────
    double confidence;
    std::string notes;
    int edge_margin = 10;
    bool near_left  = x1 < edge_margin;
    bool near_right = x2 > (frame_width - edge_margin);
    double fill_ratio = static_cast<double>(W_pixel) / frame_width;

    if (fill_ratio > 0.6) {
        confidence = 0.50 + 0.15 * std::min(fill_ratio, 1.0);
        confidence = std::clamp(confidence, 0.50, 0.65);
        notes = "Bbox lebar (mungkin mode no-yolo)";
    } else if (near_left || near_right) {
        confidence = 0.30 + 0.10 *
            (std::min(x1, frame_width - x2) / static_cast<double>(edge_margin));
        confidence = std::clamp(confidence, 0.30, 0.45);
        notes = "Bbox mepet tepi frame";
    } else {
        confidence = 0.55 + 0.10 * std::min(fill_ratio / 0.4, 1.0);
        confidence = std::clamp(confidence, 0.55, 0.65);
    }

    MethodAResult r;
    r.D_tray_cm  = std::round(D_tray * 100.0) / 100.0;
    r.confidence = std::round(confidence * 1000.0) / 1000.0;
    r.status     = "OK";
    r.notes      = notes;
    return r;
}

} // namespace tray
