/**
 * onnx_detector.cpp — ONNX Detector via OpenCV DNN (PC: CPU/GPU)
 *
 * Loads YOLOv8 ONNX model and runs inference using cv::dnn module.
 * Supports CPU (default) and CUDA GPU backend.
 */

#include "onnx_detector.h"
#include <iostream>
#include <opencv2/imgproc.hpp>

namespace tray {

OnnxDetector::OnnxDetector(const std::string& model_path,
                           bool use_gpu,
                           float conf_thresh,
                           float nms_thresh)
    : conf_thresh_(conf_thresh), nms_thresh_(nms_thresh) {
    std::cout << "[DETECTOR] Loading ONNX model: " << model_path << std::endl;

    net_ = cv::dnn::readNetFromONNX(model_path);

    if (net_.empty()) {
        std::cerr << "[DETECTOR] ERROR: Failed to load ONNX model!" << std::endl;
        return;
    }

    if (use_gpu) {
        net_.setPreferableBackend(cv::dnn::DNN_BACKEND_CUDA);
        net_.setPreferableTarget(cv::dnn::DNN_TARGET_CUDA);
        std::cout << "[DETECTOR] Backend: CUDA (GPU)" << std::endl;
    } else {
        net_.setPreferableBackend(cv::dnn::DNN_BACKEND_OPENCV);
        net_.setPreferableTarget(cv::dnn::DNN_TARGET_CPU);
        std::cout << "[DETECTOR] Backend: OpenCV (CPU)" << std::endl;
    }

    std::cout << "[DETECTOR] Model loaded successfully." << std::endl;
}


std::vector<DetectionBox> OnnxDetector::detect(const cv::Mat& frame) {
    if (net_.empty()) return {};

    int orig_w = frame.cols;
    int orig_h = frame.rows;

    // Pre-process: letterbox to 640x640
    cv::Mat blob = cv::dnn::blobFromImage(
        frame, 1.0 / 255.0,
        cv::Size(input_width_, input_height_),
        cv::Scalar(0, 0, 0), true, false
    );

    net_.setInput(blob);

    // Forward pass
    std::vector<cv::Mat> outputs;
    net_.forward(outputs, net_.getUnconnectedOutLayersNames());

    return postprocess(outputs[0], orig_w, orig_h);
}


std::vector<DetectionBox> OnnxDetector::postprocess(
    const cv::Mat& output, int orig_w, int orig_h) {

    // YOLOv8 output format: [1, num_classes+4, num_detections]
    // Transpose to [num_detections, num_classes+4]
    int rows = output.size[2];  // number of detections
    int cols = output.size[1];  // 4 + num_classes

    cv::Mat det = output.reshape(1, cols).t();  // [rows, cols]

    std::vector<cv::Rect> boxes;
    std::vector<float> confidences;
    std::vector<int> class_ids;

    float x_scale = static_cast<float>(orig_w) / input_width_;
    float y_scale = static_cast<float>(orig_h) / input_height_;

    for (int i = 0; i < rows; i++) {
        const float* row_ptr = det.ptr<float>(i);

        // First 4 values: cx, cy, w, h
        float cx = row_ptr[0];
        float cy = row_ptr[1];
        float w  = row_ptr[2];
        float h  = row_ptr[3];

        // Find best class score (cols 4..end)
        float max_score = 0.0f;
        int best_class = 0;
        for (int c = 4; c < cols; c++) {
            if (row_ptr[c] > max_score) {
                max_score = row_ptr[c];
                best_class = c - 4;
            }
        }

        if (max_score < conf_thresh_) continue;

        // Convert to pixel coordinates
        int x1 = static_cast<int>((cx - w / 2.0f) * x_scale);
        int y1 = static_cast<int>((cy - h / 2.0f) * y_scale);
        int bw = static_cast<int>(w * x_scale);
        int bh = static_cast<int>(h * y_scale);

        boxes.emplace_back(x1, y1, bw, bh);
        confidences.push_back(max_score);
        class_ids.push_back(best_class);
    }

    // NMS
    std::vector<int> indices;
    cv::dnn::NMSBoxes(boxes, confidences, conf_thresh_, nms_thresh_, indices);

    std::vector<DetectionBox> results;
    for (int idx : indices) {
        DetectionBox db;
        db.x1 = boxes[idx].x;
        db.y1 = boxes[idx].y;
        db.x2 = boxes[idx].x + boxes[idx].width;
        db.y2 = boxes[idx].y + boxes[idx].height;
        db.confidence = confidences[idx];
        db.class_id = class_ids[idx];
        db.label = "cup";  // Single-class model
        results.push_back(db);
    }

    return results;
}


// ── Factory method ──────────────────────────────────────────────────────
#ifdef USE_ONNX
std::unique_ptr<IDetector> IDetector::create(const std::string& model_path,
                                              bool use_gpu) {
    return std::make_unique<OnnxDetector>(model_path, use_gpu);
}
#endif

} // namespace tray
