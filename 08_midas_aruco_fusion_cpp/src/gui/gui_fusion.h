/**
 * @file gui_fusion.h
 * @brief GTKmm-3.0 GUI for cup height estimation.
 * Identical layout to Python 07_midas_aruco_fusion.
 */

#pragma once

#ifdef HAS_GTKMM

#include <gtkmm.h>
#include <opencv2/core.hpp>
#include <functional>
#include <string>

namespace fusion {

class FusionGUI : public Gtk::Window {
public:
    FusionGUI();
    ~FusionGUI() override = default;

    /// Update the main camera view
    void update_frame(const cv::Mat& frame);

    /// Update status bar text
    void set_status(const std::string& text);

    /// Update measurement display
    void update_measurements(double height_cm, double distance_cm,
                             double diameter_cm, double volume_ml);

    /// Set calibration mode label
    void set_calib_mode(const std::string& mode);

    // Callbacks
    std::function<void(int)> on_calib_type;      
    std::function<void()>    on_start_calib;      
    std::function<void()>    on_snapshot;         
    std::function<void()>    on_generate_report;  

    std::function<void(double)> on_smart_exposure;
    std::function<void(double, double, double)> on_apply_anypoint;
    std::function<void()> on_reset_anypoint;
    
    std::function<void(bool)> on_toggle_normalize;
    std::function<void(bool)> on_toggle_bw;
    std::function<void(bool)> on_toggle_depth;
    std::function<void(int)>  on_queue_key;

protected:
    // Signal handlers
    bool on_key_press_event(GdkEventKey* event) override;

private:
    // Layout
    Gtk::Box main_box_{Gtk::ORIENTATION_HORIZONTAL};
    Gtk::Box left_panel_{Gtk::ORIENTATION_VERTICAL};
    
    // Camera view (Right Panel)
    Gtk::Image camera_view_;

    // --- System Status ---
    Gtk::Label lbl_status_calib_{"Mode: Live"};
    Gtk::Label lbl_status_ai_{"AI: Ready"};
    
    // --- Smart Exposure ---
    Gtk::Entry entry_exposure_;
    Gtk::Button btn_exp_mm_{"--"};
    Gtk::Button btn_exp_m_{" - "};
    Gtk::Button btn_exp_p_{" + "};
    Gtk::Button btn_exp_pp_{"++"};
    Gtk::Button btn_apply_exp_{"Apply"};
    
    // --- Moildev Anypoint ---
    Gtk::Entry entry_alpha_;
    Gtk::Entry entry_beta_;
    Gtk::Entry entry_zoom_;
    Gtk::Button btn_apply_anypoint_{"Apply Anypoint"};
    Gtk::Button btn_reset_anypoint_{"Reset View"};
    
    // --- Actions ---
    Gtk::Button btn_start_calib_{"▶ Start Calibration"};
    Gtk::Button btn_next_step_{"⏭ Next Step (Space)"};
    
    Gtk::CheckButton chk_normalize_{"Enable Normalize Lighting"};
    Gtk::CheckButton chk_bw_{"Enable Black & White Mode"};
    Gtk::CheckButton chk_depth_{"Enable MiDaS Depth Map"};
    
    Gtk::Button btn_record_{"Toggle Record (R)"};
    Gtk::Button btn_snapshot_{"Screenshot (S)"};
    Gtk::Button btn_cap_{"Capture Calib Point (C)"};
    Gtk::Button btn_quit_{"Quit (ESC)"};
    
    Gtk::Label lbl_setup_hint_{""};

    // Helper: convert cv::Mat to Gdk::Pixbuf
    Glib::RefPtr<Gdk::Pixbuf> mat_to_pixbuf(const cv::Mat& frame) const;

    void setup_ui();
    void connect_signals();
    
    void adj_exposure(double delta);
    void adj_alpha(double delta);
    void adj_beta(double delta);
    void adj_zoom(double delta);
};

} // namespace fusion

#endif // HAS_GTKMM
