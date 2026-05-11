/**
 * @file async_midas.h
 * @brief Asynchronous MiDaS inference wrapper.
 * Runs depth estimation on a background thread with lock-free result sharing.
 */

#pragma once

#include <opencv2/core.hpp>
#include <thread>
#include <atomic>
#include <mutex>
#include <condition_variable>
#include "midas_depth.h"

namespace fusion {

class AsyncMidas {
public:
    explicit AsyncMidas(const std::string& model_path,
                        int num_threads = 2);
    ~AsyncMidas();

    /// Submit a frame for asynchronous processing
    void submit(const cv::Mat& frame, std::optional<BBox> roi = std::nullopt);

    /// Get the latest depth result (non-blocking)
    cv::Mat get_latest_depth() const;

    /// Check if a new result is available
    bool has_new_result() const { return new_result_.load(); }

    /// Check if model is ready
    bool is_ready() const { return estimator_.is_ready(); }

    /// Start/stop the worker thread
    void start();
    void stop();

private:
    MidasDepthEstimator estimator_;

    std::thread worker_;
    std::atomic<bool> running_{false};
    mutable std::atomic<bool> new_result_{false};

    // Input buffer (latest frame)
    cv::Mat input_frame_;
    std::optional<BBox> input_roi_;
    std::mutex input_mutex_;
    std::condition_variable input_cv_;
    std::atomic<bool> has_input_{false};

    // Output buffer (latest depth)
    cv::Mat output_depth_;
    mutable std::mutex output_mutex_;

    void worker_loop();
};

} // namespace fusion
