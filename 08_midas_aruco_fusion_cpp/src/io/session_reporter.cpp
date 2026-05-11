/**
 * @file session_reporter.cpp
 * @brief Session report generation implementation.
 */

#include "session_reporter.h"
#include <opencv2/imgproc.hpp>
#include <opencv2/imgcodecs.hpp>
#include <fstream>
#include <algorithm>
#include <numeric>
#include <cmath>
#include <filesystem>
#include <iomanip>
#include <sstream>
#include <chrono>

namespace fs = std::filesystem;

namespace fusion {

SessionReporter::SessionReporter(const std::string& output_dir)
    : output_dir_(output_dir)
{
    fs::create_directories(output_dir_);
}

void SessionReporter::add_entry(const SessionEntry& entry) {
    entries_.push_back(entry);
}

SessionReporter::Stats SessionReporter::compute_stats(
    const std::vector<double>& values) const
{
    Stats s{};
    s.count = static_cast<int>(values.size());
    if (values.empty()) return s;

    s.min = *std::min_element(values.begin(), values.end());
    s.max = *std::max_element(values.begin(), values.end());
    s.mean = std::accumulate(values.begin(), values.end(), 0.0) / s.count;

    // Median
    auto sorted = values;
    std::sort(sorted.begin(), sorted.end());
    s.median = (s.count % 2 == 0) ?
        (sorted[s.count/2 - 1] + sorted[s.count/2]) / 2.0 :
        sorted[s.count/2];

    // Stddev
    double sq_sum = std::accumulate(values.begin(), values.end(), 0.0,
        [&](double acc, double v) { return acc + (v - s.mean) * (v - s.mean); });
    s.stddev = std::sqrt(sq_sum / s.count);

    return s;
}

void SessionReporter::generate_chart(const std::string& path) const {
    if (entries_.empty()) return;

    int w = 800, h = 400, pad = 60;
    cv::Mat chart(h, w, CV_8UC3, cv::Scalar(30, 30, 30));

    std::vector<double> heights;
    for (const auto& e : entries_) heights.push_back(e.cup_height_cm);

    double min_h = *std::min_element(heights.begin(), heights.end());
    double max_h = *std::max_element(heights.begin(), heights.end());
    if (max_h - min_h < 0.1) { min_h -= 1; max_h += 1; }

    // Draw grid
    for (int i = 0; i <= 4; ++i) {
        int y = pad + i * (h - 2 * pad) / 4;
        cv::line(chart, cv::Point(pad, y), cv::Point(w - pad, y),
                 cv::Scalar(60, 60, 60), 1);
        double val = max_h - i * (max_h - min_h) / 4;
        std::ostringstream ss;
        ss << std::fixed << std::setprecision(1) << val;
        cv::putText(chart, ss.str(), cv::Point(5, y + 5),
                    cv::FONT_HERSHEY_SIMPLEX, 0.35, cv::Scalar(150, 150, 150));
    }

    // Draw line
    for (size_t i = 1; i < heights.size(); ++i) {
        int x1 = pad + static_cast<int>((i-1) * (w - 2*pad) / (heights.size()-1));
        int x2 = pad + static_cast<int>(i * (w - 2*pad) / (heights.size()-1));
        int y1 = pad + static_cast<int>((max_h - heights[i-1]) / (max_h - min_h) * (h - 2*pad));
        int y2 = pad + static_cast<int>((max_h - heights[i]) / (max_h - min_h) * (h - 2*pad));
        cv::line(chart, cv::Point(x1, y1), cv::Point(x2, y2),
                 cv::Scalar(0, 200, 100), 2);
    }

    cv::putText(chart, "Cup Height (cm) over Time", cv::Point(w/2 - 120, 25),
                cv::FONT_HERSHEY_SIMPLEX, 0.6, cv::Scalar(255, 255, 255), 1);
    cv::imwrite(path, chart);
}

void SessionReporter::write_markdown(const std::string& path,
                                      const nlohmann::json& params) const {
    std::vector<double> heights, distances, volumes;
    for (const auto& e : entries_) {
        heights.push_back(e.cup_height_cm);
        distances.push_back(e.aruco_distance_cm);
        volumes.push_back(e.volume_ml);
    }

    auto h_stats = compute_stats(heights);
    auto d_stats = compute_stats(distances);

    std::ofstream f(path);
    f << "# Session Report\n\n";
    f << "**Generated**: " << __DATE__ << " " << __TIME__ << "\n\n";

    if (!params.empty()) {
        f << "## Parameters\n\n";
        f << "| Key | Value |\n|:---|:---|\n";
        for (auto& [k, v] : params.items()) {
            f << "| " << k << " | " << v.dump() << " |\n";
        }
        f << "\n";
    }

    f << "## Statistics\n\n";
    f << "| Metric | Mean | Median | StdDev | Min | Max | N |\n";
    f << "|:---|:---:|:---:|:---:|:---:|:---:|:---:|\n";
    f << std::fixed << std::setprecision(2);
    f << "| Height (cm) | " << h_stats.mean << " | " << h_stats.median
      << " | " << h_stats.stddev << " | " << h_stats.min << " | "
      << h_stats.max << " | " << h_stats.count << " |\n";
    f << "| Distance (cm) | " << d_stats.mean << " | " << d_stats.median
      << " | " << d_stats.stddev << " | " << d_stats.min << " | "
      << d_stats.max << " | " << d_stats.count << " |\n\n";
    f << "## Chart\n\n![Height Chart](chart.png)\n";
}

void SessionReporter::generate_report(const std::string& session_name,
                                       const nlohmann::json& params) const {
    std::string dir = output_dir_ + "/" + session_name;
    fs::create_directories(dir);

    // JSON data
    nlohmann::json jdata;
    for (const auto& e : entries_) {
        jdata["entries"].push_back({
            {"frame", e.frame_num}, {"height_cm", e.cup_height_cm},
            {"distance_cm", e.aruco_distance_cm},
            {"diameter_cm", e.diameter_cm}, {"volume_ml", e.volume_ml},
            {"timestamp", e.timestamp_sec}
        });
    }
    std::ofstream(dir + "/session_data.json") << jdata.dump(4);

    generate_chart(dir + "/chart.png");
    write_markdown(dir + "/report.md", params);
}

} // namespace fusion
