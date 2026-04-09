import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
import cv2
import yaml
import numpy as np
from scipy.optimize import curve_fit

import os
import sys
import json
import time

# Ensure project root is in path so we can import midas_volumecup
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from midas_volumecup.depth import MidasDepthEstimator
from midas_volumecup.detector import YoloDetector

class MultiVariateCalibrationWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="MiDaS Multivariate Calibration")
        self.set_default_size(1000, 600)
        self.connect("destroy", self.on_destroy)
        
        self.cap = None
        self.depth_estimator = None
        self.detector = None
        self.running = False
        
        self.poly_data_points = []
        self.latest_frame = None
        self.latest_depth = None
        self.latest_boxes = None
        self.current_coeffs = None
        self.requested_cam_id = None
        import threading
        self.lock = threading.Lock()
        
        # Ensure data directories exist in the calibration folder
        self.points_file = os.path.join(os.path.dirname(__file__), 'calibration_points_multivariate.json')
        self.snapshots_dir = os.path.join(os.path.dirname(__file__), 'calibration_snapshots_multivariate')
        self.config_file = os.path.join(root_dir, 'midas_calibration.yaml')

        if not os.path.exists(self.snapshots_dir):
            os.makedirs(self.snapshots_dir)
        
        self.setup_ui()
        self.load_config()
        self.load_historical_points()
        
        import threading
        self.lbl_status.set_text("Loading Models (No Crashing Initializing)...")
        threading.Thread(target=self.init_ai, daemon=True).start()

    def init_ai(self):
        self.depth_estimator = MidasDepthEstimator()
        self.detector = YoloDetector()
        GLib.idle_add(self.lbl_status.set_text, "Ready. Camera Starting...")
        GLib.idle_add(self.start_camera)

    def start_camera(self):
        self.running = True
        import threading
        threading.Thread(target=self.run_loop, daemon=True).start()

    def setup_ui(self):
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.add(hbox)
        vbox_ctrl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox_ctrl.set_border_width(10)
        vbox_ctrl.set_size_request(320, -1)
        
        # System Frame
        f_sys = Gtk.Frame(label="System Settings")
        vb_s = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        hb_cam = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.entry_cam = Gtk.Entry(text="0")
        btn_switch = Gtk.Button(label="Switch")
        btn_switch.connect("clicked", self.on_switch_camera)
        hb_cam.pack_start(self.entry_cam, True, True, 0)
        hb_cam.pack_start(btn_switch, False, False, 0)
        vb_s.pack_start(Gtk.Label(label="Cam Index:"),0,0,0)
        vb_s.pack_start(hb_cam, 0,0,0)
        self.entry_f = Gtk.Entry(text="846"); vb_s.pack_start(Gtk.Label(label="Focal Length (px):"),0,0,0); vb_s.pack_start(self.entry_f,0,0,0)
        f_sys.add(vb_s); vbox_ctrl.pack_start(f_sys, 0,0,0)

        # Multivariate Frame
        f_p = Gtk.Frame(label="Multivariate Calibration")
        vb_p = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.entry_roi = Gtk.Entry(text="10,400,100,470"); vb_p.pack_start(Gtk.Label(label="Tray ROI:"),0,0,0); vb_p.pack_start(self.entry_roi,0,0,0)
        self.entry_tray_z = Gtk.Entry(text="35.0"); vb_p.pack_start(Gtk.Label(label="True Z Tray (cm):"),0,0,0); vb_p.pack_start(self.entry_tray_z,0,0,0)
        self.entry_rim_z = Gtk.Entry(text="15.0"); vb_p.pack_start(Gtk.Label(label="True Z Rim (cm):"),0,0,0); vb_p.pack_start(self.entry_rim_z,0,0,0)
        self.entry_rim_diam = Gtk.Entry(text="7.2"); vb_p.pack_start(Gtk.Label(label="True Inner Diam (cm):"),0,0,0); vb_p.pack_start(self.entry_rim_diam,0,0,0)
        self.entry_outer_diam = Gtk.Entry(text=""); vb_p.pack_start(Gtk.Label(label="True Outer Diam (cm) [Opt]:"),0,0,0); vb_p.pack_start(self.entry_outer_diam,0,0,0)
        btn_cap = Gtk.Button(label="Capture Data Point"); btn_cap.connect("clicked", self.on_capture); vb_p.pack_start(btn_cap,0,0,0)
        self.lbl_pts = Gtk.Label(label="Points: 0"); vb_p.pack_start(self.lbl_pts,0,0,0)
        btn_fit = Gtk.Button(label="Calculate Multivariate Weights"); btn_fit.connect("clicked", self.on_fit); vb_p.pack_start(btn_fit,0,0,0)
        self.lbl_res = Gtk.Label(label="C1...C4 = None"); vb_p.pack_start(self.lbl_res,0,0,0)
        f_p.add(vb_p); vbox_ctrl.pack_start(f_p, 0,0,10)

        btn_save = Gtk.Button(label="Save to YAML"); btn_save.connect("clicked", self.on_save); vbox_ctrl.pack_start(btn_save, 0,0,10)
        self.lbl_status = Gtk.Label(label="Status..."); vbox_ctrl.pack_start(self.lbl_status, 0,0,0)
        hbox.pack_start(vbox_ctrl, 0,0,0)
        self.image = Gtk.Image(); hbox.pack_start(self.image, 1,1,0)

    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = yaml.safe_load(f)
                    self.entry_f.set_text(str(config.get('focal_length', 846.0)))
                    self.entry_cam.set_text(str(config.get('camera_index', 0)))
                    roi = config.get('tray_roi', [10,400,100,470])
                    self.entry_roi.set_text(f"{roi[0]},{roi[1]},{roi[2]},{roi[3]}")
        except: pass

    def load_historical_points(self):
        try:
            if os.path.exists(self.points_file):
                with open(self.points_file, 'r') as f:
                    self.poly_data_points = json.load(f)
                self.lbl_pts.set_text(f"Points (Loaded): {len(self.poly_data_points)}")
                # Auto-fit if we have points
                if len(self.poly_data_points) >= 4:
                    self.on_fit(None)
        except Exception as e:
            print(f"Error loading points: {e}")

    def run_loop(self):
        current_idx = None
        
        while self.running:
            try:
                # 1. Handle camera change request
                with self.lock:
                    if self.requested_cam_id is not None:
                        new_idx = self.requested_cam_id
                        self.requested_cam_id = None
                        if new_idx != current_idx:
                            if self.cap is not None:
                                self.cap.release()
                                self.cap = None
                            current_idx = new_idx
                            GLib.idle_add(self.lbl_status.set_text, f"Switching to Camera {current_idx}...")

                # 2. Ensure camera is initialized
                if self.cap is None:
                    # If this was the very first run, get it from entry
                    if current_idx is None:
                        cam_id = self.entry_cam.get_text()
                        current_idx = int(cam_id) if cam_id.isdigit() else cam_id
                    
                    self.cap = cv2.VideoCapture(current_idx)
                    if not self.cap or not self.cap.isOpened():
                        GLib.idle_add(self.lbl_status.set_text, f"FAILED to open Camera {current_idx}. Retrying...")
                        if self.cap: self.cap.release()
                        self.cap = None
                        time.sleep(2.0)
                        continue
                    else:
                        GLib.idle_add(self.lbl_status.set_text, f"Camera {current_idx} Active")

                # 3. Read Frame
                ret, frame = self.cap.read()
                if not ret: 
                    time.sleep(0.01)
                    continue
                
                # 4. Processing
                self.latest_frame = frame.copy()
                self.latest_depth = self.depth_estimator.process(frame)
                self.latest_boxes = self.detector.detect(frame)
                
                depth_norm = cv2.normalize(self.latest_depth, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                if self.latest_boxes:
                    b = self.latest_boxes[0]['bbox']
                    cv2.rectangle(frame, (b[0], b[1]), (b[2], b[3]), (0, 255, 0), 2)
                
                try:
                    roi_text = self.entry_roi.get_text()
                    roi = tuple(map(int, roi_text.split(',')))
                    cv2.rectangle(frame, (roi[0], roi[1]), (roi[2], roi[3]), (255, 0, 0), 2)
                except: pass

                dv = cv2.applyColorMap(depth_norm, cv2.COLORMAP_INFERNO)
                comb = np.hstack((frame, dv))
                GLib.idle_add(self.update_ui, comb)

            except Exception as e:
                print(f"Error in run_loop: {e}")
                time.sleep(1.0)
            
        if self.cap: 
            self.cap.release()
            self.cap = None

    def update_ui(self, frame_bgr):
        if not self.running: return
        # All GDK/GTK object creation MUST happen here in the main UI thread
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, d = rgb.shape
        pb = GdkPixbuf.Pixbuf.new_from_data(rgb.tobytes(), GdkPixbuf.Colorspace.RGB, False, 8, w, h, w*3)
        self.image.set_from_pixbuf(pb)
        return False

    def on_capture(self, widget):
        if self.latest_depth is None or not self.latest_boxes: return
        try:
            tz_tray = float(self.entry_tray_z.get_text())
            tz_rim = float(self.entry_rim_z.get_text())
            t_diam = float(self.entry_rim_diam.get_text())
            try:
                t_outer = float(self.entry_outer_diam.get_text())
            except ValueError:
                t_outer = 0.0
            roi = tuple(map(int, self.entry_roi.get_text().split(',')))
        except: return
        dn = cv2.normalize(self.latest_depth, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        mr, mt = self.depth_estimator.get_rim_depth(dn, self.latest_boxes[0]['bbox']), self.depth_estimator.get_tray_depth(dn, roi)
        if mt > 0:
            point = {'M_rim': mr, 'M_tray': mt, 'Z_tray': tz_tray, 'Z_rim': tz_rim, 'Diam_rim': t_diam, 'Diam_outer': t_outer, 'timestamp': time.time()}
            self.poly_data_points.append(point)
            
            # 1. Save point to JSON
            with open(self.points_file, 'w') as f:
                json.dump(self.poly_data_points, f, indent=4)
                
            # 2. Save image snapshot
            outer_str = f"_outer{t_outer}cm" if t_outer > 0 else ""
            img_path = os.path.join(self.snapshots_dir, f"calib_tray{tz_tray}cm_rim{tz_rim}cm_diam{t_diam}cm{outer_str}_{int(time.time())}.jpg")
            cv2.imwrite(img_path, self.latest_frame)
            
            self.lbl_pts.set_text(f"Points: {len(self.poly_data_points)}")
            self.lbl_status.set_text(f"Captured & Saved: {img_path}")

    def on_fit(self, widget):
        if len(self.poly_data_points) < 4: 
            GLib.idle_add(self.lbl_status.set_text, "Need at least 4 points for multivariate regression.")
            return
        
        try:
            X = []
            Y = []
            for p in self.poly_data_points:
                # X matrix: [M_rim, M_tray, Z_tray, 1] for C1, C2, C3, and bias C4
                X.append([p['M_rim'], p['M_tray'], p['Z_tray'], 1.0])
                Y.append(p['Z_rim'])
            
            X = np.array(X)
            Y = np.array(Y)
            
            # Solve Multivariate Linear Regression: Y = X * C
            C, residuals, rank, s = np.linalg.lstsq(X, Y, rcond=None)
            
            self.current_coeffs = C
            self.lbl_res.set_text(f"C1:{C[0]:.3f} C2:{C[1]:.3f} C3:{C[2]:.3f} C4:{C[3]:.3f}")
            res_str = str(residuals[0])[:6] if len(residuals) > 0 else "N/A"
            GLib.idle_add(self.lbl_status.set_text, f"Fit success! Residual: {res_str}")
        except Exception as e:
            GLib.idle_add(self.lbl_status.set_text, f"Fit Error: {str(e)}")

    def on_save(self, widget):
        if self.current_coeffs is None: return
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f: config = yaml.safe_load(f) or {}
            else: config = {}
        except: config = {}
            
        config['focal_length'] = float(self.entry_f.get_text())
        
        # Save Multivariate coefficients (C1, C2, C3, C4)
        config['c1'] = float(self.current_coeffs[0])
        config['c2'] = float(self.current_coeffs[1])
        config['c3'] = float(self.current_coeffs[2])
        config['c4'] = float(self.current_coeffs[3])
        
        config['tray_roi'] = list(map(int, self.entry_roi.get_text().split(',')))
        config['camera_index'] = int(self.entry_cam.get_text())
        with open(self.config_file, 'w') as f: yaml.dump(config, f)
        self.lbl_status.set_text("Saved to root midas_calibration.yaml")

    def on_switch_camera(self, widget):
        cam_id = self.entry_cam.get_text()
        idx = int(cam_id) if cam_id.isdigit() else cam_id
        with self.lock:
            self.requested_cam_id = idx
        self.lbl_status.set_text(f"Requesting camera switch to {idx}...")

    def on_destroy(self, widget):
        self.running = False; Gtk.main_quit()

if __name__ == "__main__":
    win = MultiVariateCalibrationWindow(); win.show_all(); Gtk.main()
