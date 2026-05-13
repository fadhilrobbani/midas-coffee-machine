/**
 * @file compare_anypoint_modes.cpp
 * @brief Utility to compare Moildev Anypoint Mode 1 and Mode 2.
 */

#include <iostream>
#include <opencv2/opencv.hpp>
#include <CLI/CLI.hpp>
#include "fisheye/moil_undistorter.h"

int main(int argc, char** argv) {
    CLI::App app{"Moildev Mode Comparison"};

    int camera_id = 0;
    std::string moil_json;
    double pitch = 20, yaw = 20, zoom = 1.5;

    app.add_option("-c,--camera", camera_id, "Camera ID")->default_val(0);
    app.add_option("--moil", moil_json, "Moildev JSON path")->required();
    app.add_option("--pitch", pitch, "Pitch/Alpha angle")->default_val(20);
    app.add_option("--yaw", yaw, "Yaw/Beta angle")->default_val(20);
    app.add_option("--zoom", zoom, "Zoom factor")->default_val(1.5);

    CLI11_PARSE(app, argc, argv);

    fusion::MoilUndistorter u1(moil_json, "", 1); // Mode 1
    fusion::MoilUndistorter u2(moil_json, "", 2); // Mode 2

    u1.update_maps(pitch, yaw, 0, zoom);
    u2.update_maps(pitch, yaw, 0, zoom);

    cv::VideoCapture cap(camera_id, cv::CAP_V4L2);
    if (!cap.isOpened()) return -1;
    cap.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
    cap.set(cv::CAP_PROP_FRAME_WIDTH, 2592);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, 1944);

    std::cout << "Comparing Mode 1 (Left) vs Mode 2 (Right)\n";
    std::cout << "Press 'q' to quit.\n";

    while (true) {
        cv::Mat frame;
        if (!cap.read(frame) || frame.empty()) break;

        cv::Mat out1 = u1.undistort(frame);
        cv::Mat out2 = u2.undistort(frame);

        cv::Mat combined;
        cv::hconcat(out1, out2, combined);
        
        cv::Mat display;
        cv::resize(combined, display, cv::Size(1280, 480));

        cv::putText(display, "Mode 1 (Alpha/Beta)", cv::Point(50, 50), cv::FONT_HERSHEY_SIMPLEX, 1.0, cv::Scalar(0, 255, 0), 2);
        cv::putText(display, "Mode 2 (Pitch/Yaw)", cv::Point(690, 50), cv::FONT_HERSHEY_SIMPLEX, 1.0, cv::Scalar(0, 255, 0), 2);

        cv::imshow("Comparison", display);
        if ((char)cv::waitKey(1) == 'q') break;
    }

    return 0;
}
