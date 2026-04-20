#pragma once
/**
 * drpai_detector.h — DRP-AI Detector Stub (Renesas RZ/V2H NPU)
 *
 * Placeholder implementation. Fill in with actual DRP-AI TVM Runtime
 * calls when the Renesas SDK is available.
 */

#include "detector.h"

namespace tray {

class DrpaiDetector : public IDetector {
public:
    /**
     * @param model_dir   Path to DRP-AI compiled model directory
     * @param conf_thresh Minimum confidence threshold
     */
    DrpaiDetector(const std::string& model_dir,
                  float conf_thresh = 0.40f);

    ~DrpaiDetector() override;

    std::vector<DetectionBox> detect(const cv::Mat& frame) override;

private:
    std::string model_dir_;
    float conf_thresh_;
    // TODO: Add DRP-AI handle, input/output buffer pointers, etc.
    // void* drpai_handle_ = nullptr;
};

} // namespace tray
