import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
import cv2
import yaml
import numpy as np
import threading
from scipy.optimize import curve_fit

from midas_volumecup.depth import MidasDepthEstimator
from midas_volumecup.detector import YoloDetector
from midas_volumecup.camera_config import CameraConfig
from midas_volumecup.volume_math import extract_signal_features

class CalibrationWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="MiDaS Volume Calibration")
        self.set_default_size(1000, 750)
        self.connect("destroy", self.on_destroy)
        
        self.cap = None
        self.current_frame = None
        self.current_depth_map = None
        self.current_boxes = None
        self.running = True
        
        self.depth_estimator = None
        self.detector = None
        
        self.cam_config = None
        self.signal_points = []
        self.poly_data_points = []
        
        self.setup_ui()
        threading.Thread(target=self.load_models, daemon=True).start()

    def load_models(self):
        GLib.idle_add(self.status_label.set_text, "Loading MiDaS...")
        self.depth_estimator = MidasDepthEstimator()
        GLib.idle_add(self.status_label.set_text, "Loading YOLO...")
        self.detector = YoloDetector()
        GLib.idle_add(self.status_label.set_text, "Models loaded! Starting live preview...")
        threading.Thread(target=self.run_loop, daemon=True).start()

    def setup_ui(self):
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.add(hbox)

        vbox_ctrl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox_ctrl.set_border_width(10)
        
        # --- Camera Selection ---
        box_cam = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        box_cam.pack_start(Gtk.Label(label="Camera Index/URL:"), False, False, 0)
        self.entry_cam = Gtk.Entry(text="0")
        box_cam.pack_start(self.entry_cam, True, True, 0)
        
        btn_cam = Gtk.Button(label="Apply Camera")
        btn_cam.connect("clicked", self.on_reconnect_cam)
        box_cam.pack_start(btn_cam, False, False, 0)
        vbox_ctrl.pack_start(box_cam, False, False, 10)
        
        # --- Step 0: Signal A/B Linear Regression ---
        frame_sa = Gtk.Frame(label="Step 0: Signal A/B Calibration")
        vbox_sa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox_sa.set_border_width(5)
        
        box_h1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        box_h1.pack_start(Gtk.Label(label="True Nozzle H (cm):"), False, False, 0)
        self.entry_sig_h = Gtk.Entry(text="25.0")
        box_h1.pack_start(self.entry_sig_h, True, True, 0)
        vbox_sa.pack_start(box_h1, False, False, 0)
        
        btn_add_sig = Gtk.Button(label="Capture Signal Data Point")
        btn_add_sig.connect("clicked", self.on_add_signal_point)
        vbox_sa.pack_start(btn_add_sig, False, False, 0)

        self.lbl_sig_count = Gtk.Label(label="Signal Points: 0")
        vbox_sa.pack_start(self.lbl_sig_count, False, False, 0)

        btn_calc_sig = Gtk.Button(label="Fit Linear Regression (A & B)")
        btn_calc_sig.connect("clicked", self.on_fit_signal)
        vbox_sa.pack_start(btn_calc_sig, False, False, 0)
        
        self.lbl_sig = Gtk.Label(label="m=None, c=None\nmb=None, cb=None")
        vbox_sa.pack_start(self.lbl_sig, False, False, 0)
        frame_sa.add(vbox_sa)
        vbox_ctrl.pack_start(frame_sa, False, False, 0)

        # --- Step 1: Focal Length ---
        frame_fl = Gtk.Frame(label="Step 1: Focal Length (f)")
        vbox_fl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox_fl.set_border_width(5)
        
        box_w = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        box_w.pack_start(Gtk.Label(label="Real Width (cm):"), False, False, 0)
        self.entry_w = Gtk.Entry(text="8.0")
        box_w.pack_start(self.entry_w, True, True, 0)
        vbox_fl.pack_start(box_w, False, False, 0)

        box_z = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        box_z.pack_start(Gtk.Label(label="Distance Z (cm):"), False, False, 0)
        self.entry_z = Gtk.Entry(text="30.0")
        box_z.pack_start(self.entry_z, True, True, 0)
        vbox_fl.pack_start(box_z, False, False, 0)

        btn_focal = Gtk.Button(label="Capture YOLO Width")
        btn_focal.connect("clicked", self.on_calc_focal_clicked)
        vbox_fl.pack_start(btn_focal, False, False, 0)
        
        self.lbl_focal = Gtk.Label(label="f = Not calculated")
        vbox_fl.pack_start(self.lbl_focal, False, False, 0)
        frame_fl.add(vbox_fl)
        vbox_ctrl.pack_start(frame_fl, False, False, 0)

        # --- Step 2: Inverse Depth Curve ---
        frame_poly = Gtk.Frame(label="Step 2: Inverse Depth Calibration")
        vbox_poly = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox_poly.set_border_width(5)

        box_roi = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        box_roi.pack_start(Gtk.Label(label="Tray ROI (x1,y1,x2,y2):"), False, False, 0)
        self.entry_roi = Gtk.Entry(text="10,400,100,470")
        box_roi.pack_start(self.entry_roi, True, True, 0)
        vbox_poly.pack_start(box_roi, False, False, 0)

        box_ztrue = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        box_ztrue.pack_start(Gtk.Label(label="True Z_rim (cm):"), False, False, 0)
        self.entry_ztrue = Gtk.Entry(text="25.0")
        box_ztrue.pack_start(self.entry_ztrue, True, True, 0)
        vbox_poly.pack_start(box_ztrue, False, False, 0)

        btn_add = Gtk.Button(label="Capture Data Point")
        btn_add.connect("clicked", self.on_add_point_clicked)
        vbox_poly.pack_start(btn_add, False, False, 0)

        self.lbl_pts = Gtk.Label(label="Points Collected: 0")
        vbox_poly.pack_start(self.lbl_pts, False, False, 0)

        btn_fit = Gtk.Button(label="Fit Inverse Curve")
        btn_fit.connect("clicked", self.on_fit_clicked)
        vbox_poly.pack_start(btn_fit, False, False, 0)

        self.lbl_poly = Gtk.Label(label="Coefficients: None")
        vbox_poly.pack_start(self.lbl_poly, False, False, 0)
        frame_poly.add(vbox_poly)
        vbox_ctrl.pack_start(frame_poly, False, False, 0)

        btn_save = Gtk.Button(label="Save Calibration")
        btn_save.connect("clicked", self.on_save_clicked)
        vbox_ctrl.pack_start(btn_save, False, False, 10)

        self.status_label = Gtk.Label(label="Initializing...")
        vbox_ctrl.pack_start(self.status_label, False, False, 0)

        hbox.pack_start(vbox_ctrl, False, False, 0)

        self.image = Gtk.Image()
        hbox.pack_start(self.image, True, True, 0)

    def run_loop(self, cam_idx=0):
        self.cap = cv2.VideoCapture(cam_idx)
        while self.running:
            ret, frame = self.cap.read()
            if not ret: break
            
            if self.cam_config is None:
                self.cam_config = CameraConfig(frame.shape[1], frame.shape[0])
            
            self.current_frame = frame.copy()
            clean_frame = frame.copy()
            
            if self.depth_estimator and self.detector:
                self.current_depth_map = self.depth_estimator.process(clean_frame)
                self.current_boxes = self.detector.detect(clean_frame)
                
                if self.current_boxes:
                    for b in self.current_boxes:
                        x1, y1, x2, y2 = b['bbox']
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(frame, "Rim", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                
                try:
                    roi_str = self.entry_roi.get_text()
                    tx1, ty1, tx2, ty2 = map(int, roi_str.split(','))
                    cv2.rectangle(frame, (tx1, ty1), (tx2, ty2), (255, 0, 0), 2)
                    cv2.putText(frame, "Tray ROI", (tx1, ty1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,0,0), 1)
                except: pass

                depth_vis = cv2.normalize(self.current_depth_map, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                depth_vis = cv2.applyColorMap(depth_vis, cv2.COLORMAP_INFERNO)
                combined = np.hstack((frame, depth_vis))
            else:
                combined = frame
                
            rgb = cv2.cvtColor(combined, cv2.COLOR_BGR2RGB)
            h, w, d = rgb.shape
            pb = GdkPixbuf.Pixbuf.new_from_data(rgb.tobytes(), GdkPixbuf.Colorspace.RGB, False, 8, w, h, w*3)
            GLib.idle_add(self.image.set_from_pixbuf, pb)
            
        if self.cap: self.cap.release()

    def show_msg(self, title, msg):
        dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.INFO,
                                   buttons=Gtk.ButtonsType.OK, text=title)
        dialog.format_secondary_text(msg)
        dialog.run()
        dialog.destroy()

    def on_reconnect_cam(self, widget):
        idx_str = self.entry_cam.get_text()
        idx = int(idx_str) if idx_str.isdigit() else idx_str
        
        # Kill current loop
        self.running = False
        if self.cap: self.cap.release()
        
        # Restart loop in new thread
        import time; time.sleep(0.5)
        self.running = True
        threading.Thread(target=self.run_loop, args=(idx,), daemon=True).start()
        self.status_label.set_text(f"Switched to Camera {idx}")

    def on_add_signal_point(self, widget):
        if self.current_frame is None or self.cam_config is None: return
        try:
            h_true = float(self.entry_sig_h.get_text())
        except ValueError:
            self.show_msg("Error", "Invalid Height number")
            return
            
        gray = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2GRAY)
        r_trans, dark_ratio = extract_signal_features(gray, self.cam_config)
        
        if r_trans is None:
            self.show_msg("Error", "Could not find shadow boundary. Is tray fully illuminated in top portion?")
            return
            
        self.signal_points.append({'h_true': h_true, 'r_trans': r_trans, 'dark': dark_ratio})
        self.lbl_sig_count.set_text(f"Signal Points: {len(self.signal_points)}")
        self.show_msg("Success", f"Recorded:\nH: {h_true}\nR_trans: {r_trans:.2f}\nDarkRatio: {dark_ratio:.2f}")

    def on_fit_signal(self, widget):
        if len(self.signal_points) < 2:
            self.show_msg("Error", "Need at least 2 distinct signal points to run linear regression!")
            return
            
        xs_A = np.array([p['r_trans'] for p in self.signal_points])
        xs_B = np.array([p['dark'] for p in self.signal_points])
        ys   = np.array([p['h_true'] for p in self.signal_points])
        
        try:
            # Polyfit degree 1 -> m*x + c
            mA, cA = np.polyfit(xs_A, ys, 1)
            mB, cB = np.polyfit(xs_B, ys, 1)
            
            self.signal_coeffs = (mA, cA, mB, cB)
            self.lbl_sig.set_text(f"m={mA:.2f}, c={cA:.2f}\nmb={mB:.2f}, cb={cB:.2f}")
        except Exception as e:
            self.show_msg("Error Fitting Signal A/B", str(e))

    def on_calc_focal_clicked(self, widget):
        if self.current_frame is None: return
        if not self.current_boxes:
            self.show_msg("Error", "No object detected! Place a cup for YOLO to auto-detect width.")
            return
        try:
            w_real = float(self.entry_w.get_text())
            z_dist = float(self.entry_z.get_text())
        except ValueError:
            self.show_msg("Input Error", "Invalid Real Width or Distance.")
            return
        box = self.current_boxes[0]['bbox']
        w_pixels = max(box[2] - box[0], box[3] - box[1])
        focal_length = (w_pixels * z_dist) / w_real
        self.lbl_focal.set_text(f"f = {focal_length:.2f}")

    def on_add_point_clicked(self, widget):
        if self.depth_estimator is None or self.detector is None:
            self.show_msg("Wait", "Models are still loading...")
            return
        if self.current_depth_map is None or self.current_boxes is None: return
        try:
            true_z_rim = float(self.entry_ztrue.get_text())
            roi_str = self.entry_roi.get_text()
            tray_roi = tuple(map(int, roi_str.split(',')))
        except:
            self.show_msg("Error", "Invalid Z_rim or Tray ROI")
            return
        if len(self.current_boxes) == 0:
            self.show_msg("Error", "No cup rim detected! Ensure cup is in view.")
            return
        best_box = self.current_boxes[0]['bbox']
        
        # MiDaS raw depth can be negative. We MUST normalize to 0-255 before sampling.
        depth_norm = cv2.normalize(self.current_depth_map, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        
        m_rim = self.depth_estimator.get_rim_depth(depth_norm, best_box)
        m_tray = self.depth_estimator.get_tray_depth(depth_norm, tray_roi)
        
        if m_tray <= 0:
            self.show_msg("Error", "Invalid M_tray depth (<= 0). Check if your Tray ROI coordinates are out of bounds for the camera resolution!")
            return
        self.poly_data_points.append({'M_rim': m_rim, 'M_tray': m_tray, 'Z_rim': true_z_rim})
        self.lbl_pts.set_text(f"Points Collected: {len(self.poly_data_points)}")
        self.show_msg("Success", f"Recorded Point!\nM_rim: {m_rim:.2f}\nM_tray: {m_tray:.2f}\nZ_rim: {true_z_rim}")

    def on_fit_clicked(self, widget):
        if len(self.poly_data_points) < 3:
            self.show_msg("Error", "Need at least 3 points.")
            return
        x_data = np.array([p['M_rim'] / p['M_tray'] for p in self.poly_data_points])
        y_data = np.array([p['Z_rim'] for p in self.poly_data_points])
        
        # Mathematically grounded Inverse Depth mapping
        def inverse_curve(ratio, a, b, c): return (a / (ratio + b)) + c
        
        try:
            # p0 gives curve_fit a safe starting point to avoid division by zero
            p0 = [1.0, 0.1, 1.0]
            popt, _ = curve_fit(inverse_curve, x_data, y_data, p0=p0, maxfev=10000)
            self.current_coeffs = popt
            self.lbl_poly.set_text(f"a={popt[0]:.4f}, b={popt[1]:.4f}, c={popt[2]:.4f}")
        except Exception as e:
            self.show_msg("Error", str(e))

    def on_save_clicked(self, widget):
        try:
            if not hasattr(self, 'signal_coeffs'): raise ValueError("Signal A/B not calibrated.")
            focal_str = self.lbl_focal.get_text().replace("f = ", "")
            if "Not" in focal_str: raise ValueError("Focal length not calculated.")
            focal = float(focal_str)
            if not hasattr(self, 'current_coeffs'): raise ValueError("Polynomial not fitted.")
            
            roi_str = self.entry_roi.get_text()
            tray_roi = list(map(int, roi_str.split(',')))
            
            sig_m, sig_c, sig_mb, sig_cb = self.signal_coeffs
            cam_idx_str = self.entry_cam.get_text()
            cam_idx = int(cam_idx_str) if cam_idx_str.isdigit() else cam_idx_str
            
            config = {
                'focal_length': focal,
                'a': float(self.current_coeffs[0]),
                'b': float(self.current_coeffs[1]),
                'c': float(self.current_coeffs[2]),
                'signal_m': float(sig_m),
                'signal_c': float(sig_c),
                'signal_mb': float(sig_mb),
                'signal_cb': float(sig_cb),
                'tray_roi': tray_roi,
                'camera_index': cam_idx
            }
            with open('midas_calibration.yaml', 'w') as f:
                yaml.dump(config, f)
            self.show_msg("Success", "Calibration saved to midas_calibration.yaml")
        except Exception as e:
            self.show_msg("Error", str(e))

    def on_destroy(self, widget):
        self.running = False
        Gtk.main_quit()

if __name__ == "__main__":
    win = CalibrationWindow()
    win.show_all()
    Gtk.main()
