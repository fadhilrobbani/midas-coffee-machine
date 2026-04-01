# MiDaS Industrial Volume Estimation: Master Guide

This guide explains the 4-step professional workflow for calibrating and running the MiDaS Volume Estimation system within this structured workspace.

## 📁 Workspace Layout

| Folder | Purpose | Key Files |
| :--- | :--- | :--- |
| **`01_calibration/`** | Initial Setup & Curve Fitting | `calibrate_midas_polynomial.py`, `visualize_curve.py` |
| **`02_evaluation/`** | Accuracy Audit & Reporting | `evaluate_test_data.py`, `validation_report.md` |
| **`03_diagnostics/`** | Real-time Debugging & Rim Analysis | `detect_camera_height_midas.py` |
| **`04_dataset/`** | Test Data & Snapshot Collection | `collect_test_data.py`, `test_points.json` |
| **`05_production/`** | Live Production Environment | `run_volumecup_midas.py` |
| **`midas_volumecup/`** | Core Math Engine | Underlying logic for AI and Geometry. |
| **`weights/`** | AI Model weights | YOLO and MiDaS `.pt` files. |

---

## 🚀 The Industrial Workflow

### Step 0: Initialization
Before run the project, please download the weight first and put in weights folder (download in my Github), the model is contain of:
- cup_detection_v3_12_s_best.pt
- midas_v21_small_256.pt

and after that install the necessary library or create new environment
```shell
conda env create -f environment.yaml
conda activate midas-py310
```

### Step 1: Stability Check (Diagnostics)
Before calibrating, ensure your camera and lighting are stable.
- Run: `python 03_diagnostics/detect_camera_height_midas.py`
- Verify that the YOLO green box stays locked on the cup rim and the `M_tray` value isn't flickering wildly.

### Step 2: Parameter Capture (Calibration)
Capture physical data points to build the depth multiplier factor.
- Run: `python 01_calibration/calibrate_midas_polynomial.py`
- **True Z Tray (cm)**: The physical distance from the camera lens to the floor/tray. Measure this accurately with a ruler.
- **True Z Rim (cm)**: The physical distance from the camera lens to the cup rim.
- **Tray ROI**: Set this box to a flat, empty area on the **absolute floor or tray surface** where the cup sits. This serves as the depth reference (`M_tray`).
- Place cups of different sizes and occasionally move the camera to different heights. Enter both true Z values and click **Capture Data Point**.
- Capture at least **3–5 points** covering different nozzle altitudes to average out optical lens distortion.
- Click **Calculate Alpha Multiplier** (uses the pure geometric multiplier).
- Click **Save to YAML** to lock the $\alpha$ constant to the root config.
- **Tip**: If you have multiple cameras, use the **Cam Index** entry and click **Switch** to change feeds without restarting.

### Step 3: Test Dataset Collection (New)
For a professional accuracy audit, collect a separate "Test Dataset" that isn't used for fitting the curve.
- Run: `python 04_dataset/collect_test_data.py`
- This script is a lightweight version of the calibrator. Enter both the `True Z Tray` and `True Z Rim`, and click **Capture Dataset Point**.
- **Recommended Count**: Collect **10-15 snapshots** at strictly varying camera heights. This ensures the geometric math remains unbroken regardless of nozzle position.
- It saves pure test images to `04_dataset/test_snapshots/`.

### Step 4: Accuracy Audit (Evaluation)
Verify exactly how accurate your calibration is using the collected test dataset.
- Run: `python 02_evaluation/evaluate_test_data.py`
- **Historical Tracking**: Each run creates a new **timestamped folder** (e.g., `evaluation_results/eval_20260401_120000/`). This prevents old results from being overwritten.
- This script automatically scans your test dataset and compares the model's predictions vs your ground truth.
- Open the **`validation_report.md`** inside the latest timestamped folder to see the full Error % table and visual evidence (side-by-side heatmap).
- If the Error % is too high (>10%), recapture points in Step 2.

### Step 5: Final Run (Production)
Deploy the system for real-time volume estimation.
- Run: `python 05_production/run_volumecup_midas.py`
- The system will use the `midas_calibration.yaml` saved in the root to provide live volume in mL.

---

## 🛠️ Configuration
All scripts share the central configuration file: **`midas_calibration.yaml`** in the root directory. 
- **DO NOT** delete this file; it contains your lenses' Focal Length and your custom **Alpha ($\alpha$) Multiplier**.

---

## 📦 Archive
Old versions, experiments, and legacy documentation are stored in **`99_archive/`** to keep the workspace clean.
