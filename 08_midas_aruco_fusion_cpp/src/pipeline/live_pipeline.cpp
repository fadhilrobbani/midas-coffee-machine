/**
 * @file live_pipeline.cpp
 * @brief Full feature parity with Python 07_midas_aruco_fusion/core/live_pipeline.py
 */

#include "live_pipeline.h"
#include <opencv2/imgproc.hpp>
#include <opencv2/imgcodecs.hpp>
#include <nlohmann/json.hpp>
#include <set>
#include <fstream>
#include <chrono>
#include <iostream>
#include <sstream>
#include <iomanip>
#include <filesystem>
#include <ctime>

namespace fusion {

// ─── Helpers ─────────────────────────────────────────────────────────────────

static double now_sec() {
    return std::chrono::duration<double>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}

static double read_focal_from_json(const std::string& json_path,
                                   const std::string& cam_name) {
    try {
        std::ifstream f(json_path);
        if (!f.is_open()) return 0.0;
        nlohmann::json j; f >> j;
        if (!cam_name.empty() && j.contains(cam_name)) {
            auto& p = j[cam_name];
            double p5     = p.value("parameter5", 0.0);
            double calib  = p.value("calibrationRatio", 1.0);
            if (calib > 0) return p5 / calib;
        }
        // Try first key as fallback
        for (auto it = j.begin(); it != j.end(); ++it) {
            double p5    = it.value().value("parameter5", 0.0);
            double calib = it.value().value("calibrationRatio", 1.0);
            if (p5 > 0 && calib > 0) return p5 / calib;
        }
    } catch (...) {}
    return 0.0;
}

// ─── Constructor / Destructor ────────────────────────────────────────────────

LivePipeline::LivePipeline(const PipelineConfig& config)
    : config_(config), reporter_("session_reports")
{
    calib_data_ = load_calibration(config_.calibration_path);
    if (calib_data_.type > 0)
        std::cout << "[Pipeline] Calibration type " << calib_data_.type << " loaded\n";
}

LivePipeline::~LivePipeline() { stop(); }

// ─── start() ────────────────────────────────────────────────────────────────

bool LivePipeline::init_models() {
    // --- Focal length: prefer Moildev JSON, else rough estimate ---
    if (!config_.camera_params_path.empty()) {
        focal_px_ = read_focal_from_json(config_.camera_params_path, config_.camera_name);
    }
    if (focal_px_ <= 0) {
        focal_px_ = std::min(config_.frame_width, config_.frame_height) * 0.6;
        std::cout << "[Pipeline] Focal fallback: " << focal_px_ << " px\n";
    } else {
        std::cout << "[Pipeline] Focal from JSON: " << focal_px_ << " px\n";
    }

    // --- ArUco ---
    cv::Mat cam_mat = (cv::Mat_<double>(3, 3) <<
        focal_px_, 0, config_.frame_width  / 2.0,
        0, focal_px_, config_.frame_height / 2.0,
        0, 0, 1);
    cv::Mat dist = cv::Mat::zeros(5, 1, CV_64F);
    aruco_ = std::make_unique<ArucoDetector>(cam_mat, dist, config_.marker_size_cm);

    // --- YOLO ---
    if (!config_.yolo_model_path.empty())
        yolo_ = std::make_unique<YoloDetector>(config_.yolo_model_path, 0.45f, 0.45f, 2);

    // --- Moildev ---
    if (config_.enable_moildev && !config_.camera_params_path.empty()) {
        moil_ = std::make_unique<MoilUndistorter>(config_.camera_params_path, config_.camera_name, config_.moil_mode);
        moil_->update_maps(0, 0, 0, config_.moil_zoom);
        std::cout << "[Moildev] Initialized mode=" << config_.moil_mode
                  << " zoom=" << config_.moil_zoom << "\n";
    }

    // --- MiDaS (direct, rate-limited) ---
    if (config_.enable_depth && !config_.midas_model_path.empty()) {
        midas_ = std::make_unique<MidasDepthEstimator>(config_.midas_model_path, 2);
        if (midas_->is_ready())
            std::cout << "[MiDaS] Model loaded: " << config_.midas_model_path << "\n";
        else
            std::cout << "[MiDaS] WARNING: Model failed to load!\n";
    }

    // --- Directories ---
    std::filesystem::create_directories("screenshots");
    std::filesystem::create_directories("recorded_videos");

    return true;
}

bool LivePipeline::start() {
    if (running_) return true;
    running_ = true;
    camera_thread_  = std::thread(&LivePipeline::camera_loop, this);
    process_thread_ = std::thread(&LivePipeline::process_loop, this);
    std::cout << "[Pipeline] Started — 3-stage parallel\n";
    return true;
}

// ─── stop() ─────────────────────────────────────────────────────────────────

void LivePipeline::stop() {
    if (!running_) return;
    running_ = false;
    if (camera_thread_.joinable())  camera_thread_.join();
    if (process_thread_.joinable()) process_thread_.join();
    { std::lock_guard<std::mutex> lk(recording_mutex_);
      if (video_writer_.isOpened()) video_writer_.release(); }
    reporter_.generate_report("auto_exit");
    std::cout << "[Pipeline] Stopped\n";
}

// ─── camera_loop() ──────────────────────────────────────────────────────────

void LivePipeline::camera_loop() {
    cv::VideoCapture cap(config_.camera_id, cv::CAP_V4L2);
    if (!cap.isOpened()) {
        std::cerr << "[Camera] Failed to open device " << config_.camera_id << "\n";
        running_ = false; return;
    }

    cap.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M','J','P','G'));
    cap.set(cv::CAP_PROP_FRAME_WIDTH,  config_.frame_width);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, config_.frame_height);

    if (config_.manual_exposure > 0) {
        cap.set(cv::CAP_PROP_AUTO_EXPOSURE, 1);
        cap.set(cv::CAP_PROP_EXPOSURE, config_.manual_exposure);
        std::cout << "[Init] Exposure locked: " << config_.manual_exposure << "\n";
    }

    std::cout << "[Init] Camera warmup...\n";
    cv::Mat dummy, gray;
    for (int i = 0; i < 90 && running_; ++i) {
        if (!cap.read(dummy) || dummy.empty()) continue;
        cv::cvtColor(dummy, gray, cv::COLOR_BGR2GRAY);
        if (cv::mean(gray)[0] > 15.0) {
            std::cout << "[Init] Warmup done at frame " << i << "\n"; break;
        }
    }
    std::cout << "[Camera] " << cap.get(cv::CAP_PROP_FRAME_WIDTH)
              << "x" << cap.get(cv::CAP_PROP_FRAME_HEIGHT) << "\n";

    while (running_) {
        double req_exp = requested_exposure_.exchange(-1.0);
        double req_gain = requested_gain_.exchange(-1.0);
        double req_bri = requested_brightness_.exchange(-1000.0);
        if (req_exp > 0) {
            cap.set(cv::CAP_PROP_AUTO_EXPOSURE, 1);
            cap.set(cv::CAP_PROP_EXPOSURE, req_exp);
            if (req_gain >= 0) cap.set(cv::CAP_PROP_GAIN, req_gain);
            if (req_bri > -1000) cap.set(cv::CAP_PROP_BRIGHTNESS, req_bri);
            std::cout << "[Camera] HW applied: exp=" << req_exp << " gain=" << req_gain << " bri=" << req_bri << "\n";
        }

        cv::Mat frame;
        if (!cap.read(frame) || frame.empty()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1)); continue;
        }
        frame_buffer_.try_push(frame);
    }
    cap.release();
}

// ─── process_loop() ─────────────────────────────────────────────────────────

void LivePipeline::process_loop() {
    auto last_fps_t  = std::chrono::steady_clock::now();
    int  frame_count = 0;

    while (running_) {
        auto frame_opt = frame_buffer_.try_pop();
        if (!frame_opt) {
            std::this_thread::sleep_for(std::chrono::microseconds(500)); continue;
        }
        cv::Mat frame = std::move(*frame_opt);
        process_frame(frame);

        frame_count++;
        auto now = std::chrono::steady_clock::now();
        double elapsed = std::chrono::duration<double>(now - last_fps_t).count();
        if (elapsed >= 1.0) {
            std::lock_guard<std::mutex> lk(metrics_mutex_);
            metrics_.fps = frame_count / elapsed;
            metrics_.frame_count += frame_count;
            frame_count = 0;
            last_fps_t  = now;
        }

        { std::lock_guard<std::mutex> lk(display_mutex_);
          display_frame_ = frame.clone(); }

        // Recording
        { std::lock_guard<std::mutex> lk(recording_mutex_);
          if (is_recording_ && video_writer_.isOpened())
              video_writer_.write(frame); }
    }
}

// ─── process_frame() ────────────────────────────────────────────────────────

void LivePipeline::process_frame(cv::Mat& frame) {
    // 1. Moildev undistortion
    if (moil_ && moil_->is_ready())
        frame = moil_->undistort(frame);

    // 2. Normalize / BW
    if (normalize_) {
        auto [norm, led] = normalize_lighting(frame);
        frame   = norm;
        led_on_ = led;
    }
    if (bw_mode_) {
        cv::cvtColor(frame, frame, cv::COLOR_BGR2GRAY);
        cv::cvtColor(frame, frame, cv::COLOR_GRAY2BGR);
    }

    // 3. LED state (only if not using normalize which already detects it)
    if (!normalize_) led_on_ = detect_led_state(frame);

    // 4. ArUco + YOLO
    std::vector<ArucoResult> aruco_res;
    std::vector<Detection>   yolo_dets;
    run_aruco_yolo(frame, aruco_res, yolo_dets);

    // 5. MiDaS rate-limited
    CalibData calib;
    { std::lock_guard<std::mutex> lk(calib_mutex_); calib = calib_data_; }

    cv::Mat depth_map;
    bool need_midas = (midas_ && midas_->is_ready() && config_.enable_depth
                       && CTYPE_NO_MIDAS.find(calib.type) == CTYPE_NO_MIDAS.end());
    if (need_midas) {
        run_midas_rate_limited(frame, yolo_dets);
        // depth_map will be empty if not due this frame; EMA inside MiDaS handles it
        depth_map = last_depth_norm_; // reuse last
    }

    // 6. Compute heights
    compute_heights(frame, depth_map);

    // 7. Draw
    if (show_aruco_ && !aruco_res.empty())
        frame = aruco_->annotate_frame(frame, aruco_res);

    draw_overlay(frame);
    if (show_depth_) draw_pip_depth(frame);
}

// ─── run_aruco_yolo() ───────────────────────────────────────────────────────

void LivePipeline::run_aruco_yolo(const cv::Mat& frame,
                                   std::vector<ArucoResult>& aruco_res,
                                   std::vector<Detection>& yolo_dets) {
    aruco_res = aruco_->detect_with_fallback(frame, 3);

    if (!aruco_res.empty()) {
        auto best = aruco_->get_best_distance(aruco_res);
        if (best) {
            z_tray_live_ = best->distance_cm;
            auto corners = aruco_res[0].corners;
            if (!corners.empty()) {
                float x1 = corners[0].x, y1 = corners[0].y,
                      x2 = corners[0].x, y2 = corners[0].y;
                for (auto& c : corners) {
                    x1 = std::min(x1, c.x); y1 = std::min(y1, c.y);
                    x2 = std::max(x2, c.x); y2 = std::max(y2, c.y);
                }
                int px = std::max(2, (int)((x2-x1)/10));
                int py = std::max(2, (int)((y2-y1)/10));
                aruco_roi_ = BBox{(int)x1+px, (int)y1+py, (int)x2-px, (int)y2-py};
            }
        }
    }

    if (yolo_) {
        yolo_dets = yolo_->detect(frame);
        // Sort left-to-right, keep up to 2
        if (yolo_dets.size() > 2) {
            std::sort(yolo_dets.begin(), yolo_dets.end(),
                [](const Detection& a, const Detection& b){ return a.bbox.x1 < b.bbox.x1; });
            yolo_dets.resize(2);
        }
        cup_count_ = (int)yolo_dets.size();
        for (int i = 0; i < cup_count_; ++i) cup_bboxes_[i] = yolo_dets[i].bbox;
    }
}

// ─── run_midas_rate_limited() ────────────────────────────────────────────────

void LivePipeline::run_midas_rate_limited(const cv::Mat& frame,
                                           const std::vector<Detection>& yolo_dets) {
    (void)yolo_dets;
    if (!midas_ || !midas_->is_ready()) return;
    double now = now_sec();
    if ((now - last_midas_t_) < (1.0 / MIDAS_FPS_LIMIT)) return;
    if (z_tray_live_ <= 0 || !aruco_roi_) return;

    try {
        cv::Mat depth = midas_->process(frame);
        cv::Mat smooth = midas_->get_smoothed_depth(depth);
        cv::normalize(smooth, last_depth_norm_, 0, 255, cv::NORM_MINMAX, CV_8UC1);

        // Store raw depth for height calc
        { std::lock_guard<std::mutex> lk(display_mutex_);
          depth_colormap_ = last_depth_norm_.clone(); }

        last_midas_t_ = now;
    } catch (const std::exception& e) {
        std::cerr << "[MiDaS] Error: " << e.what() << "\n";
        last_midas_t_ = now; // prevent tight retry loop
    }
}

// ─── compute_heights() ──────────────────────────────────────────────────────

void LivePipeline::compute_heights(const cv::Mat& frame,
                                    const cv::Mat& depth_map) {
    CalibData calib;
    { std::lock_guard<std::mutex> lk(calib_mutex_); calib = calib_data_; }

    bool no_midas = (CTYPE_NO_MIDAS.find(calib.type) != CTYPE_NO_MIDAS.end());

    std::lock_guard<std::mutex> lk(metrics_mutex_);
    metrics_.aruco_found        = (z_tray_live_ > 0);
    metrics_.aruco_distance_cm  = z_tray_live_;
    metrics_.led_on             = led_on_;

    for (int i = 0; i < 2; ++i) {
        metrics_.cup_found[i]    = (i < cup_count_);
        metrics_.cup_height_cm[i]= 0;
        metrics_.diameter_cm[i]  = 0;
        metrics_.volume_ml[i]    = 0;
    }

    if (z_tray_live_ <= 0 || cup_count_ == 0) return;

    double m_tray = 0, m_rim = 0;
    bool has_depth = (!depth_map.empty() && midas_);
    if (has_depth) {
        m_tray = midas_->get_tray_depth(depth_map);
    }

    for (int i = 0; i < cup_count_; ++i) {
        const BBox& bbox = cup_bboxes_[i];
        double height_raw = 0;

        if (no_midas) {
            // Fast-path: no MiDaS needed
            if (calib.type == 5)
                height_raw = calc_height_geom(z_tray_live_, bbox, focal_px_, calib.poly_Kgeom);
            else if (calib.type == 7)
                height_raw = calc_height_analytic(z_tray_live_, bbox, calib.A, calib.B);
        } else if (has_depth && m_tray > 0) {
            m_rim = midas_->get_rim_depth(depth_map, bbox);
            if (m_rim > 0) {
                switch (calib.type) {
                    case 1: height_raw = calc_height_1point(m_rim, m_tray, z_tray_live_, calib.K); break;
                    case 2: height_raw = calc_height_2point(m_rim, m_tray, z_tray_live_, calib.m, calib.c); break;
                    case 3: height_raw = calc_height_zgrid(m_rim, m_tray, z_tray_live_, calib.poly_K); break;
                    case 4: height_raw = calc_height_bbox(m_rim, m_tray, z_tray_live_, bbox,
                                             calib.m_ref, calib.c_ref, calib.ref_bbox_area_px); break;
                    case 6: height_raw = calc_height_bilateral_zgrid(m_rim, m_tray, z_tray_live_,
                                             calib.poly_m, calib.poly_c); break;
                    default: height_raw = calc_height_1point(m_rim, m_tray, z_tray_live_, calib.K); break;
                }
            }
        }

        // EMA smoothing
        if (height_raw > 0) {
            if (cup_heights_ema_[i] < 0)
                cup_heights_ema_[i] = height_raw;
            else
                cup_heights_ema_[i] = EMA_ALPHA * height_raw + (1.0 - EMA_ALPHA) * cup_heights_ema_[i];
            metrics_.cup_height_cm[i] = cup_heights_ema_[i];
        } else {
            cup_heights_ema_[i] = -1.0;
        }

        // Volume / diameter
        if (metrics_.cup_height_cm[i] > 0) {
            double z_rim = std::max(0.1, z_tray_live_ - metrics_.cup_height_cm[i]);
            double rim_w = measure_rim_width_px(frame, bbox);
            metrics_.diameter_cm[i] = calc_diameter(rim_w, z_rim, focal_px_);
            metrics_.volume_ml[i]   = calc_volume(metrics_.cup_height_cm[i], metrics_.diameter_cm[i]);
        }
    }

    // Reset cups no longer detected
    for (int i = cup_count_; i < 2; ++i) cup_heights_ema_[i] = -1.0;
}

// ─── draw_overlay() ─────────────────────────────────────────────────────────

void LivePipeline::draw_overlay(cv::Mat& frame) {
    if (frame.empty()) return;
    int h = frame.rows, w = frame.cols;
    PipelineMetrics m;
    { std::lock_guard<std::mutex> lk(metrics_mutex_); m = metrics_; }

    // Dynamic scale like Python: S = max(0.5, w/1000.0)
    double S = std::max(0.5, w / 1000.0);
    int font = cv::FONT_HERSHEY_SIMPLEX;

    // Dark info panel top-left
    int pw = (int)(560*S), ph = (int)(155*S);
    cv::rectangle(frame, {20,20}, {20+pw, 20+ph}, {25,25,25}, -1);
    cv::rectangle(frame, {20,20}, {20+pw, 20+ph}, {90,90,90}, 2);

    // Header
    std::ostringstream ss;
    ss << std::fixed << std::setprecision(1);
    ss << "CUP HEIGHTS";
    cv::putText(frame, ss.str(), {(int)(40*S),(int)(45*S)}, font, 0.55*S, {170,170,170}, 2);
    if (m.aruco_found) {
        ss.str(""); ss << "Z_tray: " << m.aruco_distance_cm << " cm";
        cv::putText(frame, ss.str(), {(int)(230*S),(int)(40*S)}, font, 0.5*S, {255,160,60}, 2);
    }

    // Per-cup rows
    int base_y = (int)(95*S);
    for (int i = 0; i < 2; ++i) {
        int yp = base_y + i*(int)(50*S);
        std::string lbl = "CUP " + std::to_string(i+1) + ":";
        if (m.cup_height_cm[i] > 0) {
            cv::putText(frame, lbl, {(int)(40*S), yp-(int)(15*S)}, font, 0.6*S, {200,200,200}, 2);
            ss.str(""); ss << m.cup_height_cm[i] << " cm";
            cv::putText(frame, ss.str(), {(int)(115*S), yp+(int)(5*S)}, cv::FONT_HERSHEY_DUPLEX, 1.3*S, {0,255,100}, 3);
            ss.str(""); ss << "D:" << m.diameter_cm[i] << "cm";
            cv::putText(frame, ss.str(), {(int)(395*S), yp-(int)(4*S)}, font, 0.45*S, {200,200,255}, 2);
            ss.str(""); ss << "V:" << (int)m.volume_ml[i] << "mL";
            cv::putText(frame, ss.str(), {(int)(480*S), yp-(int)(4*S)}, font, 0.45*S, {255,220,80}, 2);
        } else {
            cv::putText(frame, lbl, {(int)(40*S), yp-(int)(15*S)}, font, 0.6*S, {100,100,100}, 2);
            cv::putText(frame, "-- cm", {(int)(115*S), yp+(int)(5*S)}, cv::FONT_HERSHEY_DUPLEX, 1.3*S, {70,70,70}, 3);
        }
    }

    // Recording indicator
    bool rec;
    { std::lock_guard<std::mutex> lk(recording_mutex_); rec = is_recording_; }
    if (rec) {
        auto t = std::chrono::steady_clock::now().time_since_epoch().count();
        if ((t / 500000000LL) % 2 == 0) {  // blink every 0.5s
            cv::circle(frame, {w-(int)(140*S), (int)(45*S)}, (int)(15*S), {0,0,255}, -1);
            cv::putText(frame, "REC", {w-(int)(115*S), (int)(58*S)}, font, 0.9*S, {0,0,255}, 3);
        }
    }

    // Status bar bottom
    int bh = (int)(45*S);
    cv::rectangle(frame, {0, h-bh}, {w, h}, {15,15,15}, -1);
    std::string led_txt = m.led_on ? "LED:ON" : "LED:OFF";
    cv::Scalar led_col  = m.led_on ? cv::Scalar(0,220,255) : cv::Scalar(100,100,100);
    cv::putText(frame, led_txt, {w-(int)(200*S), h-(int)(15*S)}, font, 0.5*S, led_col, 2);

    ss.str(""); ss << "FPS:" << std::setprecision(1) << m.fps
                   << " | ArUco:" << (m.aruco_found ? "OK" : "X")
                   << " | YOLO:" << (m.cup_found[0] ? "OK" : "X")
                   << " | [R]Rec  [S]Shot  [Q]Quit";
    cv::putText(frame, ss.str(), {(int)(20*S), h-(int)(15*S)}, font, 0.5*S, {130,200,130}, 2);
}

// ─── draw_pip_depth() ───────────────────────────────────────────────────────

void LivePipeline::draw_pip_depth(cv::Mat& frame) {
    if (last_depth_norm_.empty()) return;
    int h = frame.rows, w = frame.cols;
    double S = std::max(0.5, w / 1000.0);

    cv::Mat color;
    cv::applyColorMap(last_depth_norm_, color, cv::COLORMAP_JET);

    int pip_h = (int)(h / 3.2), pip_w = (int)(w / 3.2);
    cv::Mat pip; cv::resize(color, pip, {pip_w, pip_h});

    int py1 = h - pip_h - (int)(40*S), px1 = w - pip_w - (int)(10*S);
    pip.copyTo(frame(cv::Rect(px1, py1, pip_w, pip_h)));
    cv::rectangle(frame, {px1,py1}, {px1+pip_w, py1+pip_h}, {200,200,200}, 2);
    cv::putText(frame, "MiDaS Depth", {px1+(int)(12*S), py1+(int)(28*S)},
                cv::FONT_HERSHEY_SIMPLEX, 0.5*S, {255,255,255}, 2);
}

// ─── Accessors ───────────────────────────────────────────────────────────────

cv::Mat LivePipeline::get_display_frame() const {
    std::lock_guard<std::mutex> lk(display_mutex_);
    return display_frame_.clone();
}
cv::Mat LivePipeline::get_depth_colormap() const {
    std::lock_guard<std::mutex> lk(display_mutex_);
    return depth_colormap_.clone();
}
PipelineMetrics LivePipeline::get_metrics() const {
    std::lock_guard<std::mutex> lk(metrics_mutex_);
    return metrics_;
}
void LivePipeline::set_calibration(const CalibData& calib) {
    std::lock_guard<std::mutex> lk(calib_mutex_);
    calib_data_ = calib;
    std::cout << "[Pipeline] Calibration updated to type " << calib.type << "\n";
}

// ─── Recording / Screenshot ──────────────────────────────────────────────────

void LivePipeline::toggle_recording() {
    std::lock_guard<std::mutex> lk(recording_mutex_);
    if (!is_recording_) {
        auto t    = std::time(nullptr);
        char buf[64]; std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", std::localtime(&t));
        std::string path = std::string("recorded_videos/fusion_") + buf + ".avi";
        cv::Mat f = get_display_frame();
        if (f.empty()) return;
        video_writer_.open(path, cv::VideoWriter::fourcc('X','V','I','D'), 10, f.size());
        is_recording_ = true;
        std::cout << "[REC] Started: " << path << "\n";
    } else {
        is_recording_ = false;
        if (video_writer_.isOpened()) video_writer_.release();
        std::cout << "[REC] Stopped\n";
    }
}

void LivePipeline::save_screenshot(const std::string& dir) {
    cv::Mat f = get_display_frame();
    if (f.empty()) return;
    auto t = std::time(nullptr);
    char buf[64]; std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", std::localtime(&t));
    std::string path = dir + "/fusion_" + buf + ".jpg";
    cv::imwrite(path, f);
    std::cout << "[SHOT] " << path << "\n";
}

} // namespace fusion
