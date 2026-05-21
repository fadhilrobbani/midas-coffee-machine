import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

import cv2
# KRITIS: Matikan OpenCL — tidak thread-safe dengan multi-pipeline
# (Moildev remap + YOLO + GTK rendering) → SIGABRT / SIGSEGV.
cv2.ocl.setUseOpenCL(False)
import numpy as np
import time
import threading
import torch
import os
import sys
import json
import argparse

# ── Moildev import ──────────────────────────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_FUSION_DIR = os.path.abspath(os.path.join(_THIS_DIR, "..", "07_midas_aruco_fusion"))
if _FUSION_DIR not in sys.path:
    sys.path.insert(0, _FUSION_DIR)

try:
    from core.moil_undistorter import MoilUndistorter
    MOILDEV_AVAILABLE = True
    print("[MOIL] MoilUndistorter imported successfully.")
except ImportError as e:
    MOILDEV_AVAILABLE = False
    print(f"[MOIL] MoilUndistorter not available: {e}")
    print("[MOIL] Fisheye undistortion will be disabled.")

# Define CSS stylesheet for premium dark mode aesthetics
CSS_STYLE = """
window {
    background-color: #121212;
}

#main-box {
    background-color: #121212;
}

.sidebar {
    background-color: #1a1a1a;
    border-right: 1px solid #2d2d2d;
    padding: 18px;
}

.sidebar-title {
    font-size: 16px;
    font-weight: bold;
    color: #00bcf2;
    margin-bottom: 2px;
}

.sidebar-subtitle {
    font-size: 11px;
    color: #8a8a8a;
    margin-bottom: 20px;
}

.card {
    background-color: #222222;
    border: 1px solid #2d2d2d;
    border-radius: 8px;
    padding: 14px;
    margin-bottom: 14px;
}

.card-title {
    font-size: 11px;
    font-weight: bold;
    color: #8a8a8a;
    margin-bottom: 12px;
}

.input-label {
    font-size: 11px;
    color: #a0a0a0;
    margin-bottom: 6px;
}

.entry-source {
    background-color: #2d2d2d;
    color: #ffffff;
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    padding: 8px;
    font-family: monospace;
    font-size: 13px;
}

.entry-source:focus {
    border-color: #00bcf2;
}

.btn-action {
    background-color: #007acc;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 10px;
    font-weight: bold;
    font-size: 13px;
}

.btn-action:hover {
    background-color: #0098ff;
}

.btn-stop {
    background-color: #d83b01;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 10px;
    font-weight: bold;
    font-size: 13px;
}

.btn-stop:hover {
    background-color: #f7630c;
}

.stat-row {
    margin-bottom: 12px;
}

.stat-label {
    font-size: 10px;
    color: #8a8a8a;
}

.stat-value {
    font-size: 24px;
    font-weight: bold;
    color: #ffffff;
    font-family: monospace;
}

.pill-container {
    margin-top: 4px;
}

.pill-cup {
    background-color: rgba(0, 188, 242, 0.1);
    border: 1px solid #00bcf2;
    border-radius: 6px;
    padding: 10px;
}

.pill-liquid {
    background-color: rgba(247, 99, 12, 0.1);
    border: 1px solid #f7630c;
    border-radius: 6px;
    padding: 10px;
}

.pill-val {
    font-size: 28px;
    font-weight: bold;
    font-family: monospace;
}

.pill-val-cup {
    color: #00bcf2;
}

.pill-val-liquid {
    color: #f7630c;
}

.pill-lbl {
    font-size: 10px;
    font-weight: bold;
    color: #d4d4d4;
}

.status-badge-container {
    padding-top: 15px;
    border-top: 1px solid #2d2d2d;
}

.status-pill {
    padding: 8px 12px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: bold;
    color: #ffffff;
}

.status-live {
    background-color: #107c41;
}

.status-stopped {
    background-color: #4b4b4b;
}

.status-connecting {
    background-color: #b75c00;
}

.status-error {
    background-color: #a80000;
}

#video-viewport {
    background-color: #0a0a0a;
    border-radius: 8px;
    margin: 18px;
    border: 1px solid #2d2d2d;
}
"""

class VideoWorker(threading.Thread):
    """
    Background worker thread that connects to camera/video source,
    runs YOLOv8 object detection, and formats frames for the GTK UI.
    """
    def __init__(self, model_path, source, conf=0.25, iou=0.45, yolo_enabled=True,
                 full_threshold=0.85,
                 moil_undistorter=None, cap_width=1280, cap_height=720,
                 callback=None, error_callback=None):
        super().__init__()
        self.model_path = model_path
        self.source = source
        self.conf = conf
        self.iou = iou
        self.yolo_enabled = yolo_enabled
        self.full_threshold = full_threshold
        self.moil_undistorter = moil_undistorter
        self.cap_width = cap_width
        self.cap_height = cap_height
        self.callback = callback
        self.error_callback = error_callback
        
        self.running = True
        self.model = None
        self.cap = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
    def run(self):
        # Load YOLO model inside the thread to avoid blocking GUI startup
        try:
            from ultralytics import YOLO
            self.model = YOLO(self.model_path)
            print(f"[YOLO] Model loaded successfully on device: {self.device}")
        except Exception as e:
            print("[YOLO] Error loading model:", e)
            if self.error_callback:
                GLib.idle_add(self.error_callback, f"Failed to load YOLO model: {e}")
            return
            
        parsed_source = self.source
        try:
            parsed_source = int(self.source)
        except ValueError:
            pass
            
        self.cap = cv2.VideoCapture(parsed_source)
        if not self.cap.isOpened():
            print(f"[Worker] Failed to open video source: {self.source}")
            if self.error_callback:
                GLib.idle_add(self.error_callback, f"Failed to open video source: {self.source}")
            return
        
        # Set camera resolution
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cap_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cap_height)
        self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[CAM] Resolution: {actual_w}x{actual_h} (requested {self.cap_width}x{self.cap_height})")

        last_frame_time = time.time()
        
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                # If it's a video file, loop it
                if isinstance(parsed_source, str) and parsed_source.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    time.sleep(0.03)
                    continue
                else:
                    print("[Worker] Failed to read frame or feed ended.")
                    if self.error_callback:
                        GLib.idle_add(self.error_callback, "Camera disconnected or video source ended.")
                    break
            
            # Force resize if camera hardware ignores requested resolution
            if frame.shape[1] != self.cap_width or frame.shape[0] != self.cap_height:
                frame = cv2.resize(frame, (self.cap_width, self.cap_height), interpolation=cv2.INTER_LINEAR)

            # ── Moildev fisheye undistortion ──────────────────────────────
            if self.moil_undistorter is not None:
                frame = self.moil_undistorter.undistort(frame)

            # FPS Calculation
            curr_time = time.time()
            dt = curr_time - last_frame_time
            last_frame_time = curr_time
            fps = 1.0 / dt if dt > 0 else 0.0
            
            # Run YOLO inference
            inf_time_ms = 0.0
            counts = {0: 0, 1: 0} # 0: cup_rim, 1: liquid
            
            if self.yolo_enabled and self.model is not None:
                t0 = time.time()
                results = self.model.predict(
                    source=frame,
                    conf=self.conf,
                    iou=self.iou,
                    verbose=False,
                    device=self.device
                )
                inf_time_ms = (time.time() - t0) * 1000.0
                
                if len(results) > 0:
                    result = results[0]
                    boxes = result.boxes
                    cup_rim_boxes = []
                    liquid_boxes = []
                    
                    for box in boxes:
                        cls_id = int(box.cls[0].item())
                        conf_val = float(box.conf[0].item())
                        
                        if cls_id in counts:
                            counts[cls_id] += 1
                            
                        # Coordinates
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        
                        if cls_id == 0:
                            cup_rim_boxes.append((x1, y1, x2, y2))
                            cls_name = "Cup Rim"
                            color = (255, 188, 0) # Sky Blue/Cyan
                        elif cls_id == 1:
                            liquid_boxes.append((x1, y1, x2, y2))
                            cls_name = "Liquid"
                            color = (0, 140, 255) # Orange
                        else:
                            cls_name = f"Class {cls_id}"
                            color = (0, 255, 0)
                            
                        # Draw bounding box
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        
                        # Draw label tag
                        label = f"{cls_name} {conf_val:.2f}"
                        (w_txt, h_txt), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                        text_y = max(y1, h_txt + 5)
                        cv2.rectangle(frame, (x1 - 1, text_y - h_txt - 5), (x1 + w_txt + 5, text_y + 4), color, -1)
                        cv2.putText(frame, label, (x1 + 2, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

                    # Check for "Coffee is Full" condition
                    is_full = False
                    for (lx1, ly1, lx2, ly2) in liquid_boxes:
                        lw = lx2 - lx1
                        # Find overlapping cup rim
                        for (cx1, cy1, cx2, cy2) in cup_rim_boxes:
                            cw = cx2 - cx1
                            # Check if liquid center is inside cup x-boundaries
                            lcx = (lx1 + lx2) / 2
                            if cx1 <= lcx <= cx2:
                                if cw > 0 and (lw / cw) >= self.full_threshold:
                                    is_full = True
                                    break
                        if is_full:
                            break
                            
                    if is_full:
                        # Draw warning text on the frame
                        warn_label = "WARNING: COFFEE IS FULL"
                        (w_w, h_w), _ = cv2.getTextSize(warn_label, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)
                        frame_h, frame_w = frame.shape[:2]
                        cx, cy = (frame_w - w_w) // 2, int(frame_h * 0.1)  # Top center
                        # Background for warning
                        cv2.rectangle(frame, (cx - 10, cy - h_w - 10), (cx + w_w + 10, cy + 10), (0, 0, 255), -1)
                        cv2.putText(frame, warn_label, (cx, cy), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3, cv2.LINE_AA)
            
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, c = rgb_frame.shape
            
            try:
                # Wrap numpy array bytes into GLib.Bytes to avoid GC issues
                bytes_data = GLib.Bytes.new(rgb_frame.tobytes())
                pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
                    bytes_data,
                    GdkPixbuf.Colorspace.RGB,
                    False,
                    8,
                    w,
                    h,
                    w * c
                )
                
                stats = {
                    "fps": fps,
                    "inf_time": inf_time_ms,
                    "cup_rim_count": counts.get(0, 0),
                    "liquid_count": counts.get(1, 0)
                }
                
                # Push frame to GTK main loop thread-safely
                GLib.idle_add(self.callback, pixbuf, stats)
            except Exception as e:
                print("[Worker] Error creating pixbuf:", e)
                
            # Control loop speed slightly (limit to ~120 fps max)
            time.sleep(0.005)
            
    def stop(self):
        self.running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()


class CoffeeMonitorApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="Coffee Machine AI Monitor")
        self.set_default_size(1200, 750)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("destroy", self.on_destroy)
        
        # Application settings and state
        self.current_worker = None
        self.target_width = 640
        self.target_height = 480
        self.latest_pixbuf = None
        self.moil_undistorter = None
        
        # Load CSS provider
        self.load_css()
        
        # Main Layout: Sidebar & Video Viewport
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        main_box.set_name("main-box")
        self.add(main_box)
        
        # ----------------- SIDEBAR (scrollable) -----------------
        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_size_request(330, -1)
        
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.get_style_context().add_class("sidebar")
        sidebar_scroll.add(sidebar)
        main_box.pack_start(sidebar_scroll, False, False, 0)
        
        # App Title Group
        lbl_title = Gtk.Label()
        lbl_title.set_markup("<span font_desc='System-UI Bold 18' color='#00bcf2'>ARANUS COFFEE AI</span>")
        lbl_title.set_halign(Gtk.Align.START)
        lbl_title.get_style_context().add_class("sidebar-title")
        sidebar.pack_start(lbl_title, False, False, 0)
        
        lbl_subtitle = Gtk.Label(label="Coffee Machine Liquid Detection Monitor")
        lbl_subtitle.set_halign(Gtk.Align.START)
        lbl_subtitle.get_style_context().add_class("sidebar-subtitle")
        sidebar.pack_start(lbl_subtitle, False, False, 0)
        
        # 1. Source Settings Card
        card_src = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card_src.get_style_context().add_class("card")
        sidebar.pack_start(card_src, False, False, 0)
        
        lbl_src_title = Gtk.Label(label="Source Configuration")
        lbl_src_title.set_halign(Gtk.Align.START)
        lbl_src_title.get_style_context().add_class("card-title")
        card_src.pack_start(lbl_src_title, False, False, 0)
        
        lbl_src_input = Gtk.Label(label="Camera Index or Video File:")
        lbl_src_input.set_halign(Gtk.Align.START)
        lbl_src_input.get_style_context().add_class("input-label")
        card_src.pack_start(lbl_src_input, False, False, 0)
        
        self.entry_source = Gtk.Entry()
        self.entry_source.set_text("0")
        self.entry_source.get_style_context().add_class("entry-source")
        card_src.pack_start(self.entry_source, False, False, 0)
        
        self.btn_toggle_cam = Gtk.Button(label="START CAMERA")
        self.btn_toggle_cam.get_style_context().add_class("btn-action")
        self.btn_toggle_cam.connect("clicked", self.on_btn_toggle_cam_clicked)
        card_src.pack_start(self.btn_toggle_cam, False, False, 4)
        
        # 2. Model Settings Card
        card_model = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card_model.get_style_context().add_class("card")
        sidebar.pack_start(card_model, False, False, 0)
        
        lbl_model_title = Gtk.Label(label="Model Optimization")
        lbl_model_title.set_halign(Gtk.Align.START)
        lbl_model_title.get_style_context().add_class("card-title")
        card_model.pack_start(lbl_model_title, False, False, 0)
        
        # YOLO Switch
        yolo_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        lbl_yolo_sw = Gtk.Label(label="Enable YOLO Inference")
        lbl_yolo_sw.set_halign(Gtk.Align.START)
        lbl_yolo_sw.get_style_context().add_class("input-label")
        yolo_box.pack_start(lbl_yolo_sw, True, True, 0)
        
        self.switch_yolo = Gtk.Switch()
        self.switch_yolo.set_active(True)
        self.switch_yolo.connect("state-set", self.on_yolo_toggled)
        yolo_box.pack_end(self.switch_yolo, False, False, 0)
        card_model.pack_start(yolo_box, False, False, 2)
        
        # Conf Slider
        self.lbl_conf = Gtk.Label(label="Confidence Threshold: 0.25")
        self.lbl_conf.set_halign(Gtk.Align.START)
        self.lbl_conf.get_style_context().add_class("input-label")
        card_model.pack_start(self.lbl_conf, False, False, 0)
        
        self.slider_conf = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.05, 1.0, 0.05)
        self.slider_conf.set_value(0.25)
        self.slider_conf.connect("value-changed", self.on_conf_changed)
        card_model.pack_start(self.slider_conf, False, False, 0)
        
        # IoU Slider
        self.lbl_iou = Gtk.Label(label="NMS IoU Threshold: 0.45")
        self.lbl_iou.set_halign(Gtk.Align.START)
        self.lbl_iou.get_style_context().add_class("input-label")
        card_model.pack_start(self.lbl_iou, False, False, 0)
        
        self.slider_iou = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.05, 1.0, 0.05)
        self.slider_iou.set_value(0.45)
        self.slider_iou.connect("value-changed", self.on_iou_changed)
        card_model.pack_start(self.slider_iou, False, False, 0)
        
        # Liquid Full Threshold Slider
        self.lbl_full_thresh = Gtk.Label(label="Liquid Full Threshold: 85%")
        self.lbl_full_thresh.set_halign(Gtk.Align.START)
        self.lbl_full_thresh.get_style_context().add_class("input-label")
        card_model.pack_start(self.lbl_full_thresh, False, False, 0)
        
        self.slider_full_thresh = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.1, 1.0, 0.05)
        self.slider_full_thresh.set_value(0.85)
        self.slider_full_thresh.connect("value-changed", self.on_full_thresh_changed)
        card_model.pack_start(self.slider_full_thresh, False, False, 0)
        
        # 2.5 Fisheye Correction Card (Moildev)
        card_moil = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card_moil.get_style_context().add_class("card")
        sidebar.pack_start(card_moil, False, False, 0)
        
        lbl_moil_title = Gtk.Label(label="Fisheye Correction (Moildev)")
        lbl_moil_title.set_halign(Gtk.Align.START)
        lbl_moil_title.get_style_context().add_class("card-title")
        card_moil.pack_start(lbl_moil_title, False, False, 0)
        
        # Fisheye Enable Switch
        moil_sw_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        lbl_moil_sw = Gtk.Label(label="Enable Fisheye Remap")
        lbl_moil_sw.set_halign(Gtk.Align.START)
        lbl_moil_sw.get_style_context().add_class("input-label")
        moil_sw_box.pack_start(lbl_moil_sw, True, True, 0)
        self.switch_moil = Gtk.Switch()
        self.switch_moil.set_active(False)
        self.switch_moil.set_sensitive(MOILDEV_AVAILABLE)
        moil_sw_box.pack_end(self.switch_moil, False, False, 0)
        card_moil.pack_start(moil_sw_box, False, False, 2)

        if not MOILDEV_AVAILABLE:
            lbl_moil_warn = Gtk.Label(label="⚠ Moildev not installed")
            lbl_moil_warn.set_halign(Gtk.Align.START)
            lbl_moil_warn.get_style_context().add_class("input-label")
            card_moil.pack_start(lbl_moil_warn, False, False, 0)
        
        # Camera Name Entry
        lbl_cam_name = Gtk.Label(label="Camera Profile Name:")
        lbl_cam_name.set_halign(Gtk.Align.START)
        lbl_cam_name.get_style_context().add_class("input-label")
        card_moil.pack_start(lbl_cam_name, False, False, 0)
        
        self.entry_moil_cam = Gtk.Entry()
        self.entry_moil_cam.set_text("syue_7730v1_6")
        self.entry_moil_cam.get_style_context().add_class("entry-source")
        card_moil.pack_start(self.entry_moil_cam, False, False, 0)

        # Pitch Slider
        self.lbl_moil_pitch = Gtk.Label(label="Pitch: 0.0°")
        self.lbl_moil_pitch.set_halign(Gtk.Align.START)
        self.lbl_moil_pitch.get_style_context().add_class("input-label")
        card_moil.pack_start(self.lbl_moil_pitch, False, False, 0)
        self.slider_moil_pitch = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -90.0, 90.0, 1.0)
        self.slider_moil_pitch.set_value(0.0)
        self.slider_moil_pitch.connect("value-changed", self.on_moil_param_changed)
        card_moil.pack_start(self.slider_moil_pitch, False, False, 0)

        # Yaw Slider
        self.lbl_moil_yaw = Gtk.Label(label="Yaw: 0.0°")
        self.lbl_moil_yaw.set_halign(Gtk.Align.START)
        self.lbl_moil_yaw.get_style_context().add_class("input-label")
        card_moil.pack_start(self.lbl_moil_yaw, False, False, 0)
        self.slider_moil_yaw = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -90.0, 90.0, 1.0)
        self.slider_moil_yaw.set_value(0.0)
        self.slider_moil_yaw.connect("value-changed", self.on_moil_param_changed)
        card_moil.pack_start(self.slider_moil_yaw, False, False, 0)

        # Roll Slider
        self.lbl_moil_roll = Gtk.Label(label="Roll: 0.0°")
        self.lbl_moil_roll.set_halign(Gtk.Align.START)
        self.lbl_moil_roll.get_style_context().add_class("input-label")
        card_moil.pack_start(self.lbl_moil_roll, False, False, 0)
        self.slider_moil_roll = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -180.0, 180.0, 1.0)
        self.slider_moil_roll.set_value(0.0)
        self.slider_moil_roll.connect("value-changed", self.on_moil_param_changed)
        card_moil.pack_start(self.slider_moil_roll, False, False, 0)

        # Zoom Slider
        self.lbl_moil_zoom = Gtk.Label(label="Zoom: 1.4x")
        self.lbl_moil_zoom.set_halign(Gtk.Align.START)
        self.lbl_moil_zoom.get_style_context().add_class("input-label")
        card_moil.pack_start(self.lbl_moil_zoom, False, False, 0)
        self.slider_moil_zoom = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1.0, 10.0, 0.1)
        self.slider_moil_zoom.set_value(1.4)
        self.slider_moil_zoom.connect("value-changed", self.on_moil_param_changed)
        card_moil.pack_start(self.slider_moil_zoom, False, False, 0)
        
        # 3. Analytics Card
        card_stats = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card_stats.get_style_context().add_class("card")
        sidebar.pack_start(card_stats, False, False, 0)
        
        lbl_stats_title = Gtk.Label(label="Live Diagnostics")
        lbl_stats_title.set_halign(Gtk.Align.START)
        lbl_stats_title.get_style_context().add_class("card-title")
        card_stats.pack_start(lbl_stats_title, False, False, 0)
        
        # FPS and Latency Row
        diag_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        card_stats.pack_start(diag_row, False, False, 0)
        
        # FPS display block
        fps_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        diag_row.pack_start(fps_box, True, True, 0)
        lbl_fps_label = Gtk.Label(label="FPS")
        lbl_fps_label.set_halign(Gtk.Align.START)
        lbl_fps_label.get_style_context().add_class("stat-label")
        fps_box.pack_start(lbl_fps_label, False, False, 0)
        self.val_fps = Gtk.Label(label="---")
        self.val_fps.set_halign(Gtk.Align.START)
        self.val_fps.get_style_context().add_class("stat-value")
        fps_box.pack_start(self.val_fps, False, False, 0)
        
        # Latency display block
        lat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        diag_row.pack_start(lat_box, True, True, 0)
        lbl_lat_label = Gtk.Label(label="Inference Delay")
        lbl_lat_label.set_halign(Gtk.Align.START)
        lbl_lat_label.get_style_context().add_class("stat-label")
        lat_box.pack_start(lbl_lat_label, False, False, 0)
        self.val_latency = Gtk.Label(label="---")
        self.val_latency.set_halign(Gtk.Align.START)
        self.val_latency.get_style_context().add_class("stat-value")
        lat_box.pack_start(self.val_latency, False, False, 0)
        
        # Class detection pills container
        pill_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        pill_row.get_style_context().add_class("pill-container")
        card_stats.pack_start(pill_row, False, False, 4)
        
        # Cup Rim counter card
        pill_cup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        pill_cup.get_style_context().add_class("pill-cup")
        pill_row.pack_start(pill_cup, True, True, 0)
        self.val_cup_rim = Gtk.Label(label="0")
        self.val_cup_rim.get_style_context().add_class("pill-val")
        self.val_cup_rim.get_style_context().add_class("pill-val-cup")
        pill_cup.pack_start(self.val_cup_rim, False, False, 0)
        lbl_cup = Gtk.Label(label="Cup Rim Detections")
        lbl_cup.get_style_context().add_class("pill-lbl")
        pill_cup.pack_start(lbl_cup, False, False, 0)
        
        # Liquid counter card
        pill_liq = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        pill_liq.get_style_context().add_class("pill-liquid")
        pill_row.pack_start(pill_liq, True, True, 0)
        self.val_liquid = Gtk.Label(label="0")
        self.val_liquid.get_style_context().add_class("pill-val")
        self.val_liquid.get_style_context().add_class("pill-val-liquid")
        pill_liq.pack_start(self.val_liquid, False, False, 0)
        lbl_liq = Gtk.Label(label="Liquid Detections")
        lbl_liq.get_style_context().add_class("pill-lbl")
        pill_liq.pack_start(lbl_liq, False, False, 0)
        
        # Bottom Status Indicator
        status_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        status_container.get_style_context().add_class("status-badge-container")
        sidebar.pack_end(status_container, False, False, 0)
        
        lbl_status_badge_hdr = Gtk.Label(label="System Status")
        lbl_status_badge_hdr.set_halign(Gtk.Align.START)
        lbl_status_badge_hdr.get_style_context().add_class("input-label")
        status_container.pack_start(lbl_status_badge_hdr, False, False, 0)
        
        self.status_badge = Gtk.Label(label="OFFLINE")
        self.status_badge.get_style_context().add_class("status-pill")
        self.set_badge_style("status-stopped")
        status_container.pack_start(self.status_badge, False, False, 0)
        
        # ----------------- VIDEO PANEL -----------------
        self.video_viewport = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.video_viewport.set_name("video-viewport")
        main_box.pack_start(self.video_viewport, True, True, 0)
        
        # Gunakan DrawingArea bukan Gtk.Image.
        # DrawingArea tidak pernah melaporkan natural-size dari konten yang digambar
        # sehingga parent container TIDAK akan grow mengikuti pixbuf → tidak ada grow loop.
        self.video_draw = Gtk.DrawingArea()
        self.video_draw.connect("draw", self.on_draw)
        self.video_viewport.pack_start(self.video_draw, True, True, 0)
        
        # Show all widgets
        self.show_all()
        
    def load_css(self):
        """Load the CSS rules into GTK styling provider."""
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(CSS_STYLE.encode())
        screen = Gdk.Screen.get_default()
        Gtk.StyleContext.add_provider_for_screen(
            screen,
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        
    def set_badge_style(self, style_class):
        """Updates the status badge color styles."""
        context = self.status_badge.get_style_context()
        for cls in ["status-live", "status-stopped", "status-connecting", "status-error"]:
            if context.has_class(cls):
                context.remove_class(cls)
        context.add_class(style_class)
        
    def on_video_size_allocate(self, widget, allocation):
        pass  # tidak digunakan lagi — DrawingArea menangani sizing sendiri
        
            
    def generate_placeholder(self, w, h):
        """Generates a clean vector-style OpenCV placeholder image when video is stopped."""
        # Boundaries check
        w = max(w, 200)
        h = max(h, 150)
        
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        
        # Background design (grid overlay)
        cv2.rectangle(frame, (10, 10), (w - 10, h - 10), (25, 25, 25), -1)
        # Grid lines
        for y in range(40, h - 10, 40):
            cv2.line(frame, (10, y), (w - 10, y), (32, 32, 32), 1)
        for x in range(40, w - 10, 40):
            cv2.line(frame, (x, 10), (x, h - 10), (32, 32, 32), 1)
            
        # Draw camera outline in center
        center_x, center_y = w // 2, h // 2
        # Camera body
        cv2.rectangle(frame, (center_x - 35, center_y - 25), (center_x + 35, center_y + 25), (60, 60, 60), 2, cv2.LINE_AA)
        cv2.rectangle(frame, (center_x - 15, center_y - 35), (center_x + 15, center_y - 24), (60, 60, 60), 2, cv2.LINE_AA)
        # Lens
        cv2.circle(frame, (center_x, center_y), 15, (60, 60, 60), 2, cv2.LINE_AA)
        cv2.circle(frame, (center_x, center_y), 5, (0, 188, 242), -1, cv2.LINE_AA) # Cyan status light
        
        text1 = "ARANUS COFFEE MONITOR"
        text2 = "CAMERA FEED INACTIVE"
        text3 = "Enter camera index or file path, then click Start"
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        s1, _ = cv2.getTextSize(text1, font, 0.7, 2)
        s2, _ = cv2.getTextSize(text2, font, 0.5, 1)
        s3, _ = cv2.getTextSize(text3, font, 0.45, 1)
        
        # Put styled texts
        cv2.putText(frame, text1, (center_x - s1[0] // 2, center_y + 60), font, 0.7, (242, 188, 0), 2, cv2.LINE_AA)
        cv2.putText(frame, text2, (center_x - s2[0] // 2, center_y + 85), font, 0.5, (160, 160, 160), 1, cv2.LINE_AA)
        cv2.putText(frame, text3, (center_x - s3[0] // 2, center_y + 110), font, 0.45, (100, 100, 100), 1, cv2.LINE_AA)
        
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Convert to Pixbuf
        bytes_data = GLib.Bytes.new(rgb.tobytes())
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
            bytes_data,
            GdkPixbuf.Colorspace.RGB,
            False,
            8,
            w,
            h,
            w * 3
        )
        return pixbuf
        
    def start_camera(self):
        """Instantiates and launches the background inference thread."""
        source_str = self.entry_source.get_text().strip()
        if not source_str:
            self.show_error_dialog("Please specify a valid camera index (e.g. 0) or a path to a video file.")
            return
            
        self.entry_source.set_sensitive(False)
        self.status_badge.set_text("CONNECTING")
        self.set_badge_style("status-connecting")
        
        self.btn_toggle_cam.set_label("STOP CAMERA")
        # Swap styles to stop button
        self.btn_toggle_cam.get_style_context().remove_class("btn-action")
        self.btn_toggle_cam.get_style_context().add_class("btn-stop")
        
        # Reset counters/displays
        self.val_fps.set_text("---")
        self.val_latency.set_text("---")
        self.val_cup_rim.set_text("0")
        self.val_liquid.set_text("0")
        
        # ── Moildev initialization ────────────────────────────────────────
        self.moil_undistorter = None
        cap_w, cap_h = 1280, 720
        
        if MOILDEV_AVAILABLE and self.switch_moil.get_active():
            cam_name = self.entry_moil_cam.get_text().strip()
            json_path = os.path.join(_THIS_DIR, "camera_parameters.json")
            moil_pitch = self.slider_moil_pitch.get_value()
            moil_yaw = self.slider_moil_yaw.get_value()
            moil_roll = self.slider_moil_roll.get_value()
            moil_zoom = self.slider_moil_zoom.get_value()
            
            # Fisheye cameras typically use high resolution
            cap_w, cap_h = 2592, 1944
            
            try:
                self.moil_undistorter = MoilUndistorter(
                    json_path=json_path,
                    camera_name=cam_name,
                    pitch=moil_pitch,
                    yaw=moil_yaw,
                    roll=moil_roll,
                    zoom=moil_zoom,
                    mode=2,
                    use_opencl=False,
                    frame_width=cap_w,
                    frame_height=cap_h,
                )
                print(f"[MOIL] Undistorter initialized: {self.moil_undistorter}")
            except Exception as e:
                print(f"[MOIL] Error initializing MoilUndistorter: {e}")
                self.show_error_dialog(f"Moildev init error: {e}")
                self.moil_undistorter = None
        
        self.current_worker = VideoWorker(
            model_path="best.pt",
            source=source_str,
            conf=self.slider_conf.get_value(),
            iou=self.slider_iou.get_value(),
            yolo_enabled=self.switch_yolo.get_active(),
            full_threshold=self.slider_full_thresh.get_value(),
            moil_undistorter=self.moil_undistorter,
            cap_width=cap_w,
            cap_height=cap_h,
            callback=self.on_frame_received,
            error_callback=self.on_worker_error
        )
        self.current_worker.start()
        
    def stop_camera(self):
        """Signals background thread to terminate and cleans up resources."""
        if self.current_worker:
            self.current_worker.stop()
            # Do not block the main UI thread with join; let the GC and thread natural loop exit handle it.
            self.current_worker = None
            
        self.entry_source.set_sensitive(True)
        self.status_badge.set_text("OFFLINE")
        self.set_badge_style("status-stopped")
        
        self.btn_toggle_cam.set_label("START CAMERA")
        # Swap styles back to action button
        self.btn_toggle_cam.get_style_context().remove_class("btn-stop")
        self.btn_toggle_cam.get_style_context().add_class("btn-action")
        
        self.val_fps.set_text("---")
        self.val_latency.set_text("---")
        self.val_cup_rim.set_text("0")
        self.val_liquid.set_text("0")
        
        self.latest_pixbuf = None
        self.video_draw.queue_draw()  # trigger on_draw dengan pixbuf=None → placeholder
        
    def on_btn_toggle_cam_clicked(self, button):
        """Button click handler to toggle camera state."""
        if self.current_worker is None:
            self.start_camera()
        else:
            self.stop_camera()
            
    def on_yolo_toggled(self, switch, state):
        """Toggle to turn YOLO object detection overlay on/off."""
        if self.current_worker:
            self.current_worker.yolo_enabled = state
        return False
        
    def on_conf_changed(self, scale):
        """Callback for confidence threshold slider."""
        val = scale.get_value()
        self.lbl_conf.set_text(f"Confidence Threshold: {val:.2f}")
        if self.current_worker:
            self.current_worker.conf = val
            
    def on_iou_changed(self, scale):
        """Callback for IoU Non-Max Suppression threshold slider."""
        val = scale.get_value()
        self.lbl_iou.set_text(f"NMS IoU Threshold: {val:.2f}")
        if self.current_worker:
            self.current_worker.iou = val
            
    def on_full_thresh_changed(self, scale):
        """Callback for Liquid Full Threshold slider."""
        val = scale.get_value()
        self.lbl_full_thresh.set_text(f"Liquid Full Threshold: {int(val * 100)}%")
        if self.current_worker:
            self.current_worker.full_threshold = val
    
    def on_moil_param_changed(self, scale):
        """Callback for Moildev anypoint parameter sliders (pitch/yaw/roll/zoom).
        Updates labels and live-updates undistorter maps if running."""
        pitch = self.slider_moil_pitch.get_value()
        yaw = self.slider_moil_yaw.get_value()
        roll = self.slider_moil_roll.get_value()
        zoom = self.slider_moil_zoom.get_value()
        
        self.lbl_moil_pitch.set_text(f"Pitch: {pitch:.1f}°")
        self.lbl_moil_yaw.set_text(f"Yaw: {yaw:.1f}°")
        self.lbl_moil_roll.set_text(f"Roll: {roll:.1f}°")
        self.lbl_moil_zoom.set_text(f"Zoom: {zoom:.1f}x")
        
        # Live update maps if undistorter is active
        if self.moil_undistorter is not None:
            self.moil_undistorter.update_maps(
                pitch=pitch, yaw=yaw, roll=roll, zoom=zoom
            )
            
    def on_frame_received(self, pixbuf, stats):
        """Called from worker thread to push newly annotated frame and live stats."""
        # Ensure we are still connected to the same active worker
        if self.current_worker is None:
            return False
            
        self.render_frame(pixbuf)
        
        # Update live dashboard stats
        self.val_fps.set_text(f"{stats['fps']:.1f}")
        
        if self.switch_yolo.get_active():
            self.val_latency.set_text(f"{stats['inf_time']:.1f} ms")
            self.val_cup_rim.set_text(str(stats['cup_rim_count']))
            self.val_liquid.set_text(str(stats['liquid_count']))
        else:
            self.val_latency.set_text("Disabled")
            self.val_cup_rim.set_text("---")
            self.val_liquid.set_text("---")
            
        if self.status_badge.get_text() != "LIVE":
            self.status_badge.set_text("LIVE")
            self.set_badge_style("status-live")
            
        return False # False stops GLib idle timer from repeating (worker pushes new idles continuously)
        
    def on_draw(self, widget, cr):
        """Cairo draw callback untuk DrawingArea — menggambar pixbuf scale-to-fit.
        Dipanggil oleh GTK setiap kali widget perlu di-repaint.
        Ukuran widget TIDAK berubah akibat menggambar — tidak ada grow loop."""
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()

        pixbuf = self.latest_pixbuf

        if pixbuf is None:
            # Gambar placeholder dark background dengan teks
            cr.set_source_rgb(0.04, 0.04, 0.04)
            cr.paint()
            cr.set_source_rgb(0.24, 0.24, 0.24)
            cr.set_font_size(max(14, w // 30))
            msg = "CAMERA FEED INACTIVE"
            ext = cr.text_extents(msg)
            cr.move_to((w - ext.width) / 2, h / 2)
            cr.show_text(msg)
            return False

        # Scale-to-fit (letterbox) dengan aspect ratio terjaga
        pb_w = pixbuf.get_width()
        pb_h = pixbuf.get_height()
        if pb_w <= 0 or pb_h <= 0:
            return False

        scale = min(w / pb_w, h / pb_h)
        dst_w = int(pb_w * scale)
        dst_h = int(pb_h * scale)
        x_off = (w - dst_w) // 2
        y_off = (h - dst_h) // 2

        # Scale pixbuf dan blit ke Cairo context
        if dst_w > 1 and dst_h > 1:
            scaled = pixbuf.scale_simple(dst_w, dst_h, GdkPixbuf.InterpType.BILINEAR)
            Gdk.cairo_set_source_pixbuf(cr, scaled, x_off, y_off)
            cr.paint()

        return False

    def render_frame(self, pixbuf):
        """Minta GTK untuk menjadwalkan repaint DrawingArea dengan pixbuf terbaru.
        TIDAK mengubah ukuran widget — hanya queue_draw untuk trigger on_draw."""
        self.latest_pixbuf = pixbuf
        self.video_draw.queue_draw()
            
    def on_worker_error(self, message):
        """Handles worker thread errors cleanly by notifying user and resetting."""
        self.stop_camera()
        self.status_badge.set_text("ERROR")
        self.set_badge_style("status-error")
        self.show_error_dialog(message)
        return False
        
    def show_error_dialog(self, message):
        """Displays error window."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Camera / Model Error"
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()
        
    def on_destroy(self, widget):
        """Callback on main window close."""
        self.stop_camera()
        Gtk.main_quit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Coffee Machine AI Monitor with YOLO + Moildev")
    ap.add_argument("--source",      type=str,   default="0",     help="Camera index or video file path (default: 0)")
    ap.add_argument("--conf",        type=float, default=0.25,    help="YOLO confidence threshold (default: 0.25)")
    ap.add_argument("--iou",         type=float, default=0.45,    help="YOLO NMS IoU threshold (default: 0.45)")
    ap.add_argument("--fisheye",     action="store_true",         help="Enable Moildev fisheye correction at startup")
    ap.add_argument("--moil-camera-name", type=str, default="syue_7730v1_6",
                    help="Moildev camera profile name (default: syue_7730v1_6)")
    ap.add_argument("--moil-pitch",  type=float, default=0.0,     help="Moildev pitch in degrees (default: 0.0)")
    ap.add_argument("--moil-yaw",    type=float, default=0.0,     help="Moildev yaw in degrees (default: 0.0)")
    ap.add_argument("--moil-roll",   type=float, default=0.0,     help="Moildev roll in degrees (default: 0.0)")
    ap.add_argument("--moil-zoom",   type=float, default=1.4,     help="Moildev zoom factor (default: 1.4)")
    cli_args = ap.parse_args()

    # Initialize the app
    app = CoffeeMonitorApp()
    
    # Apply CLI arguments to UI widgets
    app.entry_source.set_text(cli_args.source)
    app.slider_conf.set_value(cli_args.conf)
    app.slider_iou.set_value(cli_args.iou)
    
    if cli_args.fisheye and MOILDEV_AVAILABLE:
        app.switch_moil.set_active(True)
    app.entry_moil_cam.set_text(cli_args.moil_camera_name)
    app.slider_moil_pitch.set_value(cli_args.moil_pitch)
    app.slider_moil_yaw.set_value(cli_args.moil_yaw)
    app.slider_moil_roll.set_value(cli_args.moil_roll)
    app.slider_moil_zoom.set_value(cli_args.moil_zoom)
    
    # Run the GTK main loop
    Gtk.main()
