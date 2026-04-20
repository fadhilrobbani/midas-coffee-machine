#pragma once
/**
 * detector.h — Abstract Detector Interface (IDetector)
 *
 * Menyediakan interface untuk deteksi objek (cup/tray).
 * Implementasi:
 *   - OnnxDetector  (PC: CPU/GPU via OpenCV DNN)
 *   - DrpaiDetector (RZ/V2H: NPU via DRP-AI)
 */

#include <vector>
#include <string>
#include <memory>
#include <opencv2/core.hpp>

namespace tray {

struct DetectionBox {
    int x1, y1, x2, y2;
    float confidence;
    int class_id;
    std::string label;
};

/**
 * Abstract interface for object detection.
 */
class IDetector {
public:
    virtual ~IDetector() = default;

    /**
     * Run detection on a frame.
     * @param frame  BGR image
     * @return vector of detected bounding boxes
     */
    virtual std::vector<DetectionBox> detect(const cv::Mat& frame) = 0;

    /**
     * Factory method: create appropriate detector based on compile flags.
     * @param model_path  Path to model (ONNX for PC, DRP-AI dir for RZ/V2H)
     * @param use_gpu     Use CUDA backend (PC only, ignored on RZ/V2H)
     */
    static std::unique_ptr<IDetector> create(const std::string& model_path,
                                              bool use_gpu = false);
};

} // namespace tray
