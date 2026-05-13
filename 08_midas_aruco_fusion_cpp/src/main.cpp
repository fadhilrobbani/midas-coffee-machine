/**
 * @file main.cpp
 * @brief Entry point for MiDaS ArUco Fusion C++ application.
 *
 * Usage:
 *   ./fusion_app --camera 0 --midas weights/midas_v21_small_256.onnx
 *                --yolo weights/cup_detection_v3_12_s_best.onnx
 *                --calib calibration.json --moil camera_params.json
 */

#include <iostream>
#include <string>
#include <csignal>
#include <atomic>
#include <thread>

#include <opencv2/imgproc.hpp>
#include <opencv2/highgui.hpp>
#include <CLI/CLI.hpp>
#include "live_pipeline.h"

#ifdef HAS_GTKMM
#include "gui_fusion.h"
#endif

static std::atomic<bool> g_running{true};

static void signal_handler(int sig) {
    (void)sig;
    g_running = false;
}

int main(int argc, char* argv[]) {
    CLI::App app{"MiDaS ArUco Fusion — C++ Real-Time Cup Estimator"};

    fusion::PipelineConfig config;
    std::string mode = "live";
    bool headless = false;

    // Hardcode defaults to match 07_midas_aruco_fusion
    config.midas_model_path = "../../weights/midas_v21_small_256.onnx";
    config.yolo_model_path = "../../weights/cup_detection_v3_12_s_best.onnx";
    config.camera_params_path = "../../weights/moil/camera_parameters.json";
    config.camera_name = "syue_7730v1_6";
    config.enable_moildev = true;

    app.add_option("-c,--camera", config.camera_id, "Camera device ID")
       ->default_val(0);
    app.add_option("-W,--width", config.frame_width, "Frame width")
       ->default_val(2592);
    app.add_option("-H,--height", config.frame_height, "Frame height")
       ->default_val(1944);
    app.add_option("--midas", config.midas_model_path, "MiDaS ONNX model path");
    app.add_option("--yolo", config.yolo_model_path, "YOLO ONNX model path");
    app.add_option("--moil", config.camera_params_path, "Moildev camera params JSON");
    app.add_option("--moil-name", config.camera_name, "Camera profile name inside Moildev JSON");
    app.add_option("--calib", config.calibration_path, "Calibration JSON path")
       ->default_val("calibration.json");
    app.add_option("--marker-size", config.marker_size_cm, "ArUco marker size (cm)")
       ->default_val(5.0);
    app.add_option("-m,--mode", mode, "Run mode: live, calibrate")
       ->default_val("live");
    app.add_flag("--headless", headless, "Run without GUI (OpenCV display)");
    app.add_flag("--fisheye", [&](int64_t) { config.enable_moildev = true; },
                 "Enable Moildev (Fisheye) undistortion");
    app.add_option("--moil-zoom", config.moil_zoom, "Initial Moildev Zoom")
       ->default_val(1.4);
    app.add_option("--moil-mode", config.moil_mode, "Moildev Mode (1 or 2)")
       ->default_val(2);
    app.add_option("--target-cup", config.target_cup_cm, "Target cup height in cm")
       ->default_val(7.6);
    app.add_option("--manual-exposure", config.manual_exposure, "V4L2 manual exposure value (0 = auto)")
       ->default_val(0);
    app.add_flag("--no-moil", [&](int64_t) { config.enable_moildev = false; },
                 "Disable Moildev undistortion");
    app.add_flag("--no-depth", [&](int64_t) { config.enable_depth = false; },
                 "Disable MiDaS depth estimation");

    CLI11_PARSE(app, argc, argv);

    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    std::cout << "╔══════════════════════════════════════════════╗\n";
    std::cout << "║  MiDaS ArUco Fusion C++                     ║\n";
    std::cout << "╠══════════════════════════════════════════════╣\n";
    std::cout << "║  Camera    : " << config.camera_id << "                              ║\n";
    std::cout << "║  Resolution: " << config.frame_width << "x" << config.frame_height << "                    ║\n";
    std::cout << "║  Mode      : " << mode << "                            ║\n";
    std::cout << "╚══════════════════════════════════════════════╝\n\n";

    if (mode == "live") {
#ifdef HAS_GTKMM
        if (!headless) {
            auto gtk_app = Gtk::Application::create("org.aranus.fusion");
            fusion::FusionGUI gui;
            fusion::LivePipeline pipeline(config);

            // Connect GUI callbacks
            gui.on_toggle_depth = [&](bool en) { pipeline.set_show_depth(en); };
            gui.on_toggle_normalize = [&](bool en) { pipeline.set_normalize_lighting(en); };
            gui.on_toggle_bw = [&](bool en) { pipeline.set_bw_mode(en); };
            
            gui.on_apply_anypoint = [&](double a, double b, double z) {
                if (pipeline.moil()) pipeline.moil()->update_maps(a, b, 0, z);
            };
            gui.on_reset_anypoint = [&]() {
                if (pipeline.moil()) pipeline.moil()->update_maps(0, 0, 0, 1.4);
            };
            
            gui.on_smart_exposure = [&](double val) {
                // Map smart exposure (1.0 - 10.0) to raw values just like Python
                double raw_exp = val * 1000.0;
                double raw_gain = (val - 1.0) / 9.0 * 255.0;
                double raw_bri = (val - 1.0) / 9.0 * 128.0 - 64.0;
                pipeline.set_smart_exposure(raw_exp, raw_gain, raw_bri);
            };

            gui.on_generate_report = [&]() {
                pipeline.reporter().generate_report("live_session");
                gui.set_status("Report generated!");
            };
            gui.on_snapshot = [&]() {
                pipeline.save_screenshot("screenshots");
                gui.set_status("Screenshot saved!");
            };
            gui.on_start_calib = [&]() {
                pipeline.toggle_recording();
            };
            gui.on_queue_key = [&](int) {};

            // Initialize AI models and ONNX Runtime safely before GTK starts its event loop
            pipeline.init_models();

            // Timer to update GUI from pipeline (~30 FPS)
            bool pipeline_started = false;
            Glib::signal_timeout().connect([&]() -> bool {
                if (!pipeline_started) {
                    pipeline.start(); // Start background threads safely after GTK is ready
                    pipeline_started = true;
                }
                auto frame = pipeline.get_display_frame();
                if (!frame.empty()) gui.update_frame(frame);
                auto m = pipeline.get_metrics();
                gui.update_measurements(
                    m.cup_height_cm[0], m.aruco_distance_cm,
                    m.diameter_cm[0],   m.volume_ml[0]);
                std::string st = std::string("ArUco:") + (m.aruco_found ? "OK" : "X")
                               + " | YOLO:" + (m.cup_found[0] ? "OK" : "X")
                               + " | LED:" + (m.led_on ? "ON" : "OFF");
                gui.set_status(st);
                return pipeline.is_running();
            }, 33);

            gtk_app->run(gui);
            pipeline.stop();
            return 0;
        }
#endif
        // Headless / OpenCV display mode
        fusion::LivePipeline pipeline(config);
        pipeline.init_models();
        pipeline.start();

        while (g_running && pipeline.is_running()) {
            auto frame = pipeline.get_display_frame();
            if (!frame.empty()) {
                cv::Mat display;
                double scale = std::min(1280.0 / frame.cols, 720.0 / frame.rows);
                cv::resize(frame, display, cv::Size(), scale, scale);
                cv::imshow("MiDaS ArUco Fusion - OpenCV Fallback", display);
                
                int key = cv::waitKey(1);
                if (key == 27 || key == 'q') g_running = false;
                else if (key == 'r') pipeline.toggle_recording();
                else if (key == 's') pipeline.save_screenshot("screenshots");
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(33));
        }

        pipeline.stop();

        auto m = pipeline.get_metrics();
        std::cout << "\n[Session Summary]\n";
        std::cout << "  Total frames : " << m.frame_count << "\n";
        std::cout << "  Last FPS     : " << m.fps << "\n";
        std::cout << "  Cup 1 height : " << m.cup_height_cm[0] << " cm\n";
        std::cout << "  Cup 2 height : " << m.cup_height_cm[1] << " cm\n";
    }

    return 0;
}
