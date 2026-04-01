import os
import sys
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
import cv2
import yaml
import numpy as np
import time

# Ensure project root is in path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from midas_volumecup.depth import MidasDepthEstimator
from midas_volumecup.detector import YoloDetector
from midas_volumecup.camera_config import CameraConfig
from midas_volumecup.volume_math import calculate_z_rim_alpha, calculate_volume

class DebugRunnerWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="MiDaS Volume Debugger (Rim Analysis)")
        self.set_default_size(1200, 700)
        self.connect("destroy", self.on_destroy)
        
        self.cap = None
        self.depth_estimator = None
        self.detector = None
        self.running = False
        
        # UI State
        self.setup_ui()
        self.load_config()
        
        # Load models in a one-time background thread so the UI doesn't freeze at start
        import threading
        self.lbl_status.set_text("Loading AI Models... Please wait.")
        threading.Thread(target=self.init_ai_models, daemon=True).start()

    def init_ai_models(self):
        self.depth_estimator = MidasDepthEstimator()
        self.detector = YoloDetector()
        GLib.idle_add(self.lbl_status.set_text, "Models Ready. Click Start.")
        GLib.idle_add(self.btn_start.set_sensitive, True)

    def setup_ui(self):
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.add(hbox)
        vbox_ctrl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox_ctrl.set_border_width(10)
        vbox_ctrl.set_size_request(320, -1)
        
        frame_vars = Gtk.Frame(label="Manual Testing Variables")
        vbox_vars = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox_vars.set_border_width(5)
        self.entry_cam_h = Gtk.Entry(text="29.0"); vbox_vars.pack_start(Gtk.Label(label="True Camera H (cm):"),0,0,0); vbox_vars.pack_start(self.entry_cam_h,0,0,0)
        self.entry_f = Gtk.Entry(text="846"); vbox_vars.pack_start(Gtk.Label(label="Focal Length (px):"),0,0,0); vbox_vars.pack_start(self.entry_f,0,0,0)
        self.entry_roi = Gtk.Entry(text="10,400,100,470"); vbox_vars.pack_start(Gtk.Label(label="Tray ROI:"),0,0,0); vbox_vars.pack_start(self.entry_roi,0,0,0)
        self.entry_alpha = Gtk.Entry(text="1.0"); vbox_vars.pack_start(Gtk.Label(label="Alpha Multiplier:"),0,0,0); vbox_vars.pack_start(self.entry_alpha,0,0,0)
        self.entry_cam = Gtk.Entry(text="0"); vbox_vars.pack_start(Gtk.Label(label="Cam Index:"),0,0,0); vbox_vars.pack_start(self.entry_cam,0,0,0)
        frame_vars.add(vbox_vars); vbox_ctrl.pack_start(frame_vars, False, False, 0)

        self.btn_start = Gtk.Button(label="Start Debug Stream"); self.btn_start.connect("clicked", self.on_start_clicked)
        self.btn_start.set_sensitive(False)
        vbox_ctrl.pack_start(self.btn_start, False, False, 10)
        self.btn_stop = Gtk.Button(label="Stop"); self.btn_stop.connect("clicked", self.on_stop_clicked); self.btn_stop.set_sensitive(False)
        vbox_ctrl.pack_start(self.btn_stop, False, False, 0)
        self.lbl_status = Gtk.Label(label="Initializing..."); vbox_ctrl.pack_start(self.lbl_status, False, False, 10)
        self.lbl_debug = Gtk.Label(label="Waiting for cup..."); self.lbl_debug.set_justify(Gtk.Justification.LEFT); vbox_ctrl.pack_start(self.lbl_debug, False, False, 10)
        hbox.pack_start(vbox_ctrl, False, False, 0)
        self.image = Gtk.Image(); hbox.pack_start(self.image, True, True, 0)

    def load_config(self):
        try:
            config_file = os.path.join(root_dir, 'midas_calibration.yaml')
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    config = yaml.safe_load(f)
                    self.entry_f.set_text(str(config.get('focal_length', 846.0)))
                    self.entry_alpha.set_text(str(config.get('alpha', 1.0)))
                    roi = config.get('tray_roi', [10,400,100,470])
                    self.entry_roi.set_text(f"{roi[0]},{roi[1]},{roi[2]},{roi[3]}")
        except: pass

    def on_start_clicked(self, widget):
        if self.running: return
        self.running = True
        self.btn_start.set_sensitive(False)
        self.btn_stop.set_sensitive(True)
        import threading
        threading.Thread(target=self.run_loop, daemon=True).start()

    def on_stop_clicked(self, widget):
        self.running = False
        self.btn_start.set_sensitive(True)
        self.btn_stop.set_sensitive(False)

    def extract_patch_median(self, depth_map, cx, cy, w, h):
        H_m, W_m = depth_map.shape
        py1, py2 = max(0, cy - h//2), min(H_m, cy + h//2)
        px1, px2 = max(0, cx - w//2), min(W_m, cx + w//2)
        patch = depth_map[py1:py2, px1:px2]
        return float(np.median(patch)) if patch.size > 0 else 0.0

    def run_loop(self):
        cam_str = self.entry_cam.get_text()
        idx = int(cam_str) if cam_str.isdigit() else cam_str
        self.cap = cv2.VideoCapture(idx)
        if not self.cap.isOpened():
            GLib.idle_add(self.lbl_status.set_text, "Camera Failed to Open!")
            self.running = False
            GLib.idle_add(self.btn_start.set_sensitive, True)
            GLib.idle_add(self.btn_stop.set_sensitive, False)
            return
        
        while self.running:
            ret, frame = self.cap.read()
            if not ret: continue
            
            # Read UI values safely (PyGObject allows get_text across threads occasionally but copying to vars is better. 
            # To be 100% safe, we wrap in try block, but since we are isolated it should be fine as long as we don't modify UI).
            try:
                manual_h = float(self.entry_cam_h.get_text())
                focal = float(self.entry_f.get_text())
                alpha = float(self.entry_alpha.get_text())
                t1, t2, t3, t4 = map(int, self.entry_roi.get_text().split(','))
            except:
                continue
            
            depth_map = self.depth_estimator.process(frame)
            boxes = self.detector.detect(frame)
            depth_norm = cv2.normalize(depth_map, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
            
            m_tray = self.depth_estimator.get_tray_depth(depth_norm, (t1,t2,t3,t4))
            cv2.rectangle(frame, (t1, t2), (t3, t4), (255, 0, 0), 2)
            debug_text = f"M_tray: {m_tray:.1f}\n"

            if boxes and m_tray > 0:
                x1, y1, x2, y2 = boxes[0]['bbox']
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cx, cy, w_px = (x1+x2)//2, (y1+y2)//2, max(x2-x1, y2-y1)
                offset = max(5, (y2 - y1) // 10)
                pts = {"TOP":(cx,y1+offset,20,10), "BOT":(cx,y2-offset,20,10), "LFT":(x1+offset,cy,10,20), "RGT":(x2-offset,cy,10,20), "CEN":(cx,cy,20,20)}
                
                for name, (px, py, pw, ph) in pts.items():
                    m = self.extract_patch_median(depth_norm, px, py, pw, ph)
                    ratio = m/m_tray
                    z = calculate_z_rim_alpha(m, m_tray, manual_h, alpha)
                    if z <= 0: debug_text += f"{name} -> M:{m:.1f} | R:{ratio:.2f} | ERR\n"
                    else:
                        h_cup = manual_h - z
                        debug_text += f"{name} -> M:{m:.1f} | R:{ratio:.2f} | Z:{z:.1f}cm | H:{h_cup:.1f}cm\n"
                    cv2.rectangle(frame, (px-pw//2, py-ph//2), (px+pw//2, py+ph//2), (0,255,255), 1)

            # --- Thread-Safe UI Update ---
            # We copy the final frame and text once, and send them to the main thread 
            # for all GDK/GTK operations (Pixbuf creation, etc). This prevents the 134 crash.
            depth_vis = cv2.applyColorMap(depth_norm, cv2.COLORMAP_INFERNO)
            combined = np.hstack((frame, depth_vis))
            GLib.idle_add(self.update_ui, combined, debug_text)
            
        if self.cap: self.cap.release()

    def update_ui(self, frame_bgr, debug_text):
        if not self.running: return
        self.lbl_debug.set_text(debug_text)
        
        # All GDK/GTK object creation MUST happen here in the main UI thread
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, d = rgb.shape
        pb = GdkPixbuf.Pixbuf.new_from_data(rgb.tobytes(), GdkPixbuf.Colorspace.RGB, False, 8, w, h, w*3)
        self.image.set_from_pixbuf(pb)
        return False # Only run once per idle_add

    def on_destroy(self, widget):
        self.running = False
        Gtk.main_quit()

if __name__ == "__main__":
    win = DebugRunnerWindow(); win.show_all(); Gtk.main()
