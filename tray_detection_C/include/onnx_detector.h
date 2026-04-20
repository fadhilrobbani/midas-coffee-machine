#pragma once
/**
 * onnx_detector.h — ONNX Detector via OpenCV DNN (PC: CPU/GPU)
 */

#include "detector.h"
#include <opencv2/dnn.hpp>

namespace tray {

class OnnxDetector : public IDetector {
public:
    /**
     * @param model_path  Path to ONNX model file
     * @param use_gpu     Use CUDA backend if available
     * @param conf_thresh Minimum confidence threshold
     * @param nms_thresh  NMS IoU threshold
     */
    OnnxDetector(const std::string& model_path,
                 bool use_gpu = false,
                 float conf_thresh = 0.40f,
                 float nms_thresh = 0.45f);

    std::vector<DetectionBox> detect(const cv::Mat& frame) override;

private:
    cv::dnn::Net net_;
    float conf_thresh_;
    float nms_thresh_;
    int input_width_  = 640;
    int input_height_ = 640;

    // Post-processing helpers
    std::vector<DetectionBox> postprocess(const cv::Mat& output,
                                          int orig_w, int orig_h);
};

} // namespace tray
