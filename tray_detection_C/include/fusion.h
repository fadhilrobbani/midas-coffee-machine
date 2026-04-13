#pragma once
/**
 * fusion.h — Fusi hierarki metode A, B, C
 *
 * Prioritas: B+C → B → C → A → INSUFFICIENT_DATA
 */

#include <string>
#include <optional>
#include "method_a.h"
#include "method_b.h"
#include "method_c.h"

namespace tray {

struct FusedResult {
    double D_tray_cm   = 0.0;
    std::string method_used = "NONE";
    double confidence  = 0.0;
    std::string status = "INSUFFICIENT_DATA";
    double D_left_cm   = 0.0;
    double D_right_cm  = 0.0;
    int lines_left     = 0;
    int lines_right    = 0;
    std::string notes;

    // Detail per-metode (untuk debugging / visualisasi)
    MethodBResult detail_b;
    MethodCResult detail_c;
    int tray_bbox[4]  = {0, 0, 0, 0};
    int glass_bbox[4] = {0, 0, 0, 0};
    bool has_glass     = false;
    bool has_tray_bbox = false;
};

/**
 * Fusi hasil dari 3 metode sesuai hierarki prioritas.
 */
FusedResult fuse_results(
    const std::optional<MethodAResult>& result_a,
    const MethodBResult& result_b,
    const std::optional<MethodCResult>& result_c);

/**
 * Build output untuk single-method mode.
 */
FusedResult build_single_result(
    const std::string& method,
    const std::optional<MethodAResult>& result_a,
    const MethodBResult& result_b,
    const std::optional<MethodCResult>& result_c);

} // namespace tray
