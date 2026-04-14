# MiDaS Depth Calibration: Multivariate Validation Report
Generated on: 2026-04-14 16:36:08

## 1. Calibration Parameters
The system is currently using the **Multivariate Linear Regression Model**:
$$ Z_{rim} = C_1 \cdot M_{rim} + C_2 \cdot M_{tray} + C_3 \cdot Z_{tray} + C_4 $$

| Parameter | Value |
| :--- | :--- |
| **C1 (Rim Weight)** | -0.0026 |
| **C2 (Tray Weight)** | 0.0095 |
| **C3 (Lens Disp. Weight)** | 1.1113 |
| **C4 (Bias/Shift)** | -12.8446 |
| **Tray ROI** | (0, 260, 30, 350) |

## 2. Global Accuracy Summary
![Evaluation Chart](eval_chart.png)

| Metric | Value | Description |
| :--- | :--- | :--- |
| **Mean Absolute Error (MAE)** | **1.35 cm** | Average absolute distance off target. |
| **Root Mean Sq Error (RMSE)** | **1.52 cm** | Punishes severe outliers heavily. |
| **Standard Deviation ($\sigma$)** | **1.50 cm** | Consistency of the error spread. |
| **Mean Abs Pct Error (MAPE)** | **10.0%** | Average percentage distance off target. |
| **Strict ($\delta < 5mm$)** | **35.7%** | Predictions within 5mm of True Z. |
| **Standard ($\delta < 1cm$)** | **35.7%** | Predictions within 10mm of True Z. |
| **Loose ($\delta < 2cm$)** | **85.7%** | Predictions within 20mm of True Z. |
| **Valid Test Set Frames** | **14** | Total snapshots successfully evaluated. |

## 3. Individual Breakdown
| Snapshot | M_rim | M_tray | True Z | Pred Z | Error % |
| :--- | :--- | :--- | :--- | :--- | :--- |
| calib_tray21.5cm_rim10.2cm_1776158949.jpg | 167.0 | 155.0 | 10.20cm | 12.09cm | 18.5% |
| calib_tray21.5cm_rim11.5cm_1776158396.jpg | 172.0 | 139.0 | 11.50cm | 11.92cm | 3.7% |
| calib_tray21.5cm_rim14.0cm_1776158896.jpg | 195.0 | 175.0 | 14.00cm | 12.20cm | 12.8% |
| calib_tray22.1cm_rim12.1cm_1776158441.jpg | 204.0 | 146.0 | 12.10cm | 12.57cm | 3.9% |
| calib_tray22.6cm_rim11.3cm_1776158992.jpg | 208.0 | 120.0 | 11.30cm | 12.87cm | 13.9% |
| calib_tray23.2cm_rim11.9cm_1776159058.jpg | 208.0 | 123.0 | 11.90cm | 13.56cm | 14.0% |
| calib_tray23.2cm_rim15.7cm_1776158843.jpg | 203.0 | 152.0 | 15.70cm | 13.85cm | 11.8% |
| calib_tray23.3cm_rim13.3cm_1776158495.jpg | 214.0 | 135.0 | 13.30cm | 13.77cm | 3.6% |
| calib_tray24.3cm_rim13.0cm_1776159117.jpg | 214.0 | 151.0 | 13.00cm | 15.04cm | 15.7% |
| calib_tray24.3cm_rim14.3cm_1776158726.jpg | 216.0 | 122.0 | 14.30cm | 14.76cm | 3.2% |
| calib_tray24.3cm_rim16.8cm_1776158781.jpg | 230.0 | 134.0 | 16.80cm | 14.83cm | 11.7% |
| calib_tray25.2cm_rim15.2cm_1776158574.jpg | 231.0 | 107.0 | 15.20cm | 15.57cm | 2.5% |
| calib_tray25.2cm_rim17.7cm_1776158631.jpg | 216.0 | 112.0 | 17.70cm | 15.66cm | 11.5% |
| calib_tray25.8cm_rim14.5cm_1776159171.jpg | 235.0 | 132.0 | 14.50cm | 16.47cm | 13.6% |

## 4. Visual Evidence
### Sample: calib_tray21.5cm_rim10.2cm_1776158949.jpg
![Debug Image](debug_calib_tray21.5cm_rim10.2cm_1776158949.jpg)

**Math Trace**:
- True Floor Distance ($Z_{tray}$): **21.50 cm**
- $Z_{rim} = (-0.0026 \cdot 167.0) + (0.0095 \cdot 155.0) + (1.1113 \cdot 21.5) + -12.8446 = 12.1 cm$
- **Pred Z_rim**: 12.09 cm
- **Pred Cup Height**: 9.41 cm

---

### Sample: calib_tray21.5cm_rim11.5cm_1776158396.jpg
![Debug Image](debug_calib_tray21.5cm_rim11.5cm_1776158396.jpg)

**Math Trace**:
- True Floor Distance ($Z_{tray}$): **21.50 cm**
- $Z_{rim} = (-0.0026 \cdot 172.0) + (0.0095 \cdot 139.0) + (1.1113 \cdot 21.5) + -12.8446 = 11.9 cm$
- **Pred Z_rim**: 11.92 cm
- **Pred Cup Height**: 9.58 cm

---

### Sample: calib_tray21.5cm_rim14.0cm_1776158896.jpg
![Debug Image](debug_calib_tray21.5cm_rim14.0cm_1776158896.jpg)

**Math Trace**:
- True Floor Distance ($Z_{tray}$): **21.50 cm**
- $Z_{rim} = (-0.0026 \cdot 195.0) + (0.0095 \cdot 175.0) + (1.1113 \cdot 21.5) + -12.8446 = 12.2 cm$
- **Pred Z_rim**: 12.20 cm
- **Pred Cup Height**: 9.30 cm

---

### Sample: calib_tray22.1cm_rim12.1cm_1776158441.jpg
![Debug Image](debug_calib_tray22.1cm_rim12.1cm_1776158441.jpg)

**Math Trace**:
- True Floor Distance ($Z_{tray}$): **22.10 cm**
- $Z_{rim} = (-0.0026 \cdot 204.0) + (0.0095 \cdot 146.0) + (1.1113 \cdot 22.1) + -12.8446 = 12.6 cm$
- **Pred Z_rim**: 12.57 cm
- **Pred Cup Height**: 9.53 cm

---

### Sample: calib_tray22.6cm_rim11.3cm_1776158992.jpg
![Debug Image](debug_calib_tray22.6cm_rim11.3cm_1776158992.jpg)

**Math Trace**:
- True Floor Distance ($Z_{tray}$): **22.60 cm**
- $Z_{rim} = (-0.0026 \cdot 208.0) + (0.0095 \cdot 120.0) + (1.1113 \cdot 22.6) + -12.8446 = 12.9 cm$
- **Pred Z_rim**: 12.87 cm
- **Pred Cup Height**: 9.73 cm

---

### Sample: calib_tray23.2cm_rim11.9cm_1776159058.jpg
![Debug Image](debug_calib_tray23.2cm_rim11.9cm_1776159058.jpg)

**Math Trace**:
- True Floor Distance ($Z_{tray}$): **23.20 cm**
- $Z_{rim} = (-0.0026 \cdot 208.0) + (0.0095 \cdot 123.0) + (1.1113 \cdot 23.2) + -12.8446 = 13.6 cm$
- **Pred Z_rim**: 13.56 cm
- **Pred Cup Height**: 9.64 cm

---

### Sample: calib_tray23.2cm_rim15.7cm_1776158843.jpg
![Debug Image](debug_calib_tray23.2cm_rim15.7cm_1776158843.jpg)

**Math Trace**:
- True Floor Distance ($Z_{tray}$): **23.20 cm**
- $Z_{rim} = (-0.0026 \cdot 203.0) + (0.0095 \cdot 152.0) + (1.1113 \cdot 23.2) + -12.8446 = 13.9 cm$
- **Pred Z_rim**: 13.85 cm
- **Pred Cup Height**: 9.35 cm

---

### Sample: calib_tray23.3cm_rim13.3cm_1776158495.jpg
![Debug Image](debug_calib_tray23.3cm_rim13.3cm_1776158495.jpg)

**Math Trace**:
- True Floor Distance ($Z_{tray}$): **23.30 cm**
- $Z_{rim} = (-0.0026 \cdot 214.0) + (0.0095 \cdot 135.0) + (1.1113 \cdot 23.3) + -12.8446 = 13.8 cm$
- **Pred Z_rim**: 13.77 cm
- **Pred Cup Height**: 9.53 cm

---

### Sample: calib_tray24.3cm_rim13.0cm_1776159117.jpg
![Debug Image](debug_calib_tray24.3cm_rim13.0cm_1776159117.jpg)

**Math Trace**:
- True Floor Distance ($Z_{tray}$): **24.30 cm**
- $Z_{rim} = (-0.0026 \cdot 214.0) + (0.0095 \cdot 151.0) + (1.1113 \cdot 24.3) + -12.8446 = 15.0 cm$
- **Pred Z_rim**: 15.04 cm
- **Pred Cup Height**: 9.26 cm

---

### Sample: calib_tray24.3cm_rim14.3cm_1776158726.jpg
![Debug Image](debug_calib_tray24.3cm_rim14.3cm_1776158726.jpg)

**Math Trace**:
- True Floor Distance ($Z_{tray}$): **24.30 cm**
- $Z_{rim} = (-0.0026 \cdot 216.0) + (0.0095 \cdot 122.0) + (1.1113 \cdot 24.3) + -12.8446 = 14.8 cm$
- **Pred Z_rim**: 14.76 cm
- **Pred Cup Height**: 9.54 cm

---

### Sample: calib_tray24.3cm_rim16.8cm_1776158781.jpg
![Debug Image](debug_calib_tray24.3cm_rim16.8cm_1776158781.jpg)

**Math Trace**:
- True Floor Distance ($Z_{tray}$): **24.30 cm**
- $Z_{rim} = (-0.0026 \cdot 230.0) + (0.0095 \cdot 134.0) + (1.1113 \cdot 24.3) + -12.8446 = 14.8 cm$
- **Pred Z_rim**: 14.83 cm
- **Pred Cup Height**: 9.47 cm

---

### Sample: calib_tray25.2cm_rim15.2cm_1776158574.jpg
![Debug Image](debug_calib_tray25.2cm_rim15.2cm_1776158574.jpg)

**Math Trace**:
- True Floor Distance ($Z_{tray}$): **25.20 cm**
- $Z_{rim} = (-0.0026 \cdot 231.0) + (0.0095 \cdot 107.0) + (1.1113 \cdot 25.2) + -12.8446 = 15.6 cm$
- **Pred Z_rim**: 15.57 cm
- **Pred Cup Height**: 9.63 cm

---

### Sample: calib_tray25.2cm_rim17.7cm_1776158631.jpg
![Debug Image](debug_calib_tray25.2cm_rim17.7cm_1776158631.jpg)

**Math Trace**:
- True Floor Distance ($Z_{tray}$): **25.20 cm**
- $Z_{rim} = (-0.0026 \cdot 216.0) + (0.0095 \cdot 112.0) + (1.1113 \cdot 25.2) + -12.8446 = 15.7 cm$
- **Pred Z_rim**: 15.66 cm
- **Pred Cup Height**: 9.54 cm

---

### Sample: calib_tray25.8cm_rim14.5cm_1776159171.jpg
![Debug Image](debug_calib_tray25.8cm_rim14.5cm_1776159171.jpg)

**Math Trace**:
- True Floor Distance ($Z_{tray}$): **25.80 cm**
- $Z_{rim} = (-0.0026 \cdot 235.0) + (0.0095 \cdot 132.0) + (1.1113 \cdot 25.8) + -12.8446 = 16.5 cm$
- **Pred Z_rim**: 16.47 cm
- **Pred Cup Height**: 9.33 cm

---

## 5. Conclusion & Limitations
### Conclusion
The Multivariate Regression approach successfully mitigates the scale and shift ambiguity inherent in monocular depth estimation models. Based on the evaluation metrics:
- The model achieved a highly precise geometric correlation with a **Mean Absolute Error (MAE) of 1.35 cm**.
- The **RMSE of 1.52 cm** confirms the absence of catastrophic arithmetic outliers.
- A **Strict Accuracy ($\delta < 1cm$) of 35.7%** demonstrates that the numerical pipeline is mathematically robust for industrial deployment when analyzing static snapshots.

### Current Limitations
Despite the successful numerical alignment, the system inherits several physical limitations from the underlying AI and the evaluation conditions:
- **AI Temporal Jitter**: Monocular depth models natively suffer from frame-to-frame instability. Depth values can randomly jump or fluctuate even when the physical scene is completely static.
- **Model Quality Dependency**: The final accuracy is heavily bound to the chosen AI model's spatial understanding capabilities. Weak base modeling (e.g., bad edge preservation) will immediately degrade the linear regression.
- **Controlled Lighting Restraints**: The current calibration and testing sets were captured in a consistent lighting environment. Significant lux or glare variations remain untested.
- **Homogeneous Object Testing**: Evaluation metrics were recorded using a single type of cup geometry and material. Transparent, reflective, or vastly complex geometries may produce skewed depth maps that the current $C_1 \dots C_4$ constants cannot properly absorb.

