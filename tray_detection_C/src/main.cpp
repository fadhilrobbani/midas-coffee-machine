/**
 * main.cpp — CLI Entry Point for Tray Detector (C++)
 *
 * 3 mode operasi:
 *   --image PATH        → proses satu gambar
 *   --input_dir PATH    → batch seluruh folder gambar
 *   --camera [INDEX]    → live webcam dengan overlay real-time
 *
 * Contoh:
 *   ./tray_detector --image test.jpg
 *   ./tray_detector --camera 0 --method B --lock-focus
 *   ./tray_detector --image test.jpg --no-yolo
 */

#include <iostream>
#include <fstream>
#include <string>
#include <vector>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <filesystem>

#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/highgui.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/videoio.hpp>

#include "config.h"
#include "pipeline.h"
#include "camera_utils.h"

namespace fs = std::filesystem;

// ── Helper: Print result as JSON ────────────────────────────────────────
static void print_result(const tray::FusedResult& r, const std::string& src) {
    std::string prefix = src.empty() ? "" : "[" + src + "] ";
    std::printf("\n%s==================================================\n", prefix.c_str());
    std::printf("{\n");
    std::printf("  \"D_tray_cm\": %.1f,\n", r.D_tray_cm);
    std::printf("  \"method_used\": \"%s\",\n", r.method_used.c_str());
    std::printf("  \"confidence\": %.3f,\n", r.confidence);
    std::printf("  \"status\": \"%s\",\n", r.status.c_str());
    std::printf("  \"D_left_cm\": %.1f,\n", r.D_left_cm);
    std::printf("  \"D_right_cm\": %.1f,\n", r.D_right_cm);
    std::printf("  \"lines_left\": %d,\n", r.lines_left);
    std::printf("  \"lines_right\": %d,\n", r.lines_right);
    std::printf("  \"notes\": \"%s\"\n", r.notes.c_str());
    std::printf("}\n");
    std::printf("==================================================\n\n");
}


// ── Helper: Get timestamp string ────────────────────────────────────────
static std::string get_timestamp() {
    auto now = std::chrono::system_clock::now();
    auto t = std::chrono::system_clock::to_time_t(now);
    std::tm tm = *std::localtime(&t);
    char buf[64];
    std::strftime(buf, sizeof(buf), "%Y-%m-%d_%H%M%S", &tm);
    return std::string(buf);
}


// ── Mode: Single Image ─────────────────────────────────────────────────
static void process_single_image(tray::TrayDistancePipeline& pipeline,
                                  const std::string& image_path,
                                  const std::string& output_dir) {
    cv::Mat img = cv::imread(image_path);
    if (img.empty()) {
        std::cerr << "Error: Cannot read image: " << image_path << std::endl;
        return;
    }

    std::cout << "Processing: " << image_path << std::endl;
    auto result = pipeline.process_frame(img);
    print_result(result, fs::path(image_path).filename().string());

    cv::Mat annotated = pipeline.annotate_frame(img, result);
    std::string basename = fs::path(image_path).stem().string();
    std::string out_path = output_dir + "/dtray_" + basename + ".jpg";
    cv::imwrite(out_path, annotated);
    std::cout << "Visualization saved: " << out_path << std::endl;
}


// ── Mode: Batch Directory ───────────────────────────────────────────────
static void process_directory(tray::TrayDistancePipeline& pipeline,
                               const std::string& input_dir,
                               const std::string& output_dir) {
    std::vector<std::string> exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"};
    std::vector<std::string> images;

    for (const auto& entry : fs::directory_iterator(input_dir)) {
        if (!entry.is_regular_file()) continue;
        std::string ext = entry.path().extension().string();
        std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);
        for (const auto& e : exts) {
            if (ext == e) {
                images.push_back(entry.path().string());
                break;
            }
        }
    }

    std::sort(images.begin(), images.end());

    if (images.empty()) {
        std::cout << "No images found in: " << input_dir << std::endl;
        return;
    }

    std::cout << "Processing " << images.size() << " images from: "
              << input_dir << std::endl;
    for (const auto& path : images)
        process_single_image(pipeline, path, output_dir);
}


// ── Mode: Live Camera ───────────────────────────────────────────────────
static void run_live_camera(tray::TrayDistancePipeline& pipeline,
                             int camera_index, bool lock_focus,
                             int focus_value) {
    const std::string SCREENSHOT_DIR = "tray_detector/results/live_cam";
    fs::create_directories(SCREENSHOT_DIR);

    auto cap = tray::init_camera(camera_index, lock_focus, focus_value);
    if (!cap) return;

    std::cout << "Live camera started (index=" << camera_index << ")" << std::endl;
    std::cout << "Press 'q' to exit | 's' screenshot | 'r' record | 'p' pause" << std::endl;
    if (lock_focus)
        std::cout << "Focus locked at value=" << focus_value << std::endl;

    cv::VideoWriter video_writer;
    bool is_recording = false;
    bool is_paused = false;

    int fps_counter = 0;
    auto fps_time = std::chrono::steady_clock::now();
    double fps_display = 0.0;

    // Statistics
    int stats_total = 0, stats_valid = 0;
    double stats_sum = 0, stats_min = 1e9, stats_max = -1e9;
    int stats_spikes = 0;

    while (true) {
        cv::Mat frame;
        if (!cap->read(frame) || frame.empty()) {
            std::cerr << "Error: Failed to read frame" << std::endl;
            break;
        }

        if (frame.cols > 640)
            cv::resize(frame, frame, cv::Size(640, 480));

        auto t_start = std::chrono::steady_clock::now();
        auto result = pipeline.process_frame(frame);
        auto t_end = std::chrono::steady_clock::now();
        double t_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();

        // ── Update statistics ───────────────────────────────────────────
        stats_total++;
        if (result.D_tray_cm > 0) {
            stats_valid++;
            stats_sum += result.D_tray_cm;
            stats_min = std::min(stats_min, result.D_tray_cm);
            stats_max = std::max(stats_max, result.D_tray_cm);
        }
        if (result.notes.find("Spike detected") != std::string::npos)
            stats_spikes++;

        // ── Annotate ────────────────────────────────────────────────────
        cv::Mat annotated = pipeline.annotate_frame(frame, result);

        // FPS
        fps_counter++;
        auto now = std::chrono::steady_clock::now();
        double elapsed = std::chrono::duration<double>(now - fps_time).count();
        if (elapsed >= 1.0) {
            fps_display = fps_counter / elapsed;
            fps_counter = 0;
            fps_time = now;
        }

        char fps_txt[64];
        std::snprintf(fps_txt, sizeof(fps_txt),
                      "FPS: %.1f | Process: %.0fms", fps_display, t_ms);
        int fh = annotated.rows;
        cv::putText(annotated, fps_txt, cv::Point(10, fh - 15),
                    cv::FONT_HERSHEY_SIMPLEX, 0.5,
                    cv::Scalar(150, 255, 150), 1);

        // Recording overlay
        if (is_recording && video_writer.isOpened()) {
            const char* rec_txt = is_paused ? "[PAUSED]" : "[REC]";
            auto color = is_paused
                ? cv::Scalar(0, 255, 255)   // Yellow
                : cv::Scalar(0, 0, 255);    // Red
            cv::putText(annotated, rec_txt,
                        cv::Point(annotated.cols - 110, 30),
                        cv::FONT_HERSHEY_SIMPLEX, 0.6, color, 2);

            if (!is_paused)
                video_writer.write(annotated);
        }

        cv::imshow("Tray Detector - Live (C++)", annotated);

        int key = cv::waitKey(1) & 0xFF;
        if (key == 'q') {
            std::cout << "Live camera stopped." << std::endl;
            break;
        } else if (key == 'r') {
            if (!is_recording) {
                std::string vid_path = SCREENSHOT_DIR + "/record_"
                                       + get_timestamp() + ".mp4";
                video_writer.open(vid_path,
                    cv::VideoWriter::fourcc('m', 'p', '4', 'v'),
                    15.0, cv::Size(640, 480));
                is_recording = true;
                is_paused = false;
                std::cout << "Start recording: " << vid_path << std::endl;
            } else {
                is_recording = false;
                is_paused = false;
                video_writer.release();
                std::cout << "Recording stopped & saved." << std::endl;
            }
        } else if (key == 'p') {
            if (is_recording) {
                is_paused = !is_paused;
                std::cout << "Recording "
                          << (is_paused ? "paused" : "resumed") << std::endl;
            }
        } else if (key == 's') {
            std::string ts = get_timestamp();
            double d_calib = pipeline.config().D_known_cm;
            char d_str[16];
            if (d_calib > 0)
                std::snprintf(d_str, sizeof(d_str), "%.1fcm", d_calib);
            else
                std::strcpy(d_str, "NA");

            std::string ss_path = SCREENSHOT_DIR + "/tray_detector_"
                                  + std::string(d_str) + "_" + ts + ".jpg";
            cv::imwrite(ss_path, annotated);
            print_result(result, "screenshot");
            std::cout << "Screenshot saved: " << ss_path << std::endl;
        }
    }

    if (video_writer.isOpened()) video_writer.release();
    cap->release();
    cv::destroyAllWindows();

    // ── Session Report ──────────────────────────────────────────────────
    std::printf("\n==================================================\n");
    std::printf("  LIVE CAMERA SESSION REPORT\n");
    std::printf("==================================================\n");
    std::printf("Total frames processed  : %d\n", stats_total);
    if (stats_valid > 0) {
        double avg = stats_sum / stats_valid;
        std::printf("Valid Frames (with D)   : %d (%.1f%%)\n",
                    stats_valid, 100.0 * stats_valid / std::max(1, stats_total));
        std::printf("Average Distance (D)    : %.2f cm\n", avg);
        std::printf("Minimum Distance        : %.2f cm\n", stats_min);
        std::printf("Maximum Distance        : %.2f cm\n", stats_max);
        std::printf("Outlier Spikes rejected : %d\n", stats_spikes);
        std::printf("--------------------------------------------------\n");
        std::printf("  FINAL ESTIMATED TRAY DISTANCE: %.2f cm\n", avg);
    } else {
        std::printf("Valid Frames            : 0 (No tray detected)\n");
    }
    std::printf("==================================================\n\n");
}


// ══════════════════════════════════════════════════════════════════════════
//  MAIN
// ══════════════════════════════════════════════════════════════════════════

struct CliArgs {
    std::string image;
    std::string input_dir;
    int camera_index = -1;  // -1 = not set
    std::string output_dir;
    std::string method = "auto";
    std::string weights;
    std::string params;
    bool no_yolo = false;
    bool lock_focus = false;
    int focus_value = 0;
    bool use_gpu = false;
    bool show_help = false;
};


static void print_help() {
    std::printf(R"(
Tray Detector (C++) — Camera to Tray Distance Detection

Usage:
  ./tray_detector --image PATH              Process single image
  ./tray_detector --input_dir PATH          Batch process directory
  ./tray_detector --camera [INDEX]          Live camera mode

Options:
  --image PATH          Path to single image file
  --input_dir PATH      Directory of images for batch processing
  --camera [INDEX]      Camera index for live mode (default: 0)
  --output_dir PATH     Output directory (default: tray_detector/results)
  --method METHOD       Detection method: auto, A, B, C (default: auto)
  --no-yolo             Disable YOLO, use full frame as ROI
  --weights PATH        Path to ONNX model weights
  --params PATH         Path to calibration YAML
  --lock-focus          Lock camera auto-focus (recommended)
  --focus-value N       Fixed focus value 0-255 (default: 0 = infinity)
  --gpu                 Use CUDA GPU backend for YOLO (PC only)
  --help                Show this help message

Examples:
  ./tray_detector --image test_tray25.0cm.jpg --method B
  ./tray_detector --camera 0 --method B --lock-focus --focus-value 0
  ./tray_detector --camera 2 --no-yolo --lock-focus
  ./tray_detector --input_dir images/ --output_dir results/
)");
}


static CliArgs parse_args(int argc, char* argv[]) {
    CliArgs args;

    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];

        if (arg == "--help" || arg == "-h") {
            args.show_help = true;
        } else if (arg == "--image" && i + 1 < argc) {
            args.image = argv[++i];
        } else if (arg == "--input_dir" && i + 1 < argc) {
            args.input_dir = argv[++i];
        } else if (arg == "--camera") {
            args.camera_index = 0;
            if (i + 1 < argc && argv[i + 1][0] != '-')
                args.camera_index = std::atoi(argv[++i]);
        } else if (arg == "--output_dir" && i + 1 < argc) {
            args.output_dir = argv[++i];
        } else if (arg == "--method" && i + 1 < argc) {
            args.method = argv[++i];
        } else if (arg == "--weights" && i + 1 < argc) {
            args.weights = argv[++i];
        } else if (arg == "--params" && i + 1 < argc) {
            args.params = argv[++i];
        } else if (arg == "--no-yolo") {
            args.no_yolo = true;
        } else if (arg == "--lock-focus") {
            args.lock_focus = true;
        } else if (arg == "--focus-value" && i + 1 < argc) {
            args.focus_value = std::atoi(argv[++i]);
        } else if (arg == "--gpu") {
            args.use_gpu = true;
        } else {
            std::cerr << "Unknown argument: " << arg << std::endl;
        }
    }

    return args;
}


int main(int argc, char* argv[]) {
    auto args = parse_args(argc, argv);

    if (args.show_help || argc < 2) {
        print_help();
        return 0;
    }

    // Validate: at least one mode must be selected
    bool has_mode = !args.image.empty() || !args.input_dir.empty()
                    || args.camera_index >= 0;
    if (!has_mode) {
        std::cerr << "Error: Specify --image, --input_dir, or --camera"
                  << std::endl;
        print_help();
        return 1;
    }

    // Default output dir
    std::string output_dir = args.output_dir.empty()
                             ? "tray_detector/results"
                             : args.output_dir;
    fs::create_directories(output_dir);

    // ── Load config ─────────────────────────────────────────────────────
    std::cout << "Initializing pipeline..." << std::endl;
    auto cfg = tray::load_config(args.params, "", args.weights);

    tray::TrayDistancePipeline pipeline(
        cfg, args.no_yolo, args.method, args.use_gpu);
    std::cout << "Pipeline ready.\n" << std::endl;

    // ── Run ─────────────────────────────────────────────────────────────
    if (!args.image.empty()) {
        process_single_image(pipeline, args.image, output_dir);
    } else if (!args.input_dir.empty()) {
        process_directory(pipeline, args.input_dir, output_dir);
    } else if (args.camera_index >= 0) {
        run_live_camera(pipeline, args.camera_index,
                        args.lock_focus, args.focus_value);
    }

    return 0;
}
