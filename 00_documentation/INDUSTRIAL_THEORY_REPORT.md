# MiDaS Single-Camera Volume Estimation: Industrial Theory Report

This report outlines the complete mathematical theory, conceptual models, and calibration logic used for the professional-grade volume estimation system. It combines Deep Learning depth AI (MiDaS) with classical Pinhole Geometry to achieve stable measurements from a single RGB sensor mounted on a moving rig.

---

## 1. The Core Geometric Objective
The system derives the physical volume of a cylinder (the cup) by measuring two primary dimensions:
1. **$H_{cup}$ (Cup Height)**: Derived from the camera altitude minus the distance to the rim.
2. **$W_{real}$ (Cup Diameter)**: Derived from pixel-width using pinhole projection physics.

$$ \text{Volume (mL)} = \pi \times \left( \frac{W_{real}}{2} \right)^2 \times H_{cup} $$

---

## 2. Dynamic Nozzle Altitude ($Z_{tray}$)
Because the camera is mounted on a sliding nozzle, the system must continuously determine its absolute physical height above the drip tray ($Z_{tray}$) to provide scale context to the AI.

This altitude is provided by an independent, external vision pipeline (e.g., **Tray Pattern Recognition**). This module analyzes fixed physical geometric patterns on the tray to calculate exact spatial distance, feeding the live $Z_{tray}$ variable directly into the MiDaS depth engine for every single video frame.

---

## 3. The Depth Engine: MiDaS & The Ambiguity Problem
MiDaS is a powerful depth estimator, but it predicts **relative depth** ratios, not absolute distances. This creates a critical scale ambiguity when the camera physically moves up and down.

### 3.1 The Tray ROI "Anchor"
To anchor the AI, we define a static **Tray ROI** ($M_{tray}$) as a reference point. MiDaS scores both the cup rim ($M_{rim}$) and this floor anchor. All physical distance calculations originate from this mathematical Ratio:
$$ R = \frac{M_{rim}}{M_{tray}} $$

### 3.2 Resolving Ambiguity: The "Pure Physics" Multiplier (Default)
Because $R$ is mathematically equivalent to the ratio of their physical distances ($R = \frac{Z_{tray}}{Z_{rim}}$), rearranging the formula proves that the calculated cup height strictly depends on knowing the distance to the floor:
$$ Z_{rim} = \frac{Z_{tray}}{R} $$

If digital cameras and glass lenses were flawless, this raw division would be mathematically perfect. To account for optical lens distortion and AI biases, the system introduces a static **Lens Correction Multiplier** ($\alpha$):

$$ \text{Predicted } Z_{rim} = \left( \frac{\text{Live } Z_{tray}}{R} \right) \times \alpha $$

**Factory Calibration (Finding $\alpha$)**  
During calibration, the system does not solve complex multi-variable curves. It simply isolates the optical error factor:
$$ \alpha = \frac{\text{True } Z_{rim} \times R}{\text{True } Z_{tray}} $$
The technician moves the camera to various heights, inputs both True $Z_{tray}$ and True $Z_{rim}$, and the software averages the algebraic results to lock in a single, permanent $\alpha$ constant (saved to `midas_calibration.yaml`).

### 3.3 Alternative: 3D Surface Regression
If the neural network behaves heavily non-linearly at extreme camera altitudes (e.g., severe perspective warping renders a static $\alpha$ inaccurate), the system must fallback to a multidimensional surface fit:
$$ Z_{rim} = \frac{a \cdot Z_{tray}}{R} + b \cdot Z_{tray} + c $$
*Note: While ensuring unbreakable bounding accuracy across all heights, this requires tedious multi-height data collection during assembly.*

---

## 4. Pinhole Geometry ($W_{real}$)
To find the diameter, we use the Pinhole Camera Model ($W \approx f \cdot \frac{w}{Z}$). By knowing the Focal Length ($f$) and the precise Z-distance to the rim, we back-solve the real width of the cup:

$$ W_{real} = \frac{W_{pixels} \times Z_{rim}}{f} $$

---

## 5. Industrial Smoothing & Reliability
To prevent frame-to-frame calculation "flicker," the software applies two constant filters:

### 5.1 Temporal UX (EMA Filter)
An **Exponential Moving Average** (EMA) mathematically locks the depth output for UI butter-smoothness:
$$ Z_{smooth} = \lambda \cdot Z_{new} + (1 - \lambda) \cdot Z_{prev} $$

### 5.2 CLAHE Normalization
**Contrast Limited Adaptive Histogram Equalization** is applied to every frame *before* AI inference. This flattens aggressive glints/shadows from stainless steel components, ensuring the $M_{tray}$ anchor remains mathematically stable across varying lighting scenarios.

---

## 6. Academic Evaluation Metrics
To ensure the depth engine is robust enough for industrial deployment, the evaluation pipeline generates a full academic grading suite. Given a predicted cup height $\hat{y}$ and a true measured height $y$ over $n$ evaluation snapshots:

### 6.1 Mean Absolute Error (MAE)
A simple, universally understood average of the distance off-target.
$$ \text{MAE} = \frac{1}{n} \sum_{i=1}^n |\hat{y}_i - y_i| $$

### 6.2 Root Mean Square Error (RMSE)
Heavily punishes large outlier errors by squaring the error before averaging. In industrial terms, it mathematically proves the system doesn't have wild, catastrophic failures (like missing a cup entirely).
$$ \text{RMSE} = \sqrt{ \frac{1}{n} \sum_{i=1}^n (\hat{y}_i - y_i)^2 } $$

### 6.3 Standard Deviation of Error ($\sigma$)
Measures the spread of the errors around the mean. A low $\sigma$ combined with a high MAE indicates a *systematic bias* (easily fixed by tuning the $\alpha$ multiplier). A high $\sigma$ indicates erratic, untrustworthy AI noise.
$$ \sigma = \sqrt{ \frac{1}{n} \sum_{i=1}^n \left( (\hat{y}_i - y_i) - \text{Mean Error} \right)^2 } $$

### 6.4 Mean Absolute Percentage Error (MAPE)
Normalizes the error relative to the physical scale of the object. A millimeter of error on a tiny cup is heavily penalized compared to the same error on a massive jug.
$$ \text{MAPE} = \frac{100\%}{n} \sum_{i=1}^n \left| \frac{\hat{y}_i - y_i}{y_i} \right| $$

### 6.5 Delta Threshold Accuracy ($\delta$)
Measures the strict percentage of predictions that perfectly fall within a designated tolerance threshold (e.g., $<5\text{mm}$, $<1\text{cm}$, $<2\text{cm}$). This provides a direct "Success Rate" metric for production deployment gating.

---

## 7. Professional Workflow
| Phase | Tool | Goal |
| :--- | :--- | :--- |
| **Diagnostics** | `03_diagnostics/detect_camera_height_midas.py` | Verify AI stability and sensor noise. |
| **Calibration** | `01_calibration/calibrate_midas_polynomial.py` | Solve for $\alpha, f$ using manual $Z_{tray}$ / $Z_{rim}$ data points. |
| **Test Collection**| `04_dataset/collect_test_data.py` | Create a dataset of snapshots across various nozzle heights. |
| **Evaluation** | `02_evaluation/evaluate_test_data.py` | Audit snapshots to verify strictly evaluated Mean Absolute Error (MAE). |
| **Production** | `05_production/run_volumecup_midas.py` | Deploy the locked-down engine leveraging the live Tray Pattern sensor. |
