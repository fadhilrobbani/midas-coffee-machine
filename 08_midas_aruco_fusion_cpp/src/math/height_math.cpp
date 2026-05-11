/**
 * @file height_math.cpp
 * @brief Implementation of cup height calculation functions.
 *
 * Direct port of Python core/height_math.py.
 * All functions follow the same guard pattern:
 *   - Return 0.0 for invalid inputs (zero/negative denominators)
 *   - Return 0.0 for negative calculated heights
 */

#include "height_math.h"
#include <algorithm>

namespace fusion {

double calc_height_1point(double m_rim, double m_tray, double z_tray, double K) {
    if (m_tray <= 0.0 || z_tray <= 0.0) return 0.0;
    double ratio = m_rim / m_tray;
    if (ratio <= 0.0) return 0.0;
    double cup_height = z_tray * (1.0 - K / ratio);
    return (cup_height > 0.0) ? cup_height : 0.0;
}

double calc_height_2point(double m_rim, double m_tray, double z_tray,
                          double m, double c) {
    if (m_tray <= 0.0 || z_tray <= 0.0) return 0.0;
    double ratio = m_rim / m_tray;
    if (ratio <= 0.0) return 0.0;
    double cup_height = z_tray * (m * ratio + c);
    return (cup_height > 0.0) ? cup_height : 0.0;
}

double calc_height_zgrid(double m_rim, double m_tray, double z_tray,
                         const std::vector<double>& poly_K) {
    if (m_tray <= 0.0 || z_tray <= 0.0) return 0.0;
    double ratio = m_rim / m_tray;
    if (ratio <= 0.0) return 0.0;
    double K_live = polyval(poly_K, z_tray);
    double cup_height = z_tray * (1.0 - K_live / ratio);
    return (cup_height > 0.0) ? cup_height : 0.0;
}

double calc_height_bbox(double m_rim, double m_tray, double z_tray,
                        const BBox& bbox, double m_ref, double c_ref,
                        double ref_area) {
    if (m_tray <= 0.0 || z_tray <= 0.0) return 0.0;
    double ratio = m_rim / m_tray;
    if (ratio <= 0.0) return 0.0;

    double live_area = std::max(1.0,
        static_cast<double>((bbox.x2 - bbox.x1) * (bbox.y2 - bbox.y1)));
    double scale = ref_area / live_area;
    double m_adj = m_ref * scale;
    double cup_height = z_tray * (m_adj * ratio + c_ref);
    return (cup_height > 0.0) ? cup_height : 0.0;
}

double calc_height_geom(double z_tray, const BBox& bbox,
                        double focal_length_px,
                        const std::vector<double>& poly_Kgeom) {
    if (z_tray <= 0.0 || focal_length_px <= 0.0) return 0.0;
    double bbox_h_px = std::max(1.0, static_cast<double>(bbox.y2 - bbox.y1));
    double K_live = polyval(poly_Kgeom, z_tray);
    double cup_height = z_tray * (bbox_h_px / focal_length_px) * K_live;
    return (cup_height > 0.0) ? cup_height : 0.0;
}

double calc_height_bilateral_zgrid(double m_rim, double m_tray, double z_tray,
                                   const std::vector<double>& poly_m,
                                   const std::vector<double>& poly_c) {
    if (m_tray <= 0.0 || z_tray <= 0.0) return 0.0;
    double ratio = m_rim / m_tray;
    if (ratio <= 0.0) return 0.0;
    double m_live = polyval(poly_m, z_tray);
    double c_live = polyval(poly_c, z_tray);
    double cup_height = z_tray * (m_live * ratio + c_live);
    return (cup_height > 0.0) ? cup_height : 0.0;
}

double calc_height_analytic(double z_tray, const BBox& bbox,
                            double A, double B) {
    if (z_tray <= 0.0) return 0.0;
    double bbox_h = static_cast<double>(bbox.y2 - bbox.y1);
    double denom = bbox_h + B;
    if (std::abs(denom) < 1e-4) return 0.0;
    double cup_height = (bbox_h * z_tray - A) / denom;
    return (cup_height > 0.0) ? cup_height : 0.0;
}

} // namespace fusion
