/**
 * camera_utils.cpp — Utilitas kamera: init, focus lock
 */

#include "camera_utils.h"
#include <iostream>

namespace tray {

std::unique_ptr<cv::VideoCapture> init_camera(
    int camera_index, bool lock_focus, int focus_value,
    int width, int height) {

    auto cap = std::make_unique<cv::VideoCapture>(camera_index);

    if (!cap->isOpened()) {
        std::cerr << "[CAMERA] Error: Cannot open camera index "
                  << camera_index << std::endl;
        return nullptr;
    }

    // Set resolution
    cap->set(cv::CAP_PROP_FRAME_WIDTH, width);
    cap->set(cv::CAP_PROP_FRAME_HEIGHT, height);

    int actual_w = static_cast<int>(cap->get(cv::CAP_PROP_FRAME_WIDTH));
    int actual_h = static_cast<int>(cap->get(cv::CAP_PROP_FRAME_HEIGHT));
    std::cout << "[CAMERA] Resolution: " << actual_w << "x" << actual_h
              << std::endl;

    // Lock focus
    if (lock_focus) {
        bool af_ok = cap->set(cv::CAP_PROP_AUTOFOCUS, 0);
        if (af_ok) {
            cap->set(cv::CAP_PROP_FOCUS, focus_value);
            double actual = cap->get(cv::CAP_PROP_FOCUS);
            std::cout << "[CAMERA] Focus LOCKED: auto-focus OFF, focus="
                      << actual << std::endl;
        } else {
            std::cerr << "[CAMERA] Camera does not support focus control "
                      << "via OpenCV." << std::endl;
            std::cerr << "[CAMERA] Try: v4l2-ctl -d /dev/video"
                      << camera_index
                      << " -c focus_automatic_continuous=0" << std::endl;
            std::cerr << "[CAMERA]      v4l2-ctl -d /dev/video"
                      << camera_index
                      << " -c focus_absolute=" << focus_value << std::endl;
        }
    }

    return cap;
}

} // namespace tray
