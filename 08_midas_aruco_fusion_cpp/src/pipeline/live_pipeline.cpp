/**
 * @file live_pipeline.cpp
 * @brief 3-stage parallel pipeline implementation.
 */

#include "live_pipeline.h"
#include <opencv2/imgproc.hpp>
#include <chrono>
#include <iostream>
#include <sstream>
#include <iomanip>

namespace fusion {

LivePipeline::LivePipeline(const PipelineConfig& config)
    : config_(config), reporter_("session_reports")
{
    // Load calibration
    calib_data_ = load_calibration(config_.calibration_path);
    if (calib_data_.type > 0) {
        std::cout << "[Pipeline] Calibration type " << calib_data_.type << " loaded\n";
    }
}

LivePipeline::~LivePipeline() {
    stop();
}

bool LivePipeline::start() {
    if (running_) return true;

    // Initialize ArUco detector
    cv::Mat cam_mat = (cv::Mat_<double>(3, 3) <<
        500, 0, config_.frame_width / 2.0,
        0, 500, config_.frame_height / 2.0,
        0, 0, 1);
    cv::Mat dist = cv::Mat::zeros(5, 1, CV_64F);
    aruco_ = std::make_unique<ArucoDetector>(cam_mat, dist, config_.marker_size_cm);

    // Initialize YOLO
    yolo_ = std::make_unique<YoloDetector>(config_.yolo_model_path, 0.5f, 0.45f, 2);

    // Initialize Moildev
    if (config_.enable_moildev && !config_.camera_params_path.empty()) {
        moil_ = std::make_unique<MoilUndistorter>(config_.camera_params_path, config_.moil_mode);
        moil_->update_maps(0, 0, 0, config_.moil_zoom);
    }

    // Initialize Async MiDaS
    if (config_.enable_depth && !config_.midas_model_path.empty()) {
        async_midas_ = std::make_unique<AsyncMidas>(config_.midas_model_path, 2);
        async_midas_->start();
    }

    running_ = true;
    camera_thread_ = std::thread(&LivePipeline::camera_loop, this);
    process_thread_ = std::thread(&LivePipeline::process_loop, this);

    std::cout << "[Pipeline] Started — 3-stage parallel\n";
    return true;
}

void LivePipeline::stop() {
    if (!running_) return;
    running_ = false;

    if (async_midas_) async_midas_->stop();
    if (camera_thread_.joinable()) camera_thread_.join();
    if (process_thread_.joinable()) process_thread_.join();

    std::cout << "[Pipeline] Stopped\n";
}

void LivePipeline::camera_loop() {
    // Force V4L2 backend to prevent GStreamer from defaulting to 640x480
    cv::VideoCapture cap(config_.camera_id, cv::CAP_V4L2);
    if (!cap.isOpened()) {
        std::cerr << "[Camera] Failed to open camera " << config_.camera_id << " with V4L2\n";
        running_ = false;
        return;
    }

    // High resolution via USB requires MJPG compression
    cap.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
    cap.set(cv::CAP_PROP_FRAME_WIDTH, config_.frame_width);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, config_.frame_height);

    if (config_.manual_exposure > 0) {
        cap.set(cv::CAP_PROP_AUTO_EXPOSURE, 1); // 1 = manual in V4L2
        cap.set(cv::CAP_PROP_EXPOSURE, config_.manual_exposure);
        std::cout << "[Init] Exposure locked to: " << config_.manual_exposure << "\n";
    }

    // Smart Warmup: wait for auto-exposure to settle (brightness > 15)
    std::cout << "[Init] Camera warmup...\n";
    cv::Mat dummy, gray;
    for (int i = 0; i < 90; ++i) {
        if (!cap.read(dummy) || dummy.empty()) continue;
        cv::cvtColor(dummy, gray, cv::COLOR_BGR2GRAY);
        cv::Scalar mean_val = cv::mean(gray);
        if (mean_val[0] > 15.0) {
            std::cout << "[Init] Warmup complete at iteration " << i << "\n";
            break;
        }
    }

    std::cout << "[Camera] " << cap.get(cv::CAP_PROP_FRAME_WIDTH) << "x"
              << cap.get(cv::CAP_PROP_FRAME_HEIGHT) << "\n";

    while (running_) {
        cv::Mat frame;
        if (!cap.read(frame) || frame.empty()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
            continue;
        }
        frame_buffer_.try_push(frame);  // Drop if full (acceptable)
    }

    cap.release();
}

void LivePipeline::process_loop() {
    auto last_time = std::chrono::steady_clock::now();
    int frame_count = 0;

    while (running_) {
        auto frame_opt = frame_buffer_.try_pop();
        if (!frame_opt) {
            std::this_thread::sleep_for(std::chrono::microseconds(500));
            continue;
        }

        cv::Mat frame = std::move(*frame_opt);
        process_frame(frame);

        // FPS calculation
        frame_count++;
        auto now = std::chrono::steady_clock::now();
        double elapsed = std::chrono::duration<double>(now - last_time).count();
        if (elapsed >= 1.0) {
            std::lock_guard<std::mutex> lock(metrics_mutex_);
            metrics_.fps = frame_count / elapsed;
            metrics_.frame_count += frame_count;
            frame_count = 0;
            last_time = now;
        }

        // Store display frame
        {
            std::lock_guard<std::mutex> lock(display_mutex_);
            display_frame_ = frame.clone();
        }
    }
}

void LivePipeline::process_frame(cv::Mat& frame) {
    // Step 1: Moildev undistortion
    if (moil_ && moil_->is_ready()) {
        frame = moil_->undistort(frame);
    }

    // Step 2: Normalize lighting & BW
    if (normalize_) {
        auto [norm, led] = normalize_lighting(frame);
        frame = norm;
    }
    if (bw_mode_) {
        cv::cvtColor(frame, frame, cv::COLOR_BGR2GRAY);
        cv::cvtColor(frame, frame, cv::COLOR_GRAY2BGR);
    }

    // Step 3: ArUco detection
    auto aruco_results = aruco_->detect_with_fallback(frame, 3);

    // Step 4: YOLO detection
    auto yolo_dets = yolo_->detect(frame);

    // Step 5: Submit to async MiDaS
    cv::Mat depth_map;
    if (async_midas_ && config_.enable_depth) {
        if (!yolo_dets.empty()) {
            async_midas_->submit(frame, yolo_dets[0].bbox);
        } else {
            async_midas_->submit(frame);
        }
        if (async_midas_->has_new_result()) {
            depth_map = async_midas_->get_latest_depth();
        }
    }

    // Step 6: Compute height/volume
    compute_height(frame, aruco_results, yolo_dets, depth_map);

    // Step 7: Draw overlays
    if (show_aruco_) {
        frame = aruco_->annotate_frame(frame, aruco_results);
    }

    PipelineMetrics m;
    {
        std::lock_guard<std::mutex> lock(metrics_mutex_);
        m = metrics_;
    }
    draw_overlay(frame, m);

    // Step 8: Depth colormap (Single View Overlay)
    if (show_depth_ && !depth_map.empty()) {
        cv::Mat normalized;
        cv::normalize(depth_map, normalized, 0, 255, cv::NORM_MINMAX, CV_8UC1);
        cv::Mat colormap;
        cv::applyColorMap(normalized, colormap, cv::COLORMAP_MAGMA);
        
        cv::Mat resized_color;
        cv::resize(colormap, resized_color, frame.size());
        
        // Alpha blend
        cv::addWeighted(frame, 0.5, resized_color, 0.5, 0, frame);
    }
}

void LivePipeline::compute_height(cv::Mat& frame,
                                   const std::vector<ArucoResult>& aruco_res,
                                   const std::vector<Detection>& yolo_dets,
                                   const cv::Mat& depth_map) {
    auto best = aruco_->get_best_distance(aruco_res);
    if (!best) return;

    double z_tray = best->distance_cm;
    double m_rim = 0, m_tray = z_tray;

    // Get MiDaS depth values if available
    if (!depth_map.empty() && !yolo_dets.empty()) {
        MidasDepthEstimator dummy;
        m_tray = dummy.get_tray_depth(depth_map);
        m_rim = dummy.get_rim_depth(depth_map, yolo_dets[0].bbox);
    } else {
        m_rim = z_tray * 0.85;  // fallback
    }

    double height = 0;
    BBox bbox = yolo_dets.empty() ? BBox{0,0,0,0} : yolo_dets[0].bbox;

    switch (calib_data_.type) {
        case 1: height = calc_height_1point(m_rim, m_tray, z_tray, calib_data_.K); break;
        case 2: height = calc_height_2point(m_rim, m_tray, z_tray, calib_data_.m, calib_data_.c); break;
        case 3: height = calc_height_zgrid(m_rim, m_tray, z_tray, calib_data_.poly_K); break;
        case 4: height = calc_height_bbox(m_rim, m_tray, z_tray, bbox,
                     calib_data_.m_ref, calib_data_.c_ref, calib_data_.ref_bbox_area_px); break;
        case 5: height = calc_height_geom(z_tray, bbox, 500.0, calib_data_.poly_Kgeom); break;
        case 6: height = calc_height_bilateral_zgrid(m_rim, m_tray, z_tray,
                     calib_data_.poly_m, calib_data_.poly_c); break;
        case 7: height = calc_height_analytic(z_tray, bbox, calib_data_.A, calib_data_.B); break;
        default: break;
    }

    // Compute volume
    double rim_w = yolo_dets.empty() ? 0 : measure_rim_width_px(frame, bbox);
    double z_rim = z_tray - height;
    double diameter = calc_diameter(rim_w, std::max(0.1, z_rim), 500.0);
    double volume = calc_volume(height, diameter);

    // Update metrics
    {
        std::lock_guard<std::mutex> lock(metrics_mutex_);
        metrics_.cup_height_cm = height;
        metrics_.aruco_distance_cm = z_tray;
        metrics_.diameter_cm = diameter;
        metrics_.volume_ml = volume;
        metrics_.aruco_found = !aruco_res.empty();
        metrics_.cup_found = !yolo_dets.empty();
    }

    // Add to reporter
    if (height > 0) {
        SessionEntry entry;
        entry.cup_height_cm = height;
        entry.aruco_distance_cm = z_tray;
        entry.diameter_cm = diameter;
        entry.volume_ml = volume;
        entry.frame_num = metrics_.frame_count;
        reporter_.add_entry(entry);
    }
}

void LivePipeline::draw_overlay(cv::Mat& frame, const PipelineMetrics& m) {
    int y = 30;
    auto put = [&](const std::string& text, const cv::Scalar& color) {
        cv::putText(frame, text, cv::Point(10, y),
                    cv::FONT_HERSHEY_SIMPLEX, 0.6, color, 2);
        y += 25;
    };

    std::ostringstream ss;
    ss << std::fixed << std::setprecision(1);

    ss << "FPS: " << m.fps;
    put(ss.str(), cv::Scalar(0, 255, 0));

    if (m.aruco_found) {
        ss.str(""); ss << "ArUco: " << m.aruco_distance_cm << " cm";
        put(ss.str(), cv::Scalar(0, 255, 255));
    }

    if (m.cup_height_cm > 0) {
        ss.str(""); ss << "Height: " << m.cup_height_cm << " cm";
        put(ss.str(), cv::Scalar(255, 200, 0));
        ss.str(""); ss << "Diameter: " << m.diameter_cm << " cm";
        put(ss.str(), cv::Scalar(255, 200, 0));
        ss.str(""); ss << "Volume: " << m.volume_ml << " mL";
        put(ss.str(), cv::Scalar(0, 200, 255));
    }

    // Calib mode badge
    if (calib_data_.type > 0) {
        ss.str(""); ss << "Calib: Type " << calib_data_.type;
        put(ss.str(), cv::Scalar(200, 100, 255));
    }
}

cv::Mat LivePipeline::get_display_frame() const {
    std::lock_guard<std::mutex> lock(display_mutex_);
    return display_frame_.clone();
}

cv::Mat LivePipeline::get_depth_colormap() const {
    std::lock_guard<std::mutex> lock(display_mutex_);
    return depth_colormap_.clone();
}

PipelineMetrics LivePipeline::get_metrics() const {
    std::lock_guard<std::mutex> lock(metrics_mutex_);
    return metrics_;
}

void LivePipeline::set_calibration(const CalibData& calib) {
    std::lock_guard<std::mutex> lock(metrics_mutex_);
    calib_data_ = calib;
    std::cout << "[Pipeline] Calibration updated to type " << calib.type << "\n";
}

} // namespace fusion
