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

    app.add_option("-c,--camera", config.camera_id, "Camera device ID")
       ->default_val(0);
    app.add_option("-W,--width", config.frame_width, "Frame width")
       ->default_val(2592);
    app.add_option("-H,--height", config.frame_height, "Frame height")
       ->default_val(1944);
    app.add_option("--midas", config.midas_model_path, "MiDaS ONNX model path");
    app.add_option("--yolo", config.yolo_model_path, "YOLO ONNX model path");
    app.add_option("--moil", config.camera_params_path, "Moildev camera params JSON");
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
       ->default_val(1.0);
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
                // Execute v4l2-ctl for hardware exposure via system call (like Python did)
                std::string cmd = "v4l2-ctl -d /dev/video" + std::to_string(config.camera_id) + " -c exposure_absolute=" + std::to_string((int)(val * 1000));
                int ret = system(cmd.c_str());
                (void)ret;
            };

            gui.on_generate_report = [&]() {
                pipeline.reporter().generate_report("live_session");
                gui.set_status("Report generated!");
            };
            
            gui.on_queue_key = [&](int keyval) {
                // If the user wants to trigger screenshot/record/etc, handle it here if implemented in pipeline
                // For now just stub
            };

            // Timer to update GUI from pipeline
            Glib::signal_timeout().connect([&]() -> bool {
                auto frame = pipeline.get_display_frame();
                if (!frame.empty()) gui.update_frame(frame);

                auto m = pipeline.get_metrics();
                gui.update_measurements(m.cup_height_cm, m.aruco_distance_cm,
                                        m.diameter_cm, m.volume_ml);
                return pipeline.is_running();
            }, 33);  // ~30 FPS update

            pipeline.start();
            gtk_app->run(gui);
            pipeline.stop();
            return 0;
        }
#endif
        // Headless / OpenCV display mode
        fusion::LivePipeline pipeline(config);
        pipeline.start();

        while (g_running && pipeline.is_running()) {
            auto frame = pipeline.get_display_frame();
            if (!frame.empty()) {
                cv::Mat display;
                double scale = std::min(1280.0 / frame.cols, 720.0 / frame.rows);
                cv::resize(frame, display, cv::Size(), scale, scale);
                cv::imshow("MiDaS ArUco Fusion - OpenCV Fallback", display);
                
                int key = cv::waitKey(1);
                if (key == 27 || key == 'q') {
                    g_running = false;
                }
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(33));
        }

        pipeline.stop();

        auto m = pipeline.get_metrics();
        std::cout << "\n[Session Summary]\n";
        std::cout << "  Total frames: " << m.frame_count << "\n";
        std::cout << "  Last FPS: " << m.fps << "\n";
        std::cout << "  Entries logged: " << pipeline.reporter().size() << "\n";
    }

    return 0;
}
