/**
 * @file gui_fusion.cpp
 * @brief GTKmm-3.0 GUI implementation.
 * Identical layout to Python 07_midas_aruco_fusion.
 */

#ifdef HAS_GTKMM

#include "gui_fusion.h"
#include <opencv2/imgproc.hpp>
#include <sstream>
#include <iomanip>
#include <iostream>

namespace fusion {

FusionGUI::FusionGUI() {
    set_title("ArUco + MiDaS | Fusion Interface (C++)");
    set_default_size(1280, 720);
    
    // Enable dark theme to match typical Python GTK feel (optional but nice)
    auto settings = Gtk::Settings::get_default();
    if (settings) {
        settings->property_gtk_application_prefer_dark_theme() = true;
    }

    setup_ui();
    connect_signals();
}

void FusionGUI::setup_ui() {
    main_box_.set_spacing(10);
    add(main_box_);

    // ─── Sidebar Kiri (Controls) ───
    left_panel_.set_spacing(5);
    left_panel_.set_border_width(10);
    left_panel_.set_size_request(320, -1);

    // System Status Frame
    auto f_sys = Gtk::make_managed<Gtk::Frame>("System Status");
    auto vb_s = Gtk::make_managed<Gtk::Box>(Gtk::ORIENTATION_VERTICAL, 5);
    vb_s->set_border_width(5);
    vb_s->pack_start(lbl_status_calib_, Gtk::PACK_SHRINK);
    vb_s->pack_start(lbl_status_ai_, Gtk::PACK_SHRINK);

    // Smart Exposure Control
    auto hb_exp = Gtk::make_managed<Gtk::Box>(Gtk::ORIENTATION_HORIZONTAL, 3);
    auto lbl_exp = Gtk::make_managed<Gtk::Label>("Smart Exp:");
    hb_exp->pack_start(*lbl_exp, Gtk::PACK_SHRINK);
    
    entry_exposure_.set_text("1.0");
    entry_exposure_.set_tooltip_text("1.0 (Gelap) - 10.0 (Sangat Terang). Otomatis mengatur Shutter, ISO & EV.");
    entry_exposure_.set_width_chars(6);

    hb_exp->pack_start(btn_exp_mm_, Gtk::PACK_SHRINK);
    hb_exp->pack_start(btn_exp_m_, Gtk::PACK_SHRINK);
    hb_exp->pack_start(entry_exposure_, Gtk::PACK_EXPAND_WIDGET);
    hb_exp->pack_start(btn_exp_p_, Gtk::PACK_SHRINK);
    hb_exp->pack_start(btn_exp_pp_, Gtk::PACK_SHRINK);
    hb_exp->pack_start(btn_apply_exp_, Gtk::PACK_SHRINK);
    
    vb_s->pack_start(*hb_exp, Gtk::PACK_SHRINK, 5);
    f_sys->add(*vb_s);
    left_panel_.pack_start(*f_sys, Gtk::PACK_SHRINK, 5);

    // Moildev Anypoint Frame
    auto f_moil = Gtk::make_managed<Gtk::Frame>("Moildev Anypoint Controls");
    auto vb_m = Gtk::make_managed<Gtk::Box>(Gtk::ORIENTATION_VERTICAL, 5);
    vb_m->set_border_width(5);

    auto make_adj_row = [](const std::string& label, Gtk::Button& b_min, Gtk::Entry& entry, Gtk::Button& b_plus) {
        auto hb = Gtk::make_managed<Gtk::Box>(Gtk::ORIENTATION_HORIZONTAL, 5);
        auto lbl = Gtk::make_managed<Gtk::Label>(label);
        lbl->set_width_chars(12);
        lbl->set_alignment(0.0, 0.5);
        hb->pack_start(*lbl, Gtk::PACK_SHRINK);
        
        b_min.set_label(" - ");
        b_plus.set_label(" + ");
        hb->pack_start(b_min, Gtk::PACK_SHRINK);
        hb->pack_start(entry, Gtk::PACK_EXPAND_WIDGET);
        hb->pack_start(b_plus, Gtk::PACK_SHRINK);
        return hb;
    };

    entry_alpha_.set_text("0.0");
    entry_beta_.set_text("0.0");
    entry_zoom_.set_text("1.4");

    auto btn_a_min = Gtk::make_managed<Gtk::Button>();
    auto btn_a_plus = Gtk::make_managed<Gtk::Button>();
    vb_m->pack_start(*make_adj_row("Alpha (Pitch):", *btn_a_min, entry_alpha_, *btn_a_plus), Gtk::PACK_SHRINK);
    
    auto btn_b_min = Gtk::make_managed<Gtk::Button>();
    auto btn_b_plus = Gtk::make_managed<Gtk::Button>();
    vb_m->pack_start(*make_adj_row("Beta (Yaw):", *btn_b_min, entry_beta_, *btn_b_plus), Gtk::PACK_SHRINK);
    
    auto btn_z_min = Gtk::make_managed<Gtk::Button>();
    auto btn_z_plus = Gtk::make_managed<Gtk::Button>();
    vb_m->pack_start(*make_adj_row("Zoom:", *btn_z_min, entry_zoom_, *btn_z_plus), Gtk::PACK_SHRINK);

    // Adj handlers
    btn_a_min->signal_clicked().connect([this]() { adj_alpha(-5.0); });
    btn_a_plus->signal_clicked().connect([this]() { adj_alpha(5.0); });
    btn_b_min->signal_clicked().connect([this]() { adj_beta(-5.0); });
    btn_b_plus->signal_clicked().connect([this]() { adj_beta(5.0); });
    btn_z_min->signal_clicked().connect([this]() { adj_zoom(-0.1); });
    btn_z_plus->signal_clicked().connect([this]() { adj_zoom(0.1); });

    auto hb_moil_btns = Gtk::make_managed<Gtk::Box>(Gtk::ORIENTATION_HORIZONTAL, 5);
    hb_moil_btns->pack_start(btn_apply_anypoint_, Gtk::PACK_EXPAND_WIDGET);
    hb_moil_btns->pack_start(btn_reset_anypoint_, Gtk::PACK_EXPAND_WIDGET);
    vb_m->pack_start(*hb_moil_btns, Gtk::PACK_SHRINK, 5);

    f_moil->add(*vb_m);
    left_panel_.pack_start(*f_moil, Gtk::PACK_SHRINK, 5);

    // Actions Frame
    auto f_act = Gtk::make_managed<Gtk::Frame>("Actions");
    auto vb_a = Gtk::make_managed<Gtk::Box>(Gtk::ORIENTATION_VERTICAL, 5);
    vb_a->set_border_width(5);

    vb_a->pack_start(btn_start_calib_, Gtk::PACK_SHRINK);
    vb_a->pack_start(btn_next_step_, Gtk::PACK_SHRINK);
    
    // Hide calib buttons by default
    btn_start_calib_.hide();
    btn_next_step_.hide();

    vb_a->pack_start(chk_normalize_, Gtk::PACK_SHRINK, 5);
    vb_a->pack_start(chk_bw_, Gtk::PACK_SHRINK, 5);
    vb_a->pack_start(chk_depth_, Gtk::PACK_SHRINK, 5);
    
    lbl_setup_hint_.set_line_wrap(true);
    vb_a->pack_start(lbl_setup_hint_, Gtk::PACK_SHRINK);

    vb_a->pack_start(btn_record_, Gtk::PACK_SHRINK);
    vb_a->pack_start(btn_snapshot_, Gtk::PACK_SHRINK);
    vb_a->pack_start(btn_cap_, Gtk::PACK_SHRINK);
    vb_a->pack_start(btn_quit_, Gtk::PACK_SHRINK);

    f_act->add(*vb_a);
    left_panel_.pack_start(*f_act, Gtk::PACK_SHRINK, 5);

    main_box_.pack_start(left_panel_, Gtk::PACK_SHRINK);

    // ─── Main Video Feed (Kanan) ───
    main_box_.pack_start(camera_view_, Gtk::PACK_EXPAND_WIDGET);

    show_all_children();
    btn_start_calib_.hide();
    btn_next_step_.hide();
}

void FusionGUI::adj_exposure(double delta) {
    try {
        double val = std::stod(entry_exposure_.get_text());
        val = std::max(1.0, std::min(10.0, val + delta));
        std::ostringstream ss;
        ss << std::fixed << std::setprecision(1) << val;
        entry_exposure_.set_text(ss.str());
    } catch (...) {}
}

void FusionGUI::adj_alpha(double delta) {
    try {
        double val = std::stod(entry_alpha_.get_text());
        std::ostringstream ss;
        ss << std::fixed << std::setprecision(1) << (val + delta);
        entry_alpha_.set_text(ss.str());
    } catch (...) {}
}

void FusionGUI::adj_beta(double delta) {
    try {
        double val = std::stod(entry_beta_.get_text());
        std::ostringstream ss;
        ss << std::fixed << std::setprecision(1) << (val + delta);
        entry_beta_.set_text(ss.str());
    } catch (...) {}
}

void FusionGUI::adj_zoom(double delta) {
    try {
        double val = std::stod(entry_zoom_.get_text());
        val = std::max(0.1, val + delta);
        std::ostringstream ss;
        ss << std::fixed << std::setprecision(2) << val;
        entry_zoom_.set_text(ss.str());
    } catch (...) {}
}

void FusionGUI::connect_signals() {
    btn_exp_mm_.signal_clicked().connect([this]() { adj_exposure(-2.0); });
    btn_exp_m_.signal_clicked().connect([this]()  { adj_exposure(-0.5); });
    btn_exp_p_.signal_clicked().connect([this]()  { adj_exposure(0.5); });
    btn_exp_pp_.signal_clicked().connect([this]() { adj_exposure(2.0); });

    btn_apply_exp_.signal_clicked().connect([this]() {
        if (on_smart_exposure) {
            try { on_smart_exposure(std::stod(entry_exposure_.get_text())); } catch(...) {}
        }
    });

    btn_apply_anypoint_.signal_clicked().connect([this]() {
        if (on_apply_anypoint) {
            try {
                double a = std::stod(entry_alpha_.get_text());
                double b = std::stod(entry_beta_.get_text());
                double z = std::stod(entry_zoom_.get_text());
                on_apply_anypoint(a, b, z);
            } catch (...) {}
        }
    });

    btn_reset_anypoint_.signal_clicked().connect([this]() {
        entry_alpha_.set_text("0.0");
        entry_beta_.set_text("0.0");
        entry_zoom_.set_text("1.4");
        if (on_reset_anypoint) on_reset_anypoint();
    });

    btn_start_calib_.signal_clicked().connect([this]() { if (on_start_calib) on_start_calib(); });
    
    chk_normalize_.signal_toggled().connect([this]() {
        if (on_toggle_normalize) on_toggle_normalize(chk_normalize_.get_active());
    });
    
    chk_bw_.signal_toggled().connect([this]() {
        if (on_toggle_bw) on_toggle_bw(chk_bw_.get_active());
    });
    
    chk_depth_.signal_toggled().connect([this]() {
        if (on_toggle_depth) on_toggle_depth(chk_depth_.get_active());
    });

    btn_snapshot_.signal_clicked().connect([this]() { if (on_snapshot) on_snapshot(); });
    btn_quit_.signal_clicked().connect([this]() { close(); });

    btn_record_.signal_clicked().connect([this]() { if (on_queue_key) on_queue_key('r'); });
    btn_cap_.signal_clicked().connect([this]() { if (on_queue_key) on_queue_key('c'); });
    btn_next_step_.signal_clicked().connect([this]() { if (on_queue_key) on_queue_key(' '); });
}

Glib::RefPtr<Gdk::Pixbuf> FusionGUI::mat_to_pixbuf(const cv::Mat& frame) const {
    cv::Mat rgb;
    if (frame.channels() == 3) {
        cv::cvtColor(frame, rgb, cv::COLOR_BGR2RGB);
    } else if (frame.channels() == 1) {
        cv::cvtColor(frame, rgb, cv::COLOR_GRAY2RGB);
    } else {
        rgb = frame;
    }

    // Must clone data because Gdk::Pixbuf doesn't copy it when using create_from_data
    // For safety, we use deep copy to a vector or managed memory in production, 
    // but here we let OpenCV handle the Mat lifecycle since update_frame creates a local copy.
    // Wait, Gdk::Pixbuf requires data to stay alive. We must copy it.
    auto pb = Gdk::Pixbuf::create(Gdk::COLORSPACE_RGB, false, 8, rgb.cols, rgb.rows);
    
    int rowstride = pb->get_rowstride();
    guint8* pixels = pb->get_pixels();
    for (int y = 0; y < rgb.rows; ++y) {
        std::memcpy(pixels + y * rowstride, rgb.ptr(y), rgb.cols * 3);
    }
    
    return pb;
}

void FusionGUI::update_frame(const cv::Mat& frame) {
    if (frame.empty()) return;
    
    // Resize with INTER_AREA for high-quality downscale (similar to Python)
    cv::Mat display;
    int target_w = 960;
    if (frame.cols > target_w) {
        double scale = static_cast<double>(target_w) / frame.cols;
        int target_h = static_cast<int>(frame.rows * scale);
        cv::resize(frame, display, cv::Size(target_w, target_h), 0, 0, cv::INTER_AREA);
    } else {
        display = frame.clone();
    }
    
    auto pb = mat_to_pixbuf(display);
    camera_view_.set(pb);
}

void FusionGUI::set_status(const std::string& text) {
    lbl_status_ai_.set_text(text);
}

void FusionGUI::update_measurements(double height_cm, double distance_cm,
                                     double diameter_cm, double volume_ml) {
    (void)distance_cm;
    (void)diameter_cm;
    std::ostringstream ss;
    ss << std::fixed << std::setprecision(1);
    ss << "Height: " << height_cm << " cm | Vol: " << volume_ml << " mL";
    lbl_status_ai_.set_text(ss.str());
}

void FusionGUI::set_calib_mode(const std::string& mode) {
    lbl_status_calib_.set_text("Mode: " + mode);
}

bool FusionGUI::on_key_press_event(GdkEventKey* event) {
    if (event->keyval == GDK_KEY_q || event->keyval == GDK_KEY_Escape) {
        close();
        return true;
    }
    if (on_queue_key) {
        on_queue_key(event->keyval);
    }
    return Gtk::Window::on_key_press_event(event);
}

} // namespace fusion

#endif // HAS_GTKMM
