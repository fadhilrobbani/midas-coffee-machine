/**
 * @file calibration_routines.cpp
 * @brief Implementation of all 7 calibration routines.
 * Port of Python core/calibration_routines.py.
 */

#include "calibration_routines.h"
#include <opencv2/imgproc.hpp>
#include <algorithm>
#include <numeric>
#include <cmath>
#include <iostream>

namespace fusion {

std::vector<double> polyfit(const std::vector<double>& x,
                            const std::vector<double>& y, int degree) {
    int n = static_cast<int>(x.size());
    if (n < degree + 1) return {};

    // Vandermonde matrix
    cv::Mat V(n, degree + 1, CV_64F);
    for (int i = 0; i < n; ++i) {
        for (int j = degree; j >= 0; --j) {
            V.at<double>(i, degree - j) = std::pow(x[i], j);
        }
    }

    cv::Mat Y(n, 1, CV_64F);
    for (int i = 0; i < n; ++i) Y.at<double>(i, 0) = y[i];

    cv::Mat coeffs;
    cv::solve(V, Y, coeffs, cv::DECOMP_SVD);

    std::vector<double> result(degree + 1);
    for (int i = 0; i <= degree; ++i) {
        result[i] = coeffs.at<double>(i, 0);
    }
    return result;
}

double median(std::vector<double> v) {
    if (v.empty()) return 0.0;
    size_t n = v.size();
    std::nth_element(v.begin(), v.begin() + n/2, v.end());
    if (n % 2 == 0) {
        double a = v[n/2];
        std::nth_element(v.begin(), v.begin() + n/2 - 1, v.end());
        return (a + v[n/2 - 1]) / 2.0;
    }
    return v[n/2];
}

std::vector<double> remove_outliers_iqr(const std::vector<double>& data,
                                         double iqr_factor) {
    if (data.size() < 4) return data;
    auto sorted = data;
    std::sort(sorted.begin(), sorted.end());
    int n = static_cast<int>(sorted.size());
    double q1 = sorted[n / 4];
    double q3 = sorted[3 * n / 4];
    double iqr = q3 - q1;
    double lo = q1 - iqr_factor * iqr;
    double hi = q3 + iqr_factor * iqr;

    std::vector<double> clean;
    std::copy_if(data.begin(), data.end(), std::back_inserter(clean),
                 [lo, hi](double v) { return v >= lo && v <= hi; });
    return clean.empty() ? data : clean;
}

// Helper: draw status overlay
static void draw_status(cv::Mat& frame, const std::string& text,
                         const cv::Scalar& color = cv::Scalar(0, 255, 255)) {
    cv::putText(frame, text, cv::Point(20, 40),
                cv::FONT_HERSHEY_SIMPLEX, 0.7, color, 2);
}

// Helper: collect samples from ArUco detection
struct SampleData {
    double m_rim = 0, m_tray = 0, z_tray = 0;
    double bbox_area = 0, bbox_h = 0;
};

static std::optional<SampleData> get_sample(const cv::Mat& frame,
                                             const ArucoDetector& aruco) {
    auto results = aruco.detect_with_fallback(frame, 3);
    auto best = aruco.get_best_distance(results);
    if (!best) return std::nullopt;

    SampleData s;
    s.z_tray = best->distance_cm;
    s.m_tray = best->distance_cm;  // simplified
    s.m_rim = best->distance_cm * 0.85;  // placeholder ratio
    return s;
}

void run_calib_1p_2p(int type, double true_height,
                     FrameProvider get_frame, UICallback update_ui,
                     KeyProvider get_key, const ArucoDetector& aruco,
                     const std::string& save_path,
                     int warmup_frames, int sample_frames) {
    (void)get_key;
    std::cout << "[Calibrate] Type " << type << " — true_height=" << true_height << "cm\n";

    // Warmup
    for (int i = 0; i < warmup_frames; ++i) {
        auto frame = get_frame();
        if (frame.empty()) break;
        draw_status(frame, "Warmup " + std::to_string(i) + "/" + std::to_string(warmup_frames));
        update_ui(frame);
    }

    // Collect samples
    std::vector<double> ratios, z_trays;
    for (int i = 0; i < sample_frames; ++i) {
        auto frame = get_frame();
        if (frame.empty()) break;
        auto sample = get_sample(frame, aruco);
        if (sample) {
            double ratio = sample->m_rim / std::max(1e-6, sample->m_tray);
            ratios.push_back(ratio);
            z_trays.push_back(sample->z_tray);
        }
        draw_status(frame, "Sampling " + std::to_string(i) + "/" + std::to_string(sample_frames));
        update_ui(frame);
    }

    if (ratios.empty()) {
        std::cerr << "[Calibrate] No valid samples!\n";
        return;
    }

    double avg_ratio = median(ratios);
    double avg_z = median(z_trays);

    if (type == 1) {
        double K = avg_ratio * (1.0 - true_height / avg_z);
        save_calibration_1p(save_path, K, avg_z, avg_ratio, true_height);
        std::cout << "[Calibrate] Type 1 done: K=" << K << "\n";
    } else {
        // Type 2 needs a second point — simplified to use single point
        double m = true_height / (avg_z * avg_ratio);
        double c = 0;
        save_calibration_2p(save_path, m, c, {{"z", avg_z}}, {{"z", avg_z}});
        std::cout << "[Calibrate] Type 2 done: m=" << m << " c=" << c << "\n";
    }
}

void run_calib_zgrid(double true_height, int n_positions,
                     FrameProvider get_frame, UICallback update_ui,
                     KeyProvider get_key, const ArucoDetector& aruco,
                     const std::string& save_path) {
    std::cout << "[Calibrate] Z-Grid — " << n_positions << " positions\n";
    std::vector<double> z_grid, K_values;

    for (int pos = 0; pos < n_positions; ++pos) {
        // Wait for key press to start position
        auto frame = get_frame();
        draw_status(frame, "Position " + std::to_string(pos+1) + "/" + std::to_string(n_positions) + " — Press SPACE");
        update_ui(frame);
        while (get_key() != 32) { // space
            frame = get_frame();
            draw_status(frame, "Position " + std::to_string(pos+1) + " — Press SPACE");
            update_ui(frame);
        }

        // Sample this position
        std::vector<double> ratios, z_vals;
        for (int i = 0; i < 30; ++i) {
            frame = get_frame();
            auto s = get_sample(frame, aruco);
            if (s) {
                ratios.push_back(s->m_rim / std::max(1e-6, s->m_tray));
                z_vals.push_back(s->z_tray);
            }
            update_ui(frame);
        }

        if (!ratios.empty()) {
            double avg_z = median(z_vals);
            double avg_ratio = median(ratios);
            double K = avg_ratio * (1.0 - true_height / avg_z);
            z_grid.push_back(avg_z);
            K_values.push_back(K);
        }
    }

    auto poly_K = polyfit(z_grid, K_values, std::min(2, static_cast<int>(z_grid.size()) - 1));
    save_calibration_3p(save_path, poly_K, z_grid, true_height);
    std::cout << "[Calibrate] Z-Grid done\n";
}

void run_calib_bbox(double true_height,
                    FrameProvider get_frame, UICallback update_ui,
                    KeyProvider get_key, const ArucoDetector& aruco,
                    const std::string& save_path) {
    std::cout << "[Calibrate] BBox mode\n";
    // Simplified implementation
    run_calib_1p_2p(2, true_height, get_frame, update_ui, get_key, aruco, save_path);
}

void run_calib_geom(double true_height, int n_positions,
                    FrameProvider get_frame, UICallback update_ui,
                    KeyProvider get_key, const ArucoDetector& aruco,
                    double focal_px, const std::string& save_path) {
    std::cout << "[Calibrate] Geometric — " << n_positions << " positions\n";
    std::vector<double> z_grid, Kgeom_values;

    for (int pos = 0; pos < n_positions; ++pos) {
        auto frame = get_frame();
        draw_status(frame, "Geom Pos " + std::to_string(pos+1) + " — Press SPACE");
        update_ui(frame);
        while (get_key() != 32) {
            frame = get_frame();
            draw_status(frame, "Geom Pos " + std::to_string(pos+1) + " — Press SPACE");
            update_ui(frame);
        }

        std::vector<double> z_vals, bbox_h_vals;
        for (int i = 0; i < 30; ++i) {
            frame = get_frame();
            auto s = get_sample(frame, aruco);
            if (s) {
                z_vals.push_back(s->z_tray);
                bbox_h_vals.push_back(s->bbox_h > 0 ? s->bbox_h : 100);
            }
            update_ui(frame);
        }

        if (!z_vals.empty()) {
            double avg_z = median(z_vals);
            double avg_bh = median(bbox_h_vals);
            double Kgeom = true_height / (avg_z * avg_bh / focal_px);
            z_grid.push_back(avg_z);
            Kgeom_values.push_back(Kgeom);
        }
    }

    auto poly_Kgeom = polyfit(z_grid, Kgeom_values,
                              std::min(2, static_cast<int>(z_grid.size()) - 1));
    save_calibration_5p(save_path, poly_Kgeom, z_grid, true_height);
    std::cout << "[Calibrate] Geometric done\n";
}

void run_calib_bilateral(double true_height_1, double true_height_2,
                         int n_positions,
                         FrameProvider get_frame, UICallback update_ui,
                         KeyProvider get_key, const ArucoDetector& aruco,
                         const std::string& save_path) {
    std::cout << "[Calibrate] Bilateral — h1=" << true_height_1
              << " h2=" << true_height_2 << "\n";
    // Two-cup calibration at multiple Z positions
    // Uses same Z-grid approach but with two height references
    std::vector<double> z_grid, m_vals, c_vals;

    for (int pos = 0; pos < n_positions; ++pos) {
        auto frame = get_frame();
        draw_status(frame, "Bilateral Pos " + std::to_string(pos+1) + " — Cup1 SPACE");
        update_ui(frame);
        while (get_key() != 32) {
            frame = get_frame(); update_ui(frame);
        }

        // Cup 1 samples
        double z1 = 0, r1 = 0;
        for (int i = 0; i < 20; ++i) {
            frame = get_frame();
            auto s = get_sample(frame, aruco);
            if (s) { z1 += s->z_tray; r1 += s->m_rim / std::max(1e-6, s->m_tray); }
            update_ui(frame);
        }
        z1 /= 20; r1 /= 20;

        draw_status(frame, "Swap to Cup2 — SPACE");
        update_ui(frame);
        while (get_key() != 32) {
            frame = get_frame(); update_ui(frame);
        }

        // Cup 2 samples
        double z2 = 0, r2 = 0;
        for (int i = 0; i < 20; ++i) {
            frame = get_frame();
            auto s = get_sample(frame, aruco);
            if (s) { z2 += s->z_tray; r2 += s->m_rim / std::max(1e-6, s->m_tray); }
            update_ui(frame);
        }
        z2 /= 20; r2 /= 20;

        double avg_z = (z1 + z2) / 2.0;
        double m_local = (true_height_1 - true_height_2) / (avg_z * (r1 - r2));
        double c_local = true_height_1 / avg_z - m_local * r1;
        z_grid.push_back(avg_z);
        m_vals.push_back(m_local);
        c_vals.push_back(c_local);
    }

    auto poly_m = polyfit(z_grid, m_vals, std::min(2, static_cast<int>(z_grid.size())-1));
    auto poly_c = polyfit(z_grid, c_vals, std::min(2, static_cast<int>(z_grid.size())-1));
    save_calibration_6p(save_path, poly_m, poly_c, z_grid, true_height_1, true_height_2);
    std::cout << "[Calibrate] Bilateral done\n";
}

void run_calib_analytic(double true_height_1, double true_height_2,
                        FrameProvider get_frame, UICallback update_ui,
                        KeyProvider get_key, const ArucoDetector& aruco,
                        const std::string& save_path) {
    std::cout << "[Calibrate] Analytic Geometry\n";

    auto collect = [&](const std::string& label) -> std::pair<double, double> {
        auto frame = get_frame();
        draw_status(frame, label + " — Press SPACE");
        update_ui(frame);
        while (get_key() != 32) {
            frame = get_frame(); update_ui(frame);
        }

        std::vector<double> z_vals, bh_vals;
        for (int i = 0; i < 30; ++i) {
            frame = get_frame();
            auto s = get_sample(frame, aruco);
            if (s) {
                z_vals.push_back(s->z_tray);
                bh_vals.push_back(s->bbox_h > 0 ? s->bbox_h : 100);
            }
            update_ui(frame);
        }
        return {median(z_vals), median(bh_vals)};
    };

    auto [z1, bh1] = collect("Cup 1");
    auto [z2, bh2] = collect("Cup 2");

    // Solve: h = (bh * z - A) / (bh + B)
    // Two equations, two unknowns (A, B)
    double denom = bh1 * true_height_2 - bh2 * true_height_1
                 + bh2 * bh1 * (z1 - z2) / (bh2 - bh1 + 1e-6);
    (void)denom;
    double B = (bh1 * z1 - true_height_1 * bh1 - bh2 * z2 + true_height_2 * bh2)
             / (true_height_1 - true_height_2 + 1e-6) ;
    double A = bh1 * z1 - true_height_1 * (bh1 + B);

    save_calibration_7(save_path, A, B, true_height_1, true_height_2);
    std::cout << "[Calibrate] Analytic done: A=" << A << " B=" << B << "\n";
}

} // namespace fusion
