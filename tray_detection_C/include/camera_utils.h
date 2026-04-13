#pragma once
/**
 * camera_utils.h — Utilitas kamera: init, focus lock
 */

#include <opencv2/videoio.hpp>
#include <memory>

namespace tray {

/**
 * Inisialisasi kamera dengan opsi lock focus.
 * @return cv::VideoCapture yang sudah dikonfigurasi, atau nullptr jika gagal
 */
std::unique_ptr<cv::VideoCapture> init_camera(
    int camera_index = 0,
    bool lock_focus = false,
    int focus_value = 0,
    int width = 640,
    int height = 480);

} // namespace tray
