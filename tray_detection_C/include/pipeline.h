#pragma once
/**
 * pipeline.h — Pipeline Orchestrator
 *
 * Menjalankan urutan:
 *   1. Undistort frame
 *   2. YOLO inference → tray bbox/mask + glass bbox
 *   3. Method B (primary), C (backup), A (fallback)
 *   4. Fusi → output final
 *   5. Temporal smoothing & outlier rejection
 *   6. Annotasi frame
 */

#include <deque>
#include <memory>
#include <opencv2/core.hpp>
#include "config.h"
#include "detector.h"
#include "fusion.h"

namespace tray {

class TrayDistancePipeline {
public:
    /**
     * @param cfg        Konfigurasi tray
     * @param no_yolo    Skip YOLO, gunakan full frame
     * @param method     "AUTO", "A", "B", atau "C"
     * @param use_gpu    Gunakan GPU CUDA untuk YOLO (PC only)
     */
    TrayDistancePipeline(const TrayConfig& cfg,
                         bool no_yolo = false,
                         const std::string& method = "AUTO",
                         bool use_gpu = false);

    /**
     * Proses satu frame → estimasi D_tray_cm.
     */
    FusedResult process_frame(const cv::Mat& frame);

    /**
     * Buat annotated copy dari frame dengan overlay visualisasi.
     */
    cv::Mat annotate_frame(const cv::Mat& frame, const FusedResult& result);

    // Access config (for D_known_cm in screenshot naming)
    const TrayConfig& config() const { return cfg_; }

private:
    TrayConfig cfg_;
    bool no_yolo_;
    std::string method_;

    std::unique_ptr<IDetector> detector_;

    // Undistort maps
    cv::Mat map1_, map2_;
    bool maps_initialized_ = false;

    // YOLO caching
    int frame_count_ = 0;
    int yolo_interval_ = 5;
    int cached_tray_bbox_[4]  = {0};
    int cached_glass_bbox_[4] = {0};
    cv::Mat cached_tray_mask_;
    bool has_cached_tray_ = false;
    bool has_cached_glass_ = false;

    // Temporal smoothing
    std::deque<double> d_tray_history_;
    static constexpr int HISTORY_SIZE = 15;
    static constexpr double SPIKE_THRESHOLD = 10.0;

    void init_undistort_maps(int h, int w);
    cv::Mat undistort(const cv::Mat& frame);
    void run_yolo(const cv::Mat& frame,
                  int tray_bbox[4], cv::Mat& tray_mask,
                  int glass_bbox[4],
                  bool& found_tray, bool& found_glass);
};

} // namespace tray
