/**
 * @file yolo_detector.h
 * @brief YOLO cup detection via ONNX Runtime.
 * Port of Python midas_volumecup/detector.py.
 */

#pragma once

#include <opencv2/core.hpp>
#include <vector>
#include <string>
#include "height_math.h"  // BBox

#ifdef HAS_ONNXRUNTIME
#include <onnxruntime_cxx_api.h>
#endif

namespace fusion {

struct Detection {
    BBox bbox;
    float confidence = 0.0f;
    int class_id = 0;
};

class YoloDetector {
public:
    explicit YoloDetector(const std::string& model_path = "",
                          float conf_thresh = 0.5f,
                          float nms_thresh = 0.45f,
                          int num_threads = 2);

    std::vector<Detection> detect(const cv::Mat& frame,
                                   float roi_ratio = 1.0f) const;

    bool is_ready() const { return model_loaded_; }

private:
    bool model_loaded_ = false;
    float conf_thresh_;
    float nms_thresh_;
    int input_size_ = 640;

#ifdef HAS_ONNXRUNTIME
    Ort::Env env_;
    std::unique_ptr<Ort::Session> session_;
    Ort::AllocatorWithDefaultOptions allocator_;
    std::vector<const char*> input_names_;
    std::vector<const char*> output_names_;
#endif

    std::vector<float> preprocess(const cv::Mat& frame, float& scale,
                                   int& pad_x, int& pad_y) const;
    std::vector<Detection> postprocess(const float* data, int num_detections,
                                        float scale, int pad_x, int pad_y,
                                        int orig_w, int orig_h) const;
    static std::vector<Detection> nms(std::vector<Detection>& dets,
                                       float threshold);
};

} // namespace fusion
