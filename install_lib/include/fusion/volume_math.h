/**
 * @file volume_math.h
 * @brief Cup volume estimation from camera data.
 *
 * Port of Python core/volume_math.py.
 *
 * Pipeline:
 *   1. measure_rim_width_px(frame, bbox) → rim width in pixels
 *   2. calc_diameter(rim_w_px, z_rim, focal_px) → physical diameter (cm)
 *   3. calc_volume(h_cup, diameter) → volume (mL ≈ cm³)
 */

#pragma once

#include <opencv2/core.hpp>
#include "height_math.h"  // for BBox

namespace fusion {

/**
 * @brief Measure cup rim width in pixels using Otsu thresholding.
 *
 * Samples a thin horizontal strip at the top of the bounding box (the rim)
 * and uses Otsu threshold to find left/right edges of the cup.
 *
 * @param frame BGR image (post-undistortion)
 * @param bbox  YOLO bounding box
 * @return Rim width in pixels (always > 0, fallback to bbox center width)
 */
double measure_rim_width_px(const cv::Mat& frame, const BBox& bbox);

/**
 * @brief Calculate physical diameter (cm) via pinhole camera model.
 *
 * Formula: diameter = (rim_w_px × z_rim) / focal_px
 *
 * @param rim_w_px  Rim width in pixels
 * @param z_rim_cm  Distance from camera to cup rim (cm)
 * @param focal_px  Effective focal length in pixels
 * @return Diameter in cm (0.0 if invalid input)
 */
double calc_diameter(double rim_w_px, double z_rim_cm, double focal_px);

/**
 * @brief Calculate cup volume (mL) using cylinder model.
 *
 * Formula: V = π × (d/2)² × h   (1 cm³ = 1 mL)
 *
 * @param h_cup_cm     Cup height in cm
 * @param diameter_cm  Cup diameter in cm
 * @return Volume in mL (0.0 if invalid input)
 */
double calc_volume(double h_cup_cm, double diameter_cm);

} // namespace fusion
