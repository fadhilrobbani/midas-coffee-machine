/**
 * @file image_preprocess.h
 * @brief Image preprocessing utilities for detection pipeline.
 *
 * Port of Python core/image_preprocess.py.
 * Functions: CLAHE, unsharp mask, LED detection, lighting normalization.
 */

#pragma once

#include <opencv2/core.hpp>
#include <tuple>
#include <utility>

namespace fusion {

/**
 * @brief Apply CLAHE (Contrast Limited Adaptive Histogram Equalization).
 * Works on both BGR and grayscale images.
 */
cv::Mat apply_clahe(const cv::Mat& frame, double clip_limit = 3.0,
                    cv::Size tile_size = cv::Size(8, 8));

/**
 * @brief Apply unsharp mask for edge enhancement.
 */
cv::Mat apply_unsharp_mask(const cv::Mat& frame, double sigma = 1.0,
                           double strength = 1.5);

/**
 * @brief Detect fisheye circle (center + radius) via Hough transform.
 * @return (cx, cy, radius) or (-1,-1,-1) if not found.
 */
std::tuple<int, int, int> detect_fisheye_circle(const cv::Mat& frame);

/**
 * @brief Crop fisheye to inscribed rectangle.
 */
cv::Mat crop_fisheye_to_rect(const cv::Mat& frame, double margin = 0.05);

/**
 * @brief Detect whether LED illumination is on.
 * Uses mean brightness and standard deviation thresholds.
 */
bool detect_led_state(const cv::Mat& frame, double bright_thresh = 140.0,
                      double std_thresh = 45.0);

/**
 * @brief Normalize lighting using CLAHE + percentile stretch.
 * @return (normalized_frame, led_on)
 */
std::pair<cv::Mat, bool> normalize_lighting(const cv::Mat& frame,
                                            double clip_limit = 3.0,
                                            double low_pct = 1.0,
                                            double high_pct = 99.0);

/**
 * @brief Apply full enhancement pipeline for detection.
 * Combines normalize_lighting + unsharp_mask.
 */
cv::Mat enhance_for_detection(const cv::Mat& frame);

} // namespace fusion
