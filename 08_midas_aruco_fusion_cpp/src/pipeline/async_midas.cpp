/**
 * @file async_midas.cpp
 * @brief Async MiDaS worker implementation.
 */

#include "async_midas.h"
#include <iostream>

namespace fusion {

AsyncMidas::AsyncMidas(const std::string& model_path, int num_threads)
    : estimator_(model_path, num_threads)
{}

AsyncMidas::~AsyncMidas() {
    stop();
}

void AsyncMidas::start() {
    if (running_) return;
    running_ = true;
    worker_ = std::thread(&AsyncMidas::worker_loop, this);
}

void AsyncMidas::stop() {
    if (!running_) return;
    running_ = false;
    input_cv_.notify_all();
    if (worker_.joinable()) worker_.join();
}

void AsyncMidas::submit(const cv::Mat& frame, std::optional<BBox> roi) {
    {
        std::lock_guard<std::mutex> lock(input_mutex_);
        input_frame_ = frame.clone();
        input_roi_ = roi;
        has_input_ = true;
    }
    input_cv_.notify_one();
}

cv::Mat AsyncMidas::get_latest_depth() const {
    std::lock_guard<std::mutex> lock(output_mutex_);
    new_result_ = false;
    return output_depth_.clone();
}

void AsyncMidas::worker_loop() {
    while (running_) {
        cv::Mat frame;
        std::optional<BBox> roi;

        {
            std::unique_lock<std::mutex> lock(input_mutex_);
            input_cv_.wait(lock, [this]() {
                return has_input_.load() || !running_.load();
            });
            if (!running_) break;
            frame = std::move(input_frame_);
            roi = input_roi_;
            has_input_ = false;
        }

        if (frame.empty()) continue;

        auto depth = estimator_.process(frame, roi);
        if (!depth.empty()) {
            std::lock_guard<std::mutex> lock(output_mutex_);
            output_depth_ = std::move(depth);
            new_result_ = true;
        }
    }
}

} // namespace fusion
