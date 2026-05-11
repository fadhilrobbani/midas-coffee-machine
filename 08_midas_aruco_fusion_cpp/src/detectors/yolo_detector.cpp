/**
 * @file yolo_detector.cpp
 * @brief YOLO cup detection implementation.
 * Port of Python midas_volumecup/detector.py.
 */

#include "yolo_detector.h"
#include <opencv2/imgproc.hpp>
#include <opencv2/dnn.hpp>
#include <algorithm>
#include <iostream>
#include <cmath>

namespace fusion {

YoloDetector::YoloDetector(const std::string& model_path, float conf_thresh,
                           float nms_thresh, int num_threads)
    : conf_thresh_(conf_thresh), nms_thresh_(nms_thresh)
#ifdef HAS_ONNXRUNTIME
    , env_(ORT_LOGGING_LEVEL_WARNING, "YOLO")
#endif
{
#ifdef HAS_ONNXRUNTIME
    if (model_path.empty()) return;
    try {
        Ort::SessionOptions opts;
        opts.SetIntraOpNumThreads(num_threads);
        opts.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
        session_ = std::make_unique<Ort::Session>(env_, model_path.c_str(), opts);

        auto in_name = session_->GetInputNameAllocated(0, allocator_);
        auto out_name = session_->GetOutputNameAllocated(0, allocator_);
        input_names_ = {in_name.get()};
        output_names_ = {out_name.get()};

        auto in_shape = session_->GetInputTypeInfo(0)
                           .GetTensorTypeAndShapeInfo().GetShape();
        if (in_shape.size() >= 4) {
            input_size_ = static_cast<int>(in_shape[2]);
        }
        model_loaded_ = true;
        std::cout << "[YOLO] Model loaded: " << model_path
                  << " (input: " << input_size_ << "x" << input_size_ << ")\n";
    } catch (const Ort::Exception& e) {
        std::cerr << "[YOLO] Failed to load: " << e.what() << "\n";
    }
#else
    (void)model_path; (void)num_threads;
#endif
}

std::vector<float> YoloDetector::preprocess(const cv::Mat& frame, float& scale,
                                             int& pad_x, int& pad_y) const {
    int h = frame.rows, w = frame.cols;
    scale = std::min(static_cast<float>(input_size_) / w,
                     static_cast<float>(input_size_) / h);
    int nw = static_cast<int>(w * scale), nh = static_cast<int>(h * scale);
    pad_x = (input_size_ - nw) / 2;
    pad_y = (input_size_ - nh) / 2;

    cv::Mat resized, padded;
    cv::resize(frame, resized, cv::Size(nw, nh));
    cv::copyMakeBorder(resized, padded, pad_y, input_size_ - nh - pad_y,
                       pad_x, input_size_ - nw - pad_x,
                       cv::BORDER_CONSTANT, cv::Scalar(114, 114, 114));

    cv::Mat rgb;
    cv::cvtColor(padded, rgb, cv::COLOR_BGR2RGB);
    cv::Mat float_img;
    rgb.convertTo(float_img, CV_32FC3, 1.0 / 255.0);

    // HWC → CHW
    std::vector<float> data(3 * input_size_ * input_size_);
    cv::Mat channels[3];
    cv::split(float_img, channels);
    int plane = input_size_ * input_size_;
    for (int c = 0; c < 3; ++c) {
        std::copy(channels[c].ptr<float>(),
                  channels[c].ptr<float>() + plane,
                  data.data() + c * plane);
    }
    return data;
}

std::vector<Detection> YoloDetector::postprocess(
    const float* data, int num_dets, float scale,
    int pad_x, int pad_y, int orig_w, int orig_h) const
{
    std::vector<Detection> dets;
    // YOLOv8 output: [batch, 5+num_classes, num_boxes] → transposed
    for (int i = 0; i < num_dets; ++i) {
        float cx = data[i];
        float cy = data[num_dets + i];
        float w = data[2 * num_dets + i];
        float h = data[3 * num_dets + i];
        float conf = data[4 * num_dets + i];  // class 0 (cup) score

        if (conf < conf_thresh_) continue;

        // Remove letterbox padding and scale back
        float x1 = (cx - w / 2 - pad_x) / scale;
        float y1 = (cy - h / 2 - pad_y) / scale;
        float x2 = (cx + w / 2 - pad_x) / scale;
        float y2 = (cy + h / 2 - pad_y) / scale;

        Detection det;
        det.bbox.x1 = std::clamp(static_cast<int>(x1), 0, orig_w);
        det.bbox.y1 = std::clamp(static_cast<int>(y1), 0, orig_h);
        det.bbox.x2 = std::clamp(static_cast<int>(x2), 0, orig_w);
        det.bbox.y2 = std::clamp(static_cast<int>(y2), 0, orig_h);
        det.confidence = conf;
        det.class_id = 0;
        dets.push_back(det);
    }

    return nms(dets, nms_thresh_);
}

std::vector<Detection> YoloDetector::nms(std::vector<Detection>& dets,
                                          float threshold) {
    if (dets.empty()) return {};
    std::sort(dets.begin(), dets.end(),
              [](const Detection& a, const Detection& b) {
                  return a.confidence > b.confidence;
              });

    std::vector<Detection> result;
    std::vector<bool> suppressed(dets.size(), false);

    for (size_t i = 0; i < dets.size(); ++i) {
        if (suppressed[i]) continue;
        result.push_back(dets[i]);
        for (size_t j = i + 1; j < dets.size(); ++j) {
            if (suppressed[j]) continue;
            // Compute IoU
            int ix1 = std::max(dets[i].bbox.x1, dets[j].bbox.x1);
            int iy1 = std::max(dets[i].bbox.y1, dets[j].bbox.y1);
            int ix2 = std::min(dets[i].bbox.x2, dets[j].bbox.x2);
            int iy2 = std::min(dets[i].bbox.y2, dets[j].bbox.y2);
            int inter = std::max(0, ix2 - ix1) * std::max(0, iy2 - iy1);
            int area_i = (dets[i].bbox.x2 - dets[i].bbox.x1) *
                         (dets[i].bbox.y2 - dets[i].bbox.y1);
            int area_j = (dets[j].bbox.x2 - dets[j].bbox.x1) *
                         (dets[j].bbox.y2 - dets[j].bbox.y1);
            float iou = static_cast<float>(inter) / (area_i + area_j - inter + 1e-6f);
            if (iou > threshold) suppressed[j] = true;
        }
    }
    return result;
}

std::vector<Detection> YoloDetector::detect(const cv::Mat& frame,
                                             float roi_ratio) const {
    if (!model_loaded_ || frame.empty()) return {};

    cv::Mat input = frame;
    int offset_x = 0, offset_y = 0;
    if (roi_ratio < 1.0f) {
        int cw = static_cast<int>(frame.cols * roi_ratio);
        int ch = static_cast<int>(frame.rows * roi_ratio);
        offset_x = (frame.cols - cw) / 2;
        offset_y = (frame.rows - ch) / 2;
        input = frame(cv::Range(offset_y, offset_y + ch),
                      cv::Range(offset_x, offset_x + cw));
    }

#ifdef HAS_ONNXRUNTIME
    float scale; int pad_x, pad_y;
    auto data = preprocess(input, scale, pad_x, pad_y);

    std::array<int64_t, 4> shape = {1, 3, input_size_, input_size_};
    auto mem_info = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    auto tensor = Ort::Value::CreateTensor<float>(
        mem_info, data.data(), data.size(), shape.data(), shape.size());

    auto outputs = session_->Run(Ort::RunOptions{nullptr},
        input_names_.data(), &tensor, 1, output_names_.data(), 1);

    auto out_shape = outputs[0].GetTensorTypeAndShapeInfo().GetShape();
    int num_dets = static_cast<int>(out_shape.back());
    const float* out_data = outputs[0].GetTensorData<float>();

    auto dets = postprocess(out_data, num_dets, scale, pad_x, pad_y,
                            input.cols, input.rows);

    // Shift coordinates back for ROI
    if (roi_ratio < 1.0f) {
        for (auto& d : dets) {
            d.bbox.x1 += offset_x;
            d.bbox.y1 += offset_y;
            d.bbox.x2 += offset_x;
            d.bbox.y2 += offset_y;
        }
    }
    return dets;
#else
    (void)roi_ratio; (void)offset_x; (void)offset_y;
    return {};
#endif
}

} // namespace fusion
