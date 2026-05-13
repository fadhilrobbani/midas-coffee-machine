/**
 * @file live_pipeline.h
 * @brief 3-stage parallel processing pipeline.
 *
 * Full feature parity with Python 07_midas_aruco_fusion/core/live_pipeline.py:
 * - EMA smoothing for cup heights (alpha=0.35)
 * - MiDaS rate-limited to 5 FPS
 * - Fast-path for Type 5/7 (no MiDaS needed)
 * - Multi-cup detection (2 cups)
 * - Dynamic UI scaling like Python
 * - Recording / Screenshot
 * - LED state detection
 */

#pragma once

#include <opencv2/core.hpp>
#include <opencv2/videoio.hpp>
#include <thread>
#include <atomic>
#include <mutex>
#include <functional>
#include <string>
#include <optional>
#include <chrono>
#include <set>
#include <array>

#include "ring_buffer.h"
#include "aruco_detector.h"
#include "yolo_detector.h"
#include "midas_depth.h"
#include "async_midas.h"
#include "moil_undistorter.h"
#include "image_preprocess.h"
#include "height_math.h"
#include "volume_math.h"
#include "calibration_storage.h"
#include "session_reporter.h"

namespace fusion {

// ─── Calibration types that don't need MiDaS ────────────────────────────────
static const std::set<int> CTYPE_NO_MIDAS = {5, 7};

struct PipelineConfig {
    int camera_id = 0;
    int frame_width = 2592;
    int frame_height = 1944;
    std::string midas_model_path;
    std::string yolo_model_path;
    std::string camera_params_path;
    std::string camera_name;             // Moildev profile name in JSON
    std::string calibration_path = "calibration.json";
    double marker_size_cm = 5.0;
    bool enable_moildev = true;
    bool enable_normalize = true;
    bool enable_depth = true;
    int moil_mode = 2;
    double moil_zoom = 1.0;
    double target_cup_cm = 7.6;
    int manual_exposure = 0;
};

struct PipelineMetrics {
    // Per-cup data (up to 2)
    double cup_height_cm[2]  = {0, 0};
    double diameter_cm[2]    = {0, 0};
    double volume_ml[2]      = {0, 0};
    bool   cup_found[2]      = {false, false};

    double aruco_distance_cm = 0;
    double fps = 0;
    int frame_count = 0;
    bool aruco_found = false;
    bool led_on      = false;
};

class LivePipeline {
public:
    explicit LivePipeline(const PipelineConfig& config);
    ~LivePipeline();

    bool init_models();
    bool start();
    void stop();

    /// Get the latest processed display frame
    cv::Mat get_display_frame() const;
    cv::Mat get_depth_colormap() const;

    PipelineMetrics get_metrics() const;
    void set_calibration(const CalibData& calib);

    // Feature toggles (thread-safe)
    void set_normalize_lighting(bool e) { normalize_ = e; }
    void set_bw_mode(bool e)            { bw_mode_ = e; }
    void set_smart_exposure(double exp, double gain, double bri) {
        requested_exposure_ = exp;
        requested_gain_ = gain;
        requested_brightness_ = bri;
    }
    void set_show_depth(bool e)         { show_depth_ = e; }
    void toggle_depth_overlay()         { show_depth_ = !show_depth_; }
    void toggle_aruco_overlay()         { show_aruco_ = !show_aruco_; }
    void toggle_normalize()             { normalize_ = !normalize_; }

    // Recording / screenshot (called from GUI thread)
    void toggle_recording();
    void save_screenshot(const std::string& dir);

    SessionReporter& reporter()     { return reporter_; }
    MoilUndistorter* moil()         { return moil_.get(); }
    bool is_running() const         { return running_; }

    // Focal length (populated during start(), exposed for GUI)
    double focal_px() const         { return focal_px_; }

private:
    // ─── Config & State ───────────────────────────────────────────────
    PipelineConfig config_;
    CalibData      calib_data_;
    double         focal_px_      = 500.0;   // overwritten from JSON/ArUco

    // ─── Per-frame tracking state ─────────────────────────────────────
    double           z_tray_live_ = 0.0;
    double           cup_heights_ema_[2] = {-1.0, -1.0}; // <0 = unset
    std::array<BBox, 2> cup_bboxes_{};
    int              cup_count_ = 0;
    std::optional<BBox> aruco_roi_;
    double           last_midas_t_ = 0.0;
    cv::Mat          last_depth_norm_;        // normalized depth for PiP
    bool             led_on_ = false;
    static constexpr double EMA_ALPHA       = 0.35;
    static constexpr double MIDAS_FPS_LIMIT = 5.0;

    // ─── Recording ────────────────────────────────────────────────────
    bool             is_recording_ = false;
    cv::VideoWriter  video_writer_;
    mutable std::mutex recording_mutex_;

    // ─── Components ───────────────────────────────────────────────────
    std::unique_ptr<ArucoDetector>   aruco_;
    std::unique_ptr<YoloDetector>    yolo_;
    std::unique_ptr<MoilUndistorter> moil_;
    std::unique_ptr<MidasDepthEstimator> midas_;  // direct (rate-limited)
    SessionReporter  reporter_;

    // ─── Threading ────────────────────────────────────────────────────
    RingBuffer<4>  frame_buffer_;
    std::thread    camera_thread_;
    std::thread    process_thread_;
    std::atomic<bool> running_{false};

    cv::Mat display_frame_;
    cv::Mat depth_colormap_;
    PipelineMetrics metrics_;
    mutable std::mutex display_mutex_;
    mutable std::mutex metrics_mutex_;
    mutable std::mutex calib_mutex_;

    std::atomic<bool> show_depth_{false};
    std::atomic<bool> show_aruco_{true};
    std::atomic<bool> normalize_{false};
    std::atomic<bool> bw_mode_{false};
    std::atomic<double> requested_exposure_{-1.0};
    std::atomic<double> requested_gain_{-1.0};
    std::atomic<double> requested_brightness_{-1000.0};

    // ─── Thread functions ─────────────────────────────────────────────
    void camera_loop();
    void process_loop();

    // ─── Per-frame helpers ────────────────────────────────────────────
    void process_frame(cv::Mat& frame);
    void run_aruco_yolo(const cv::Mat& frame,
                        std::vector<ArucoResult>& aruco_res,
                        std::vector<Detection>& yolo_dets);
    void run_midas_rate_limited(const cv::Mat& frame,
                                const std::vector<Detection>& yolo_dets);
    void compute_heights(const cv::Mat& frame,
                         const cv::Mat& depth_map);
    void draw_overlay(cv::Mat& frame);
    void draw_pip_depth(cv::Mat& frame);
};

} // namespace fusion
