/**
 * @file height_math.h
 * @brief Pure math functions for cup height estimation (7 calibration modes).
 *
 * Port of Python core/height_math.py — all functions are pure, stateless,
 * and side-effect free. Designed for testability and scalability.
 *
 * Each function corresponds to a different calibration model:
 *   Type 1: 1-Point K-Factor
 *   Type 2: 2-Point Linear
 *   Type 3: Z-Grid Polynomial
 *   Type 4: BBox Area Compensation
 *   Type 5: Geometric Projection
 *   Type 6: Bilateral Z-Grid
 *   Type 7: Analytic Geometry
 */

#pragma once

#include <vector>
#include <cmath>

namespace fusion {

/**
 * @brief Bounding box struct used across the pipeline.
 */
struct BBox {
    int x1, y1, x2, y2;
};

/**
 * @brief Evaluate polynomial using Horner's method (replaces np.polyval).
 *
 * Coefficients are in highest-degree-first order (same as numpy convention).
 * p(x) = coeffs[0]*x^(n-1) + coeffs[1]*x^(n-2) + ... + coeffs[n-1]
 *
 * @param coeffs Polynomial coefficients (highest degree first)
 * @param x      Evaluation point
 * @return       p(x)
 */
inline double polyval(const std::vector<double>& coeffs, double x) {
    if (coeffs.empty()) return 0.0;
    double result = coeffs[0];
    for (size_t i = 1; i < coeffs.size(); ++i) {
        result = result * x + coeffs[i];
    }
    return result;
}

/// Type 1: 1-Point K-Factor calibration
double calc_height_1point(double m_rim, double m_tray, double z_tray, double K);

/// Type 2: 2-Point Linear calibration
double calc_height_2point(double m_rim, double m_tray, double z_tray,
                          double m, double c);

/// Type 3: Z-Grid Polynomial calibration
double calc_height_zgrid(double m_rim, double m_tray, double z_tray,
                         const std::vector<double>& poly_K);

/// Type 4: BBox Area compensation calibration
double calc_height_bbox(double m_rim, double m_tray, double z_tray,
                        const BBox& bbox, double m_ref, double c_ref,
                        double ref_area);

/// Type 5: Geometric Projection calibration
double calc_height_geom(double z_tray, const BBox& bbox,
                        double focal_length_px,
                        const std::vector<double>& poly_Kgeom);

/// Type 6: Bilateral Z-Grid calibration
double calc_height_bilateral_zgrid(double m_rim, double m_tray, double z_tray,
                                   const std::vector<double>& poly_m,
                                   const std::vector<double>& poly_c);

/// Type 7: Analytic Geometry calibration
double calc_height_analytic(double z_tray, const BBox& bbox,
                            double A, double B);

} // namespace fusion
