/**
 * @file live_pipeline.h
 * @brief 3-stage parallel processing pipeline.
 *
 * Architecture:
 *   Stage 1 (Camera Thread) → RingBuffer → Stage 2 (Process Thread) → Display
 *   Stage 2 also sends frames to Stage 3 (Async MiDaS) for depth.
 */

#pragma once

#include <opencv2/core.hpp>
#include <opencv2/videoio.hpp>
#include <thread>
#include <atomic>
#include <mutex>
#include <functional>
#include <string>

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

struct PipelineConfig {
    int camera_id = 0;
    int frame_width = 2592;
    int frame_height = 1944;
    std::string midas_model_path;
    std::string yolo_model_path;
    std::string camera_params_path;
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
    double cup_height_cm = 0;
    double aruco_distance_cm = 0;
    double diameter_cm = 0;
    double volume_ml = 0;
    double fps = 0;
    int frame_count = 0;
    bool aruco_found = false;
    bool cup_found = false;
};

class LivePipeline {
public:
    explicit LivePipeline(const PipelineConfig& config);
    ~LivePipeline();

    /// Start the pipeline
    bool start();

    /// Stop the pipeline
    void stop();

    /// Get the latest processed frame (for display)
    cv::Mat get_display_frame() const;

    /// Get the latest depth colormap
    cv::Mat get_depth_colormap() const;

    /// Get current metrics
    PipelineMetrics get_metrics() const;

    /// Set new calibration data
    void set_calibration(const CalibData& calib);
    
    // Feature toggles
    void set_normalize_lighting(bool enable) { normalize_ = enable; }
    void set_bw_mode(bool enable) { bw_mode_ = enable; }
    void set_show_depth(bool enable) { show_depth_ = enable; }

    // Toggle legacy overlays
    void toggle_depth_overlay() { show_depth_ = !show_depth_; }
    void toggle_aruco_overlay() { show_aruco_ = !show_aruco_; }
    void toggle_normalize() { normalize_ = !normalize_; }

    /// Get session reporter reference
    SessionReporter& reporter() { return reporter_; }

    /// Get MoilUndistorter pointer
    MoilUndistorter* moil() { return moil_.get(); }

    bool is_running() const { return running_; }

private:
    PipelineConfig config_;
    CalibData calib_data_;

    // Components
    std::unique_ptr<ArucoDetector> aruco_;
    std::unique_ptr<YoloDetector> yolo_;
    std::unique_ptr<MoilUndistorter> moil_;
    std::unique_ptr<AsyncMidas> async_midas_;
    SessionReporter reporter_;

    // Threading
    RingBuffer<4> frame_buffer_;
    std::thread camera_thread_;
    std::thread process_thread_;
    std::atomic<bool> running_{false};

    // State
    cv::Mat display_frame_;
    cv::Mat depth_colormap_;
    PipelineMetrics metrics_;
    mutable std::mutex display_mutex_;
    mutable std::mutex metrics_mutex_;

    std::atomic<bool> show_depth_{false};
    std::atomic<bool> show_aruco_{true};
    std::atomic<bool> normalize_{true};
    std::atomic<bool> bw_mode_{false};

    // Thread functions
    void camera_loop();
    void process_loop();

    // Processing helpers
    void process_frame(cv::Mat& frame);
    void compute_height(cv::Mat& frame, const std::vector<ArucoResult>& aruco_res,
                        const std::vector<Detection>& yolo_dets,
                        const cv::Mat& depth_map);
    void draw_overlay(cv::Mat& frame, const PipelineMetrics& m);
};

} // namespace fusion
