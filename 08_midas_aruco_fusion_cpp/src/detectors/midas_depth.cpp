/**
 * @file midas_depth.cpp
 * @brief MiDaS depth estimation implementation.
 * Port of Python midas_volumecup/depth.py.
 */

#include "midas_depth.h"
#include "image_preprocess.h"
#include <opencv2/imgproc.hpp>
#include <algorithm>
#include <numeric>
#include <cmath>
#include <iostream>

namespace fusion {

#ifdef HAS_ONNXRUNTIME
    Ort::Env& get_ort_env() {
        static Ort::Env env(ORT_LOGGING_LEVEL_WARNING, "FusionEnv");
        return env;
    }
#endif

MidasDepthEstimator::MidasDepthEstimator(const std::string& model_path,
                                         int num_threads)
{
#ifdef HAS_ONNXRUNTIME
    if (model_path.empty()) return;
    try {
        Ort::SessionOptions opts;
        opts.SetIntraOpNumThreads(num_threads);
        opts.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_BASIC);
        session_ = std::make_unique<Ort::Session>(get_ort_env(), model_path.c_str(), opts);

        // Get input/output names
        auto in_name = session_->GetInputNameAllocated(0, allocator_);
        auto out_name = session_->GetOutputNameAllocated(0, allocator_);
        input_names_ = {in_name.get()};
        output_names_ = {out_name.get()};

        // Get input dimensions
        auto in_shape = session_->GetInputTypeInfo(0)
                           .GetTensorTypeAndShapeInfo().GetShape();
        if (in_shape.size() >= 4) {
            input_height_ = static_cast<int>(in_shape[2]);
            input_width_ = static_cast<int>(in_shape[3]);
        }
        model_loaded_ = true;
        std::cout << "[MiDaS] Model loaded: " << model_path
                  << " (input: " << input_width_ << "x" << input_height_ << ")\n";
    } catch (const Ort::Exception& e) {
        std::cerr << "[MiDaS] Failed to load model: " << e.what() << "\n";
    }
#else
    (void)model_path;
    (void)num_threads;
    std::cerr << "[MiDaS] ONNX Runtime not available. Depth inference disabled.\n";
#endif
}

std::vector<float> MidasDepthEstimator::preprocess(const cv::Mat& image) const {
    cv::Mat rgb, resized, float_img;
    cv::cvtColor(image, rgb, cv::COLOR_BGR2RGB);
    cv::resize(rgb, resized, cv::Size(input_width_, input_height_));
    resized.convertTo(float_img, CV_32FC3, 1.0 / 255.0);

    // Normalize with ImageNet mean/std
    cv::Mat channels[3];
    cv::split(float_img, channels);
    channels[0] = (channels[0] - 0.485f) / 0.229f;
    channels[1] = (channels[1] - 0.456f) / 0.224f;
    channels[2] = (channels[2] - 0.406f) / 0.225f;

    // CHW layout
    std::vector<float> data(3 * input_height_ * input_width_);
    int plane_size = input_height_ * input_width_;
    for (int c = 0; c < 3; ++c) {
        auto* src = channels[c].ptr<float>();
        std::copy(src, src + plane_size, data.data() + c * plane_size);
    }
    return data;
}

cv::Mat MidasDepthEstimator::infer(const std::vector<float>& input_data) const {
#ifdef HAS_ONNXRUNTIME
    if (!session_) return cv::Mat();

    std::array<int64_t, 4> shape = {1, 3, input_height_, input_width_};
    auto mem_info = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    auto input_tensor = Ort::Value::CreateTensor<float>(
        mem_info, const_cast<float*>(input_data.data()),
        input_data.size(), shape.data(), shape.size());

    auto outputs = session_->Run(Ort::RunOptions{nullptr},
        input_names_.data(), &input_tensor, 1,
        output_names_.data(), 1);

    auto& out_tensor = outputs[0];
    auto out_shape = out_tensor.GetTensorTypeAndShapeInfo().GetShape();
    int h = static_cast<int>(out_shape[out_shape.size() - 2]);
    int w = static_cast<int>(out_shape[out_shape.size() - 1]);
    const float* out_data = out_tensor.GetTensorData<float>();

    cv::Mat depth(h, w, CV_32FC1, const_cast<float*>(out_data));
    return depth.clone();
#else
    (void)input_data;
    return cv::Mat();
#endif
}

cv::Mat MidasDepthEstimator::process(const cv::Mat& image,
                                      std::optional<BBox> roi) {
    if (!model_loaded_ || image.empty()) return cv::Mat();

    cv::Mat input = roi ? crop_roi(image, *roi) : image;
    auto preprocessed = preprocess(input);
    cv::Mat depth = infer(preprocessed);

    if (depth.empty()) return depth;

    // Resize to input image size
    cv::resize(depth, depth, input.size());

    // Paste back if ROI was used
    if (roi) {
        cv::Mat full_depth = cv::Mat::zeros(image.size(), CV_32FC1);
        depth = paste_depth(depth, full_depth, *roi);
    }

    // EMA temporal smoothing
    {
        std::lock_guard<std::mutex> lock(ema_mutex_);
        if (depth_ema_.empty() || depth_ema_.size() != depth.size()) {
            depth_ema_ = depth.clone();
        } else {
            cv::addWeighted(depth, ema_alpha_, depth_ema_, 1.0 - ema_alpha_,
                            0, depth_ema_);
        }
        return depth_ema_.clone();
    }
}

cv::Mat MidasDepthEstimator::get_smoothed_depth(const cv::Mat& depth_raw) const {
    if (depth_raw.empty()) return depth_raw;
    cv::Mat smoothed;
    cv::bilateralFilter(depth_raw, smoothed, 9, 75, 75);
    return smoothed;
}

double MidasDepthEstimator::get_tray_depth(const cv::Mat& depth_map) const {
    if (depth_map.empty()) return 0.0;
    int h = depth_map.rows;
    int strip_h = std::max(1, h / 10);
    cv::Mat strip = depth_map(cv::Range(h - strip_h, h), cv::Range::all());
    return cv::mean(strip)[0];
}

double MidasDepthEstimator::get_rim_depth(const cv::Mat& depth_map,
                                           const BBox& bbox) const {
    if (depth_map.empty()) return 0.0;
    int rim_h = std::max(1, (bbox.y2 - bbox.y1) / 10);
    int y1 = std::max(0, bbox.y1);
    int y2 = std::min(depth_map.rows, y1 + rim_h);
    int x1 = std::max(0, bbox.x1);
    int x2 = std::min(depth_map.cols, bbox.x2);
    if (y2 <= y1 || x2 <= x1) return 0.0;
    cv::Mat roi = depth_map(cv::Range(y1, y2), cv::Range(x1, x2));
    return cv::mean(roi)[0];
}

double MidasDepthEstimator::get_standardized_depth(const cv::Mat& depth_map,
                                                    const BBox& bbox) const {
    if (depth_map.empty()) return 0.0;
    double tray = get_tray_depth(depth_map);
    double rim = get_rim_depth(depth_map, bbox);
    if (tray <= 0) return 0.0;
    return std::clamp((tray - rim) / tray * 1000.0, 0.0, 1000.0);
}

cv::Mat MidasDepthEstimator::crop_roi(const cv::Mat& image, const BBox& bbox,
                                       double padding) {
    int pw = static_cast<int>((bbox.x2 - bbox.x1) * padding);
    int ph = static_cast<int>((bbox.y2 - bbox.y1) * padding);
    int x1 = std::max(0, bbox.x1 - pw);
    int y1 = std::max(0, bbox.y1 - ph);
    int x2 = std::min(image.cols, bbox.x2 + pw);
    int y2 = std::min(image.rows, bbox.y2 + ph);
    return image(cv::Range(y1, y2), cv::Range(x1, x2)).clone();
}

cv::Mat MidasDepthEstimator::paste_depth(const cv::Mat& depth_roi,
                                          const cv::Mat& full_frame,
                                          const BBox& bbox, double padding) {
    cv::Mat result = full_frame.clone();
    int pw = static_cast<int>((bbox.x2 - bbox.x1) * padding);
    int ph = static_cast<int>((bbox.y2 - bbox.y1) * padding);
    int x1 = std::max(0, bbox.x1 - pw);
    int y1 = std::max(0, bbox.y1 - ph);
    int x2 = std::min(result.cols, bbox.x2 + pw);
    int y2 = std::min(result.rows, bbox.y2 + ph);

    cv::Mat resized;
    cv::resize(depth_roi, resized, cv::Size(x2 - x1, y2 - y1));
    resized.copyTo(result(cv::Range(y1, y2), cv::Range(x1, x2)));
    return result;
}

} // namespace fusion
