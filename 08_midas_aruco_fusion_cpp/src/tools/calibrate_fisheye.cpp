/**
 * @file calibrate_fisheye.cpp
 * @brief Standalone utility for fisheye camera calibration.
 */

#include <iostream>
#include <vector>
#include <opencv2/opencv.hpp>
#include <CLI/CLI.hpp>

int main(int argc, char** argv) {
    CLI::App app{"Fisheye Camera Calibrator"};

    int camera_id = 0;
    int board_w = 9, board_h = 6;
    double square_size = 1.0;
    int num_frames = 20;

    app.add_option("-c,--camera", camera_id, "Camera ID")->default_val(0);
    app.add_option("-w,--width", board_w, "Chessboard width (inner corners)")->default_val(9);
    app.add_option("-h,--height", board_h, "Chessboard height (inner corners)")->default_val(6);
    app.add_option("-s,--size", square_size, "Square size (cm/mm)")->default_val(1.0);
    app.add_option("-n,--num", num_frames, "Number of frames to capture")->default_val(20);

    CLI11_PARSE(app, argc, argv);

    cv::VideoCapture cap(camera_id, cv::CAP_V4L2);
    if (!cap.isOpened()) {
        std::cerr << "Error: Could not open camera\n";
        return -1;
    }

    cap.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
    cap.set(cv::CAP_PROP_FRAME_WIDTH, 2592);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, 1944);

    cv::Size pattern_size(board_w, board_h);
    std::vector<std::vector<cv::Point3f>> object_points;
    std::vector<std::vector<cv::Point2f>> image_points;

    std::vector<cv::Point3f> obj;
    for (int i = 0; i < board_h; i++) {
        for (int j = 0; j < board_w; j++) {
            obj.push_back(cv::Point3f(j * square_size, i * square_size, 0));
        }
    }

    std::cout << "Press 's' to save a frame, 'q' to quit.\n";
    std::cout << "Need " << num_frames << " successful captures.\n";

    while (object_points.size() < (size_t)num_frames) {
        cv::Mat frame;
        if (!cap.read(frame) || frame.empty()) break;

        cv::Mat gray, display;
        cv::resize(frame, display, cv::Size(1280, 720));
        cv::cvtColor(frame, gray, cv::COLOR_BGR2GRAY);

        std::vector<cv::Point2f> corners;
        bool found = cv::findChessboardCorners(gray, pattern_size, corners);

        if (found) {
            cv::Mat display_corners = display.clone();
            std::vector<cv::Point2f> corners_disp;
            for(auto p : corners) corners_disp.push_back(cv::Point2f(p.x * 1280.0/2592.0, p.y * 720.0/1944.0));
            cv::drawChessboardCorners(display_corners, pattern_size, corners_disp, found);
            cv::imshow("Calibration", display_corners);
        } else {
            cv::imshow("Calibration", display);
        }

        char key = (char)cv::waitKey(1);
        if (key == 'q') break;
        if (key == 's' && found) {
            cv::cornerSubPix(gray, corners, cv::Size(11, 11), cv::Size(-1, -1),
                             cv::TermCriteria(cv::TermCriteria::EPS + cv::TermCriteria::COUNT, 30, 0.1));
            image_points.push_back(corners);
            object_points.push_back(obj);
            std::cout << "Captured " << image_points.size() << "/" << num_frames << "\n";
        }
    }

    if (image_points.size() >= (size_t)num_frames) {
        std::cout << "Calibrating...\n";
        cv::Mat K, D;
        std::vector<cv::Mat> rvecs, tvecs;
        int flags = cv::fisheye::CALIB_RECOMPUTE_EXTRINSIC | cv::fisheye::CALIB_FIX_SKEW;
        
        cv::fisheye::calibrate(object_points, image_points, cv::Size(2592, 1944), K, D, rvecs, tvecs, flags);

        std::cout << "Calibration Complete!\n";
        std::cout << "Camera Matrix K:\n" << K << "\n";
        std::cout << "Distortion Coefficients D:\n" << D << "\n";

        cv::FileStorage fs("fisheye_calibration.yaml", cv::FileStorage::WRITE);
        fs << "K" << K;
        fs << "D" << D;
        fs.release();
        std::cout << "Saved to fisheye_calibration.yaml\n";
    }

    cap.release();
    cv::destroyAllWindows();
    return 0;
}
