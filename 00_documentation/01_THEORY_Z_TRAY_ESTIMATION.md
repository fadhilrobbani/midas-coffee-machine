# Theoretical Report: Absolute Camera Altitude Estimation via Monocular Depth Regression

## 1. The Core Concept
Monocular AI depth models (such as MiDaS or Depth Anything) do not output absolute distances in centimeters; instead, they generate **relative disparity** values. However, because the camera is mounted on a strict, static vertical axis (moving exclusively straight up and down perpendicular to the tray), the relationship between the AI's predicted disparity and the actual physical distance is mathematically predictable and absolute.

By permanently anchoring the AI's reading area to a specific spot on the tray that is never obscured by an object (like a coffee cup), we can create a mathematical function that directly translates the raw AI depth output into the physical camera altitude ($Z_{tray}$).

---

## 2. Spatial Setup & Variable Definitions
The system defines its mechanical constraints and reading areas as follows:

- **$Z_{min}$**: The lowest physical point of the nozzle (e.g., the minimum allowable mechanical distance to the tray).
- **$Z_{max}$**: The highest physical point of the nozzle.
- **Anchor ROI ($A_{tray}$)**: Two static bounding boxes (located at the bottom-left and bottom-right corners of the camera frame) heavily guaranteed to always capture the bare floor of the tray, regardless of the size of the coffee cup placed in the center.
- **$d_{tray}$**: The raw, median disparity value outputted by the AI depth model within the $A_{tray}$ regions.
- **$Z_{tray}$**: The absolute physical distance from the camera lens to the tray during runtime (the target altitude we are solving for).

---

## 3. The Mathematical Fit (Regression Theory)
The natural physics of pinhole projection cameras and disparity models dictate that they are **inversely proportional to distance** ($Z \propto \frac{1}{d}$). Because of this curvature, a standard Linear Fit (a straight line) will be highly inaccurate at extreme high and low altitudes.

We have two mathematical options to build the correct Calibration Profile:

### Option A: Inverse Linear Regression (Physics-Accurate)
Because real-world distance is inversely proportional to AI disparity, we can convert the raw AI value into its reciprocal before running a linear regression:
$$ Z_{tray} = m \left( \frac{1}{d_{tray}} \right) + c $$
Where **$m$** (slope) and **$c$** (offset) are the permanent calibration constants for your specific lens.

### Option B: 2nd-Order Polynomial Fit (Distortion-Resistant)
If the AI model produces heavy non-linear distortion at extremely close ranges due to convex lens warping, a second-degree polynomial curve will trace and correct that error perfectly:
$$ Z_{tray} = a \cdot (d_{tray})^2 + b \cdot (d_{tray}) + c $$
Where **$a$**, **$b$**, and **$c$** are the constants derived from factory calibration.

---

## 4. Factory Calibration Algorithm
To capture the constants ($m, c$ or $a, b, c$), a technician only needs to perform this workflow once per machine design:

1. Move the nozzle down to exactly **$Z_{min}$**.
2. Run the AI Depth inference. Read the average raw value from the Anchor ROI ($A_{tray}$) and record it as **$d_1$**. Use a physical ruler to measure the actual physical distance and record it as **$Z_1$**.
3. Raise the nozzle incrementally (e.g., by 2 cm or 5 cm steps) until it reaches **$Z_{max}$**.
4. Collect approximately 10 to 15 data pairs of $(d_i, Z_i)$.
5. Apply a standard regression algorithm (like the Least Squares Method) to those 15 data pairs to compute and lock in the system's geometric constants.
6. Save these constants to the system's YAML config file. **Calibration is now permanent.**

---

## 5. Live Runtime Algorithm (RZ/V2H Execution)
When the coffee machine is operating in a live environment, the computational cycle becomes incredibly streamlined and lightweight:

1. **AI Inference**: The RZ/V2H processor captures an RGB frame $\rightarrow$ The Monocular AI processes the frame $\rightarrow$ Outputs the raw Depth Map.
2. **Anchor Extraction**: The system extracts the median pixel value from the static $A_{tray}$ coordinates (bottom left/right of the Depth Map). This single number becomes the live **$d_{tray}$**.
3. **Altitude Resolution**: The CPU passes the live $d_{tray}$ value through the locked calibration polynomial:
   $$ Z_{tray} = a \cdot (d_{tray})^2 + b \cdot (d_{tray}) + c $$
4. **Volume & Scale Injection**: The system now holds the absolute $Z_{tray}$ altitude in strict centimeters. This altitude is immediately passed into the cup dimension modules ($H_{cup}$ and $W_{real}$) as the absolute distance anchor, executing the core relative-scaling formula:
   $$ Z_{rim} = \left( \frac{Z_{tray}}{R} \right) \times \alpha $$

---

## 6. Theoretical Conclusion
By actively utilizing an **Anchor ROI** located in the peripheral, static areas of the tray and combining it with Polynomial or Inverse Linear Regression, the system mathematically eliminates the need for any visual chessboard markers or secondary Tray Pattern Recognition sensors.

The Depth AI model now simultaneously serves dual purposes in a true **Single-Pass Inference**:
1. It provides the relative depth ratio ($R$) between the cup rim and the floor.
2. It acts as a **Virtual Altimeter**, actively tracking the nozzle's absolute altitude ($Z_{tray}$) by reading the depth of the floor anchors.