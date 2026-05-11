/**
 * @file image_preprocess.cpp
 * @brief Implementation of image preprocessing utilities.
 *
 * Direct port of Python core/image_preprocess.py.
 */

#include "image_preprocess.h"
#include <opencv2/imgproc.hpp>
#include <algorithm>
#include <cmath>
#include <vector>

namespace fusion {

cv::Mat apply_clahe(const cv::Mat& frame, double clip_limit, cv::Size tile_size) {
    if (frame.empty()) return frame.clone();

    auto clahe = cv::createCLAHE(clip_limit, tile_size);

    if (frame.channels() == 1) {
        cv::Mat out;
        clahe->apply(frame, out);
        return out;
    }

    // Convert BGR → LAB, apply CLAHE on L channel
    cv::Mat lab;
    cv::cvtColor(frame, lab, cv::COLOR_BGR2Lab);

    std::vector<cv::Mat> channels;
    cv::split(lab, channels);
    clahe->apply(channels[0], channels[0]);
    cv::merge(channels, lab);

    cv::Mat out;
    cv::cvtColor(lab, out, cv::COLOR_Lab2BGR);
    return out;
}

cv::Mat apply_unsharp_mask(const cv::Mat& frame, double sigma, double strength) {
    if (frame.empty()) return frame.clone();

    cv::Mat blurred;
    int ksize = static_cast<int>(std::ceil(sigma * 6)) | 1;  // ensure odd
    cv::GaussianBlur(frame, blurred, cv::Size(ksize, ksize), sigma);

    cv::Mat sharpened;
    cv::addWeighted(frame, 1.0 + strength, blurred, -strength, 0, sharpened);
    return sharpened;
}

std::tuple<int, int, int> detect_fisheye_circle(const cv::Mat& frame) {
    if (frame.empty()) return {-1, -1, -1};

    cv::Mat gray;
    if (frame.channels() == 3) {
        cv::cvtColor(frame, gray, cv::COLOR_BGR2GRAY);
    } else {
        gray = frame;
    }

    cv::Mat blurred;
    cv::GaussianBlur(gray, blurred, cv::Size(9, 9), 2);

    std::vector<cv::Vec3f> circles;
    cv::HoughCircles(blurred, circles, cv::HOUGH_GRADIENT, 1,
                     gray.rows / 2.0,  // min distance
                     100, 30,           // param1, param2
                     gray.rows / 4,     // min radius
                     gray.rows / 2);    // max radius

    if (circles.empty()) return {-1, -1, -1};

    // Return the largest circle
    auto best = *std::max_element(circles.begin(), circles.end(),
        [](const cv::Vec3f& a, const cv::Vec3f& b) { return a[2] < b[2]; });

    return {static_cast<int>(best[0]), static_cast<int>(best[1]),
            static_cast<int>(best[2])};
}

cv::Mat crop_fisheye_to_rect(const cv::Mat& frame, double margin) {
    auto [cx, cy, r] = detect_fisheye_circle(frame);
    if (r <= 0) return frame.clone();

    int half_side = static_cast<int>(r * (1.0 - margin) / std::sqrt(2.0));
    int x1 = std::max(0, cx - half_side);
    int y1 = std::max(0, cy - half_side);
    int x2 = std::min(frame.cols, cx + half_side);
    int y2 = std::min(frame.rows, cy + half_side);

    return frame(cv::Range(y1, y2), cv::Range(x1, x2)).clone();
}

bool detect_led_state(const cv::Mat& frame, double bright_thresh, double std_thresh) {
    if (frame.empty()) return false;

    cv::Mat gray;
    if (frame.channels() == 3) {
        cv::cvtColor(frame, gray, cv::COLOR_BGR2GRAY);
    } else {
        gray = frame;
    }

    cv::Scalar mean_val, stddev_val;
    cv::meanStdDev(gray, mean_val, stddev_val);

    double brightness = mean_val[0];
    double stddev = stddev_val[0];

    // LED is considered "on" when frame is bright enough
    return (brightness >= bright_thresh) || (stddev >= std_thresh && brightness > 80.0);
}

std::pair<cv::Mat, bool> normalize_lighting(const cv::Mat& frame,
                                            double clip_limit,
                                            double low_pct,
                                            double high_pct) {
    if (frame.empty()) return {frame.clone(), false};

    bool led_on = detect_led_state(frame);

    // Step 1: CLAHE
    cv::Mat enhanced = apply_clahe(frame, clip_limit);

    // Step 2: Percentile stretch
    cv::Mat gray;
    if (enhanced.channels() == 3) {
        cv::cvtColor(enhanced, gray, cv::COLOR_BGR2GRAY);
    } else {
        gray = enhanced;
    }

    // Calculate percentiles using histogram
    int hist_size = 256;
    float range[] = {0, 256};
    const float* hist_range = {range};
    cv::Mat hist;
    cv::calcHist(&gray, 1, nullptr, cv::Mat(), hist, 1, &hist_size, &hist_range);

    int total_pixels = gray.rows * gray.cols;
    double low_count = total_pixels * low_pct / 100.0;
    double high_count = total_pixels * high_pct / 100.0;

    int low_val = 0, high_val = 255;
    double cumsum = 0;
    for (int i = 0; i < 256; ++i) {
        cumsum += hist.at<float>(i);
        if (cumsum >= low_count) { low_val = i; break; }
    }
    cumsum = 0;
    for (int i = 0; i < 256; ++i) {
        cumsum += hist.at<float>(i);
        if (cumsum >= high_count) { high_val = i; break; }
    }

    if (high_val <= low_val) high_val = low_val + 1;

    // Apply LUT for fast stretch
    cv::Mat lut(1, 256, CV_8UC1);
    for (int i = 0; i < 256; ++i) {
        double val = 255.0 * (i - low_val) / (high_val - low_val);
        lut.at<uchar>(i) = cv::saturate_cast<uchar>(val);
    }

    cv::Mat result;
    cv::LUT(enhanced, lut, result);

    return {result, led_on};
}

cv::Mat enhance_for_detection(const cv::Mat& frame) {
    auto [normalized, led_on] = normalize_lighting(frame);
    return apply_unsharp_mask(normalized, 1.0, 1.5);
}

} // namespace fusion
