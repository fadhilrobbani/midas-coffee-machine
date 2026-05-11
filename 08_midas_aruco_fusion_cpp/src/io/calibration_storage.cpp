/**
 * @file calibration_storage.cpp
 * @brief Implementation of calibration data persistence (JSON).
 *
 * Direct port of Python core/calibration_storage.py.
 * Uses nlohmann/json for serialization.
 */

#include "calibration_storage.h"
#include <fstream>
#include <iostream>
#include <filesystem>

namespace fusion {

CalibData load_calibration(const std::string& path) {
    CalibData data;
    if (!std::filesystem::exists(path)) {
        return data;
    }
    try {
        std::ifstream f(path);
        nlohmann::json j;
        f >> j;
        data.raw = j;

        data.type = j.value("type", 0);
        data.K = j.value("K", 0.0);
        data.m = j.value("m", 0.0);
        data.c = j.value("c", 0.0);
        data.A = j.value("A", 0.0);
        data.B = j.value("B", 0.0);
        data.m_ref = j.value("m_ref", 0.0);
        data.c_ref = j.value("c_ref", 0.0);
        data.ref_bbox_area_px = j.value("ref_bbox_area_px", 0.0);
        data.true_height_cm = j.value("true_height_cm", 0.0);
        data.true_height_cm_2 = j.value("true_height_cm_2", 0.0);

        if (j.contains("poly_K") && j["poly_K"].is_array())
            data.poly_K = j["poly_K"].get<std::vector<double>>();
        if (j.contains("poly_Kgeom") && j["poly_Kgeom"].is_array())
            data.poly_Kgeom = j["poly_Kgeom"].get<std::vector<double>>();
        if (j.contains("poly_m") && j["poly_m"].is_array())
            data.poly_m = j["poly_m"].get<std::vector<double>>();
        if (j.contains("poly_c") && j["poly_c"].is_array())
            data.poly_c = j["poly_c"].get<std::vector<double>>();

    } catch (const std::exception& e) {
        std::cerr << "[CalibStorage] Error loading " << path << ": " << e.what() << "\n";
        return CalibData{};
    }
    return data;
}

static void write_json(const std::string& path, const nlohmann::json& j) {
    std::ofstream f(path);
    f << j.dump(4);
}

void save_calibration_1p(const std::string& path, double K, double z_tray_ref,
                         double ratio_ref, double true_height) {
    nlohmann::json j = {
        {"type", 1}, {"K", K},
        {"z_tray_ref", z_tray_ref}, {"ratio_ref", ratio_ref},
        {"true_height_cm", true_height}
    };
    write_json(path, j);
}

void save_calibration_2p(const std::string& path, double m, double c,
                         const nlohmann::json& data1, const nlohmann::json& data2) {
    nlohmann::json j = {
        {"type", 2}, {"m", m}, {"c", c},
        {"point_1", data1}, {"point_2", data2}
    };
    write_json(path, j);
}

void save_calibration_3p(const std::string& path, const std::vector<double>& poly_K,
                         const std::vector<double>& z_grid, double true_height) {
    nlohmann::json j = {
        {"type", 3}, {"poly_K", poly_K}, {"z_grid", z_grid},
        {"true_height_cm", true_height}
    };
    write_json(path, j);
}

void save_calibration_4p(const std::string& path, double m_ref, double c_ref,
                         double ref_area, double z_low, double z_high, double true_height) {
    nlohmann::json j = {
        {"type", 4}, {"m_ref", m_ref}, {"c_ref", c_ref},
        {"ref_bbox_area_px", ref_area}, {"z_low", z_low}, {"z_high", z_high},
        {"true_height_cm", true_height}
    };
    write_json(path, j);
}

void save_calibration_5p(const std::string& path, const std::vector<double>& poly_Kgeom,
                         const std::vector<double>& z_grid, double true_height) {
    nlohmann::json j = {
        {"type", 5}, {"poly_Kgeom", poly_Kgeom}, {"z_grid", z_grid},
        {"true_height_cm", true_height}
    };
    write_json(path, j);
}

void save_calibration_6p(const std::string& path, const std::vector<double>& poly_m,
                         const std::vector<double>& poly_c, const std::vector<double>& z_grid,
                         double h1, double h2) {
    nlohmann::json j = {
        {"type", 6}, {"poly_m", poly_m}, {"poly_c", poly_c},
        {"z_grid", z_grid}, {"true_height_cm", h1}, {"true_height_cm_2", h2}
    };
    write_json(path, j);
}

void save_calibration_7(const std::string& path, double A, double B, double h1, double h2) {
    nlohmann::json j = {
        {"type", 7}, {"A", A}, {"B", B},
        {"true_height_cm", h1}, {"true_height_cm_2", h2}
    };
    write_json(path, j);
}

} // namespace fusion
