/**
 * @file moil_undistorter.cpp
 * @brief Fisheye undistortion implementation.
 * Port of Python core/moil_undistorter.py.
 */

#include "moil_undistorter.h"
#include <opencv2/imgproc.hpp>
#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>
#include <cmath>
#include <algorithm>

namespace fusion {

MoilUndistorter::MoilUndistorter(const std::string& camera_params_json,
                                 int mode)
    : mode_(mode)
{
    load_params(camera_params_json);
    if (focal_length_ > 0) {
        generate_maps(0, 0, 0, 1.0);
        maps_ready_ = true;
    }
}

void MoilUndistorter::load_params(const std::string& json_path) {
    try {
        std::ifstream f(json_path);
        if (!f.is_open()) {
            std::cerr << "[Moildev] Cannot open: " << json_path << "\n";
            return;
        }
        nlohmann::json j;
        f >> j;
        focal_length_ = j.value("focalLength", j.value("focal_length", 0.0));
        image_width_ = j.value("imageWidth", j.value("image_width", 0));
        image_height_ = j.value("imageHeight", j.value("image_height", 0));
        adjusted_focal_ = focal_length_;
        std::cout << "[Moildev] Loaded: f=" << focal_length_
                  << " size=" << image_width_ << "x" << image_height_ << "\n";
    } catch (const std::exception& e) {
        std::cerr << "[Moildev] Error loading params: " << e.what() << "\n";
    }
}

void MoilUndistorter::generate_maps(double pitch, double yaw, double roll,
                                     double moil_zoom) {
    // Simplified anypoint Mode 1 map generation
    // In production, this calls the MoilCV C library
    int h = image_height_, w = image_width_;
    if (h <= 0 || w <= 0) return;

    map_x_.create(h, w, CV_32FC1);
    map_y_.create(h, w, CV_32FC1);

    double cx = w / 2.0, cy = h / 2.0;
    double f = focal_length_ * moil_zoom;
    adjusted_focal_ = f;

    // Rotation angles in radians
    double alpha = pitch * CV_PI / 180.0;
    double beta = yaw * CV_PI / 180.0;

    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            // Normalized coordinates
            double nx = (x - cx) / f;
            double ny = (y - cy) / f;

            // Apply rotation (simplified equidistant projection)
            double theta = std::sqrt(nx * nx + ny * ny);
            double phi = std::atan2(ny, nx);

            // Adjust for pitch/yaw
            theta = std::max(0.0, theta - alpha * std::cos(phi) - beta * std::sin(phi));

            // Map back to source coordinates
            double src_x = cx + f * theta * std::cos(phi + roll * CV_PI / 180.0);
            double src_y = cy + f * theta * std::sin(phi + roll * CV_PI / 180.0);

            map_x_.at<float>(y, x) = static_cast<float>(src_x);
            map_y_.at<float>(y, x) = static_cast<float>(src_y);
        }
    }
}

std::pair<double, double> MoilUndistorter::split_zoom(double total_zoom) {
    if (total_zoom <= MAX_MOIL_ZOOM) {
        return {total_zoom, 1.0};
    }
    return {MAX_MOIL_ZOOM, total_zoom / MAX_MOIL_ZOOM};
}

void MoilUndistorter::rescale_maps(const cv::Size& stream_size) {
    if (map_x_.empty()) return;

    double sx = static_cast<double>(stream_size.width) / map_x_.cols;
    double sy = static_cast<double>(stream_size.height) / map_x_.rows;

    cv::resize(map_x_, scaled_map_x_, stream_size, 0, 0, cv::INTER_LINEAR);
    cv::resize(map_y_, scaled_map_y_, stream_size, 0, 0, cv::INTER_LINEAR);

    // Scale the coordinate values
    scaled_map_x_ *= static_cast<float>(sx);
    scaled_map_y_ *= static_cast<float>(sy);
    stream_size_ = stream_size;
}

cv::Mat MoilUndistorter::digital_crop(const cv::Mat& frame,
                                       double digital_zoom) const {
    if (digital_zoom <= 1.0) return frame;

    int cw = static_cast<int>(frame.cols / digital_zoom);
    int ch = static_cast<int>(frame.rows / digital_zoom);
    int cx = (frame.cols - cw) / 2;
    int cy = (frame.rows - ch) / 2;

    cv::Mat cropped = frame(cv::Range(cy, cy + ch), cv::Range(cx, cx + cw));
    cv::Mat result;
    cv::resize(cropped, result, frame.size(), 0, 0, cv::INTER_LINEAR);
    return result;
}

cv::Mat MoilUndistorter::undistort(const cv::Mat& frame) {
    if (frame.empty() || !maps_ready_) return frame.clone();

    std::lock_guard<std::mutex> lock(map_mutex_);

    // Rescale maps if frame size changed
    cv::Size frame_size(frame.cols, frame.rows);
    if (stream_size_ != frame_size) {
        rescale_maps(frame_size);
    }

    auto [moil_z, digi_z] = split_zoom(zoom_);

    // Remap
    cv::Mat remapped;
    cv::remap(frame, remapped, scaled_map_x_, scaled_map_y_,
              cv::INTER_LINEAR, cv::BORDER_CONSTANT);

    // Digital crop if needed
    if (digi_z > 1.0) {
        remapped = digital_crop(remapped, digi_z);
    }

    return remapped;
}

void MoilUndistorter::update_maps(double pitch, double yaw,
                                   double roll, double zoom) {
    std::lock_guard<std::mutex> lock(map_mutex_);
    pitch_ = pitch;
    yaw_ = yaw;
    roll_ = roll;
    zoom_ = zoom;

    auto [moil_z, digi_z] = split_zoom(zoom);
    generate_maps(pitch, yaw, roll, moil_z);
    stream_size_ = cv::Size(0, 0);  // Force rescale on next undistort
}

cv::Matx33d MoilUndistorter::build_aruco_camera_matrix(int w, int h) const {
    double fx = adjusted_focal_;
    double fy = fx;
    double cx = w / 2.0;
    double cy = h / 2.0;
    return cv::Matx33d(fx, 0, cx, 0, fy, cy, 0, 0, 1);
}

} // namespace fusion
