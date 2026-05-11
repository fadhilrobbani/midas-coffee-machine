/**
 * @file session_reporter.h
 * @brief Generate post-session reports (Markdown + JSON + charts).
 * Port of Python core/session_reporter.py.
 */

#pragma once

#include <string>
#include <vector>
#include <nlohmann/json.hpp>

namespace fusion {

struct SessionEntry {
    double timestamp_sec = 0;
    double cup_height_cm = 0;
    double aruco_distance_cm = 0;
    double diameter_cm = 0;
    double volume_ml = 0;
    int frame_num = 0;
};

class SessionReporter {
public:
    explicit SessionReporter(const std::string& output_dir = "session_reports");

    /// Add a measurement entry
    void add_entry(const SessionEntry& entry);

    /// Generate the full report (Markdown + JSON + chart PNG)
    void generate_report(const std::string& session_name,
                         const nlohmann::json& params = {}) const;

    /// Get statistics
    struct Stats { double mean, median, stddev, min, max; int count; };
    Stats compute_stats(const std::vector<double>& values) const;

    /// Clear all entries
    void clear() { entries_.clear(); }
    size_t size() const { return entries_.size(); }

private:
    std::string output_dir_;
    std::vector<SessionEntry> entries_;

    /// Generate chart as PNG using OpenCV drawing
    void generate_chart(const std::string& path) const;

    /// Write Markdown report
    void write_markdown(const std::string& path,
                        const nlohmann::json& params) const;
};

} // namespace fusion
