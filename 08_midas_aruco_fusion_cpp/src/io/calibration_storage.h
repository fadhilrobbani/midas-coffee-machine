/**
 * @file calibration_storage.h
 * @brief Calibration data persistence (JSON load/save for 7 modes).
 * @note STUB — will be implemented in Phase 2.
 */
#pragma once

#include <string>
#include <vector>
#include <map>
#include <nlohmann/json.hpp>
#include "height_math.h"

namespace fusion {

struct CalibData {
    int type = 0;
    double K = 0, m = 0, c = 0, A = 0, B = 0;
    double m_ref = 0, c_ref = 0, ref_bbox_area_px = 0;
    double true_height_cm = 0, true_height_cm_2 = 0;
    std::vector<double> poly_K, poly_Kgeom, poly_m, poly_c;
    nlohmann::json raw;
};

CalibData load_calibration(const std::string& path = "calibration.json");

void save_calibration_1p(const std::string& path, double K, double z_tray_ref,
                         double ratio_ref, double true_height);
void save_calibration_2p(const std::string& path, double m, double c,
                         const nlohmann::json& data1, const nlohmann::json& data2);
void save_calibration_3p(const std::string& path, const std::vector<double>& poly_K,
                         const std::vector<double>& z_grid, double true_height);
void save_calibration_4p(const std::string& path, double m_ref, double c_ref,
                         double ref_area, double z_low, double z_high, double true_height);
void save_calibration_5p(const std::string& path, const std::vector<double>& poly_Kgeom,
                         const std::vector<double>& z_grid, double true_height);
void save_calibration_6p(const std::string& path, const std::vector<double>& poly_m,
                         const std::vector<double>& poly_c, const std::vector<double>& z_grid,
                         double h1, double h2);
void save_calibration_7(const std::string& path, double A, double B, double h1, double h2);

} // namespace fusion
