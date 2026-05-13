/**
 * @file record_moildev.cpp
 * @brief Standalone utility to record Moildev undistorted video.
 */

#include <iostream>
#include <opencv2/opencv.hpp>
#include <CLI/CLI.hpp>
#include "fisheye/moil_undistorter.h"

int main(int argc, char** argv) {
    CLI::App app{"Moildev Video Recorder"};

    int camera_id = 0;
    std::string moil_json;
    double pitch = 0, yaw = 0, roll = 0, zoom = 1.0;
    std::string output_file = "recorded_videos/output.avi";
    int width = 2592, height = 1944;
    int fps = 20;

    app.add_option("-c,--camera", camera_id, "Camera ID")->default_val(0);
    app.add_option("--moil", moil_json, "Moildev JSON path")->required();
    app.add_option("--pitch", pitch, "Pitch angle")->default_val(0);
    app.add_option("--yaw", yaw, "Yaw angle")->default_val(0);
    app.add_option("--zoom", zoom, "Zoom factor")->default_val(1.0);
    app.add_option("-o,--output", output_file, "Output video path")->default_val("recorded_videos/output.avi");
    app.add_option("-W,--width", width, "Capture width")->default_val(2592);
    app.add_option("-H,--height", height, "Capture height")->default_val(1944);
    app.add_option("--fps", fps, "Recording FPS")->default_val(20);

    CLI11_PARSE(app, argc, argv);

    // Ensure output directory exists (simple system call for now)
    system("mkdir -p recorded_videos");

    fusion::MoilUndistorter undistorter(moil_json, "", 2); // Mode 2 by default
    undistorter.update_maps(pitch, yaw, roll, zoom);

    cv::VideoCapture cap(camera_id, cv::CAP_V4L2);
    if (!cap.isOpened()) {
        std::cerr << "Error: Could not open camera\n";
        return -1;
    }

    cap.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
    cap.set(cv::CAP_PROP_FRAME_WIDTH, width);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, height);

    cv::VideoWriter writer;
    bool is_writing = false;

    std::cout << "Recording to " << output_file << "\n";
    std::cout << "Press 'r' to start/stop recording, 'q' to quit.\n";

    while (true) {
        cv::Mat frame;
        if (!cap.read(frame) || frame.empty()) break;

        cv::Mat undistorted = undistorter.undistort(frame);
        
        cv::Mat display;
        cv::resize(undistorted, display, cv::Size(1280, 720));

        if (is_writing) {
            if (!writer.isOpened()) {
                writer.open(output_file, cv::VideoWriter::fourcc('X', 'V', 'I', 'D'), fps, undistorted.size());
            }
            writer.write(undistorted);
            cv::circle(display, cv::Point(30, 30), 10, cv::Scalar(0, 0, 255), -1);
            cv::putText(display, "REC", cv::Point(50, 40), cv::FONT_HERSHEY_SIMPLEX, 1.0, cv::Scalar(0, 0, 255), 2);
        }

        cv::imshow("Moildev Recorder", display);
        char key = (char)cv::waitKey(1);
        if (key == 'q') break;
        if (key == 'r') {
            is_writing = !is_writing;
            if (!is_writing && writer.isOpened()) {
                writer.release();
                std::cout << "Recording stopped and saved.\n";
            } else if (is_writing) {
                std::cout << "Recording started...\n";
            }
        }
    }

    cap.release();
    if (writer.isOpened()) writer.release();
    cv::destroyAllWindows();

    return 0;
}
