# MiDaS Multivariate Volume Estimation: Industrial Theory Report

This report outlines the complete mathematical theory, conceptual models, and calibration logic used for the professional-grade volume estimation system. It combines Deep Learning depth AI (MiDaS) with classical Pinhole Geometry using Multivariate Regression to achieve stable measurements from a single RGB sensor mounted on a moving rig.

---

## 1. The Core Geometric Objective
The system derives the physical volume of the cup by measuring two primary dimensions:
1. **$H_{cup}$ (Cup Height)**: Derived from the camera altitude minus the distance to the rim.
2. **$W_{real}$ (Cup Diameter)**: Derived from pixel-width using pinhole projection physics.

> [!NOTE]
> For simplicity we use the base Cylinder volume below, but real-world coffee cups are usually Truncated Cones (Frustums), so a more accurate mathematical representation when calculating volume should be: $\text{Volume} = \frac{1}{3}\pi \cdot H \cdot (R_{top}^2 + R_{top}R_{bottom} + R_{bottom}^2)$. Also note that the pinhole model measures Outer Diameter, whereas internal fluid volume depends on Inner Diameter.

$$ \text{Volume (mL)} = \pi \times \left( \frac{W_{real}}{2} \right)^2 \times H_{cup} $$

---

## 2. Dynamic Nozzle Altitude ($Z_{tray}$)
Because the camera is mounted on a sliding nozzle, the system must continuously determine its absolute physical height above the drip tray ($Z_{tray}$) to provide scale context to the AI.

This altitude is provided by an independent, external vision pipeline (e.g., **Tray Pattern Recognition**). This module analyzes fixed physical geometric patterns on the tray to calculate exact spatial distance, feeding the live $Z_{tray}$ variable directly into the depth engine for every single video frame.

---

## 3. The Depth Engine: Resolving Monocular Ambiguity
Monocular network models (such as MiDaS and Depth Anything) predict **relative disparity**, not absolute metric distances. They suffer from inherent Scale and Shift Ambiguity based on what is currently visible in the frame.

The output disparity $M$ follows the equation:
$$ M = a \cdot \frac{1}{Z} + b $$

Because the AI constantly recalibrates its global context, the shift variable ($b$) is extremely volatile. Taking simple mathematical ratios between two pixels will fail because $b$ cannot be eliminated.

### 3.1 The Solution: Multivariate Linear Regression
To bypass the unknown $a$ and $b$ values, the system extracts dual samples from the AI network:
1. **Cup Rim Disparity ($M_{rim}$)**: The AI's estimation of the cup edge distance.
2. **Tray Anchor Disparity ($M_{tray}$)**: The AI's estimation of the flat floor surface.

These values are combined with the real-time absolute physical altitude of the camera ($Z_{tray}$) into a **Multivariate Linear Regression** sequence. This completely circumvents manual geometry assumptions and allows the system to absorb the AI's internal scale and shift automatically:

$$ Z_{rim} = C_1 \cdot M_{rim} + C_2 \cdot M_{tray} + C_3 \cdot Z_{tray} + C_4 $$

> [!TIP]
> This mathematically elegant solution relies on learned constants ($C_1 \dots C_4$) to act as intelligent weights:
> - **$C_1$**: Scales the AI's rim depth guess.
> - **$C_2$**: Automatically counterbalances any global shift ($b$) hallucinations detected by observing the flat floor.
> - **$C_3$**: Curbs lens distortion physics created by varying camera altitudes.
> - **$C_4$**: An absolute bias shift correcting static hardware errors (e.g., lens-to-sensor mounting gaps).

### 3.2 Factory Calibration 
During calibration, the system automatically runs `np.linalg.lstsq` (Multiple Linear Regression) on a dataset collected by the technician across various extreme and median nozzle altitudes. It seamlessly outputs $C_1, C_2, C_3, C_4$ and locks them perfectly into the `midas_calibration.yaml` configuration for runtime inference.

---

## 4. Pinhole Geometry ($W_{real}$)
To find the diameter, we use the Pinhole Camera Model ($W \approx f \cdot \frac{w}{Z}$). By knowing the Focal Length ($f$) and the precise Z-distance to the rim, we back-solve the real width of the cup:

$$ W_{real} = \frac{W_{pixels} \times Z_{rim}}{f} $$

---

## 5. Industrial Smoothing & Reliability
To prevent frame-to-frame calculation "flicker," the software acts carefully upon input data:

### 5.1 Temporal UX (EMA Filter)
An **Exponential Moving Average** (EMA) mathematically locks the depth output for UI butter-smoothness:
$$ Z_{smooth} = \lambda \cdot Z_{new} + (1 - \lambda) \cdot Z_{prev} $$

### 5.2 Avoid CLAHE Normalization on Depth AI
> [!CAUTION]
> Applying **Contrast Limited Adaptive Histogram Equalization (CLAHE)** to every frame *before* Monocular AI inference is highly destructive. Because models like MiDaS guess depth based on the "global context" of the frame, aggressively normalizing contrast in every frame will cause the scene context to mathematically "pulsate". This causes the intrinsic Scale ($a$) and Shift ($b$) to change dramatically frame-by-frame, inducing massive flicker in the predicted depth even when the scene is static.

---

## 6. Academic Evaluation Metrics
To ensure the depth engine is robust enough for industrial deployment, the evaluation pipeline generates a full academic grading suite. Given a predicted cup height $\hat{y}$ and a true measured height $y$ over $n$ evaluation snapshots:

### 6.1 Mean Absolute Error (MAE)
A simple, universally understood average of the distance off-target.
$$ \text{MAE} = \frac{1}{n} \sum_{i=1}^n |\hat{y}_i - y_i| $$

### 6.2 Root Mean Square Error (RMSE)
Heavily punishes large outlier errors by squaring the error before averaging. In industrial terms, it mathematically proves the system doesn't have wild, catastrophic failures (like missing a cup entirely).

### 6.3 Standard Deviation of Error ($\sigma$)
Measures the spread of the errors around the mean. A high $\sigma$ indicates erratic, untrustworthy AI noise.

### 6.4 Mean Absolute Percentage Error (MAPE)
Normalizes the error relative to the physical scale of the object. A millimeter of error on a tiny cup is heavily penalized compared to the same error on a massive jug.

### 6.5 Delta Threshold Accuracy ($\delta$)
Measures the strict percentage of predictions that perfectly fall within a designated tolerance threshold (e.g., $<5\text{mm}$, $<1\text{cm}$, $<2\text{cm}$). This provides a direct "Success Rate" metric for production deployment gating.

---

## 7. Professional Workflow
| Phase | Tool | Goal |
| :--- | :--- | :--- |
| **Diagnostics** | `03_diagnostics/detect_camera_height_midas.py` | Verify AI stability and sensor noise. |
| **Calibration** | `01_calibration/calibrate_depth_multivariate.py` | Fit constants $C_1 \dots C_4$ and focal length using test points. |
| **Test Collection**| `04_dataset/collect_test_data.py` | Create a dataset of snapshots across various nozzle heights. |
| **Evaluation** | `02_evaluation/evaluate_depth_multivariate.py` | Audit snapshots to verify strict Multivariate Accuracy. |
| **Production** | `05_production/run_volumecup_midas.py` | Deploy the locked-down engine leveraging the live Tray Pattern sensor. |
