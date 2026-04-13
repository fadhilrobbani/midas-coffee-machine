/**
 * drpai_detector.cpp — DRP-AI Detector Stub (Renesas RZ/V2H NPU)
 *
 * This is a placeholder. Replace the detect() body with actual
 * DRP-AI TVM Runtime calls when the Renesas SDK is available.
 */

#include "drpai_detector.h"
#include <iostream>

namespace tray {

DrpaiDetector::DrpaiDetector(const std::string& model_dir, float conf_thresh)
    : model_dir_(model_dir), conf_thresh_(conf_thresh) {

    std::cout << "[DETECTOR] DRP-AI stub initialized." << std::endl;
    std::cout << "[DETECTOR] Model dir: " << model_dir << std::endl;
    std::cout << "[DETECTOR] NOTE: Replace this stub with actual DRP-AI "
              << "TVM Runtime implementation." << std::endl;

    // TODO: Initialize DRP-AI
    // 1. Open /dev/drpai0
    // 2. Load DRP-AI object files from model_dir
    // 3. Allocate input/output buffers
}


DrpaiDetector::~DrpaiDetector() {
    // TODO: Release DRP-AI resources
    // 1. Free buffers
    // 2. Close /dev/drpai0
}


std::vector<DetectionBox> DrpaiDetector::detect(const cv::Mat& frame) {
    // TODO: Implement actual DRP-AI inference
    //
    // Pseudocode:
    // 1. Preprocess frame (resize to model input, normalize)
    //    cv::Mat resized;
    //    cv::resize(frame, resized, cv::Size(640, 640));
    //    // Convert BGR->RGB, float32, normalize /255
    //
    // 2. Copy input data to DRP-AI input buffer
    //    memcpy(drpai_input_buf, resized.data, input_size);
    //
    // 3. Start DRP-AI inference
    //    ioctl(drpai_fd, DRPAI_START, &drpai_data);
    //
    // 4. Wait for completion
    //    struct drpai_status_t status;
    //    do { ioctl(drpai_fd, DRPAI_GET_STATUS, &status); }
    //    while (status.status == DRPAI_STATUS_RUN);
    //
    // 5. Read output buffer & postprocess (NMS, threshold)
    //    memcpy(output_data, drpai_output_buf, output_size);
    //    // Parse YOLOv8 output format → DetectionBox
    //
    // 6. Return detections

    std::cerr << "[DETECTOR] WARNING: DRP-AI stub called — "
              << "returning empty detections. "
              << "Implement actual inference here." << std::endl;

    return {};
}


// ── Factory method ──────────────────────────────────────────────────────
#ifdef USE_DRPAI
std::unique_ptr<IDetector> IDetector::create(const std::string& model_path,
                                              bool /*use_gpu*/) {
    return std::make_unique<DrpaiDetector>(model_path);
}
#endif

} // namespace tray
