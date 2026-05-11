/**
 * @file midas_depth.h
 * @brief MiDaS depth estimation via ONNX Runtime.
 *
 * Port of Python midas_volumecup/depth.py.
 * Guarded by HAS_ONNXRUNTIME compile flag.
 */

#pragma once

#include <opencv2/core.hpp>
#include <optional>
#include <vector>
#include <mutex>
#include <string>
#include "height_math.h"  // BBox

#ifdef HAS_ONNXRUNTIME
#include <onnxruntime_cxx_api.h>
#endif

namespace fusion {

/**
 * @brief MiDaS monocular depth estimator using ONNX Runtime.
 */
class MidasDepthEstimator {
public:
    /**
     * @param model_path  Path to midas_v21_small_256.onnx
     * @param num_threads ONNX Runtime intra-op thread count
     */
    explicit MidasDepthEstimator(const std::string& model_path = "",
                                 int num_threads = 2);

    /**
     * @brief Run depth inference on an image.
     * @param image BGR input image
     * @param roi   Optional ROI for focused inference
     * @return Depth map (CV_32F, same size as input or ROI)
     */
    cv::Mat process(const cv::Mat& image,
                    std::optional<BBox> roi = std::nullopt);

    /// Get bilaterally smoothed depth map for visualization
    cv::Mat get_smoothed_depth(const cv::Mat& depth_raw) const;

    /// Sample tray depth (bottom 10% of depth map)
    double get_tray_depth(const cv::Mat& depth_map) const;

    /// Sample rim depth from bbox top region
    double get_rim_depth(const cv::Mat& depth_map, const BBox& bbox) const;

    /// Normalize depth to 0-1000 range
    double get_standardized_depth(const cv::Mat& depth_map,
                                  const BBox& bbox) const;

    /// Check if model is loaded
    bool is_ready() const { return model_loaded_; }

    /// Crop ROI with padding
    static cv::Mat crop_roi(const cv::Mat& image, const BBox& bbox,
                            double padding = 0.15);

    /// Paste depth ROI back into full-frame depth map
    static cv::Mat paste_depth(const cv::Mat& depth_roi, const cv::Mat& full_frame,
                               const BBox& bbox, double padding = 0.15);

private:
    bool model_loaded_ = false;
    int input_width_ = 256;
    int input_height_ = 256;

#ifdef HAS_ONNXRUNTIME
    Ort::Env env_;
    std::unique_ptr<Ort::Session> session_;
    Ort::AllocatorWithDefaultOptions allocator_;
    std::vector<const char*> input_names_;
    std::vector<const char*> output_names_;
#endif

    /// Preprocess: BGR → RGB → resize → float32 → normalize → CHW
    std::vector<float> preprocess(const cv::Mat& image) const;

    /// Run ONNX inference
    cv::Mat infer(const std::vector<float>& input_data) const;

    /// EMA temporal smoothing state
    cv::Mat depth_ema_;
    double ema_alpha_ = 0.4;
    std::mutex ema_mutex_;
};

} // namespace fusion
