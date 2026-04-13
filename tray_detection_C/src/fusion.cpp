/**
 * fusion.cpp — Fusi hierarki metode A, B, C
 */

#include "fusion.h"
#include <cmath>
#include <algorithm>

namespace tray {

FusedResult fuse_results(
    const std::optional<MethodAResult>& result_a,
    const MethodBResult& result_b,
    const std::optional<MethodCResult>& result_c) {

    bool b_valid = result_b.valid && result_b.confidence > 0;
    bool c_valid = result_c.has_value() && result_c->valid
                   && result_c->confidence > 0;
    bool a_valid = result_a.has_value() && result_a->confidence > 0;

    FusedResult out;
    out.detail_b = result_b;
    if (result_c) out.detail_c = *result_c;

    // ── Priority 1: B + C ───────────────────────────────────────────────
    if (b_valid && c_valid) {
        double D_b = result_b.D_tray_cm;
        double D_c = result_c->D_tray_cm;
        double cb = result_b.confidence;
        double cc = result_c->confidence;

        out.D_tray_cm   = std::round((D_b * cb + D_c * cc) / (cb + cc) * 100.0) / 100.0;
        out.method_used = "B+C";
        out.confidence  = std::round(std::min((cb + cc) / 2.0 * 1.1, 1.0) * 1000.0) / 1000.0;
        out.status      = result_b.status;
        out.D_left_cm   = result_b.D_left_cm;
        out.D_right_cm  = result_b.D_right_cm;
        out.lines_left  = result_b.lines_left;
        out.lines_right = result_b.lines_right;
        return out;
    }

    // ── Priority 2: B only ──────────────────────────────────────────────
    if (b_valid) {
        out.D_tray_cm   = result_b.D_tray_cm;
        out.method_used = "B";
        out.confidence  = result_b.confidence;
        out.status      = result_b.status;
        out.D_left_cm   = result_b.D_left_cm;
        out.D_right_cm  = result_b.D_right_cm;
        out.lines_left  = result_b.lines_left;
        out.lines_right = result_b.lines_right;
        out.notes       = result_b.notes;
        return out;
    }

    // ── Priority 3: C only ──────────────────────────────────────────────
    if (c_valid) {
        out.D_tray_cm   = result_c->D_tray_cm;
        out.method_used = "C";
        out.confidence  = result_c->confidence;
        out.status      = result_c->status;
        out.notes       = result_c->notes;
        return out;
    }

    // ── Priority 4: A only ──────────────────────────────────────────────
    if (a_valid) {
        out.D_tray_cm   = result_a->D_tray_cm;
        out.method_used = "A";
        out.confidence  = result_a->confidence;
        out.status      = result_a->status;
        out.notes       = result_a->notes;
        return out;
    }

    // ── Nothing valid ───────────────────────────────────────────────────
    out.method_used = "NONE";
    out.status = "INSUFFICIENT_DATA";
    out.notes  = "Semua metode gagal";
    return out;
}


FusedResult build_single_result(
    const std::string& method,
    const std::optional<MethodAResult>& result_a,
    const MethodBResult& result_b,
    const std::optional<MethodCResult>& result_c) {

    FusedResult out;
    out.detail_b = result_b;
    if (result_c) out.detail_c = *result_c;

    if (method == "B" && result_b.valid) {
        out.D_tray_cm   = result_b.D_tray_cm;
        out.method_used = "B";
        out.confidence  = result_b.confidence;
        out.status      = result_b.status;
        out.D_left_cm   = result_b.D_left_cm;
        out.D_right_cm  = result_b.D_right_cm;
        out.lines_left  = result_b.lines_left;
        out.lines_right = result_b.lines_right;
        out.notes       = result_b.notes;
    } else if (method == "C" && result_c && result_c->valid) {
        out.D_tray_cm   = result_c->D_tray_cm;
        out.method_used = "C";
        out.confidence  = result_c->confidence;
        out.status      = result_c->status;
        out.notes       = result_c->notes;
    } else if (method == "A" && result_a && result_a->confidence > 0) {
        out.D_tray_cm   = result_a->D_tray_cm;
        out.method_used = "A";
        out.confidence  = result_a->confidence;
        out.status      = result_a->status;
        out.notes       = result_a->notes;
    } else {
        out.method_used = method;
        out.status = "INSUFFICIENT_DATA";
        out.notes = "Metode " + method + " gagal";
    }

    return out;
}

} // namespace tray
