# MiDaS Industrial Volume Estimation: Master Guide

This guide explains the 4-step professional workflow for calibrating and running the MiDaS Volume Estimation system within this structured workspace.

## 📁 Workspace Layout

| Folder | Purpose | Key Files |
| :--- | :--- | :--- |
| **`01_calibration/`** | Initial Setup & Curve Fitting | `calibrate_midas_polynomial.py`, `calibrate_depth_multivariate.py` |
| **`02_evaluation/`** | Accuracy Audit & Reporting | `evaluate_test_data.py`, `evaluate_depth_multivariate.py` |
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
Capture physical data points to build the depth geometry factors.
- **Legacy (Alpha Multiplier)**: Run `python 01_calibration/calibrate_midas_polynomial.py`
- **Modern (Multivariate)**: Run `python 01_calibration/calibrate_depth_multivariate.py` *(Recommended)*

**How to Calibrate**:
- **True Z Tray (cm)**: The physical distance from the camera lens to the floor/tray. Measure this accurately with a ruler.
- **True Z Rim (cm)**: The physical distance from the camera lens to the cup rim.
- **Tray ROI**: Set this box to a flat, empty area on the **absolute floor or tray surface** where the cup sits. This serves as the depth reference (`M_tray`).
- Place cups of different sizes and occasionally move the camera to different heights. Enter both true Z values and click **Capture Data Point**.
- Capture at least **3–5 points** covering different nozzle altitudes to average out optical lens distortion (Multivariate requires a minimum of 4 points).
- Click **Calculate** to fit the regression (Alpha or C1-C4 weights).
- Click **Save to YAML** to lock the constants to the root config.
- **Tip**: If you have multiple cameras, use the **Cam Index** entry and click **Switch** to change feeds without restarting.

### Step 3: Test Dataset Collection (New)
For a professional accuracy audit, collect a separate "Test Dataset" that isn't used for fitting the curve.
- Run: `python 04_dataset/collect_test_data.py`
- This script is a lightweight version of the calibrator. Enter both the `True Z Tray` and `True Z Rim`, and click **Capture Dataset Point**.
- **Recommended Count**: Collect **10-15 snapshots** at strictly varying camera heights. This ensures the geometric math remains unbroken regardless of nozzle position.
- It saves pure test images to `04_dataset/test_snapshots/`.

### Step 4: Accuracy Audit (Evaluation)
Verify exactly how accurate your calibration is using the collected test dataset.
- **Legacy Evaluator**: Run `python 02_evaluation/evaluate_test_data.py` (Tests Alpha $\alpha$)
- **Modern Evaluator**: Run `python 02_evaluation/evaluate_depth_multivariate.py` (Tests C1-C4)

- **Historical Tracking**: Each run creates a new **timestamped folder** (e.g., `evaluation_results/eval_20260401_120000/`). This prevents old results from being overwritten.
- This script automatically scans your test dataset and compares the model's predictions vs your ground truth.
- Open the **`validation_report.md`** inside the latest timestamped folder to see the visual evidence and the **Global Accuracy Summary** table.
- **Understanding your Metrics**:
  - **MAE**: The average raw distance (in cm) your predictions were off.
  - **RMSE**: If this is much higher than your MAE, it means your AI has a few massive, catastrophic failures (outliers).
  - **Std Dev ($\sigma$)**: If this is high, the AI's guesses are wildly erratic. If this is *low* but your MAE is high, you simply have a systematic offset and just need to re-calibrate your Alpha Multiplier.
  - **MAPE**: Your system's average error represented as a percentage.
  - **Strict/Standard/Loose ($\delta$ - Delta)**: Your hard "Success Rate" (e.g., "95% of cups were accurate within 1cm"). Use this as your pass/fail criteria for production.

### Step 5: Final Run (Production)
Deploy the system for real-time volume estimation.
- Run: `python 05_production/run_volumecup_midas.py`
- The system will use the `midas_calibration.yaml` saved in the root to provide live volume in mL.

---

## 🛠️ Configuration
All scripts share the central configuration file: **`midas_calibration.yaml`** in the root directory. 
- **DO NOT** delete this file; it contains your lenses' Focal Length and your calibration constants (Alpha $\alpha$ or $C_1 \dots C_4$).

---

## 📦 Archive
Old versions, experiments, and legacy documentation are stored in **`99_archive/`** to keep the workspace clean.
