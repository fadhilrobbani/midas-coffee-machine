# Single-Camera Volume Estimation: Technical Conceptual Report

This report outlines the complete mathematical theory, conceptual models, and calibration flow required to perform precise volume estimation using a single RGB camera mounted on a dynamic dispensing nozzle, guided by Deep Learning depth AI (MiDaS).

---

## 1. The Core Geometric Problem
To calculate the true volume of a cylinder (a cup), we need exactly two high-precision physical measurements:
1. **$H_{cup}$ (Height of the Cup)**: Measured in real-world centimeters.
2. **$W_{real}$ (Diameter of the Cup)**: Measured in real-world centimeters.

$$ \text{Volume (mL)} = \pi \times \left( \frac{W_{real}}{2} \right)^2 \times H_{cup} $$

The challenge is that a single 2D camera has no innate concept of 3D depth or scale. A large cup far away looks identical to a tiny cup right next to the lens. To break this illusion, the system uses a chained combination of Physics, Geometry, and AI.

---

## 2. Signal A & B: Finding the Camera's Altitude ($H_{nozzle}$)
Because the camera is mounted on a sliding nozzle block that moves up and down rapidly, the software must dynamically calculate the camera's exact altitude ($H_{nozzle}$) on every single video frame without relying on external mechanical sensors.

### 2.1 Signal A (The Shadow Boundary Transition)
The camera points straight down. The top edge of the video feed perfectly captures the bright, illuminated flat metal drip-tray. Directly below this bright zone is the dark, shadowed interior of the machine's body.
As the nozzle moves up and down on its rail, the visual boundary line between the **Bright Tray** and the **Dark Machine** physically shifts up and down the camera sensor.

1. **Row Means Compression**: We crush the 2D video frame into a 1D vertical array by averaging the brightness of every horizontal row.
2. **Dynamic Threshold**: We find the absolute brightest pixel value ($I_{max}$) in the top portion of the image. We set a boundary line at exactly `60%` of that brightness ($I_{max} \times 0.60$).
3. **Sub-pixel Transition ($R_{trans}$)**: We scan down the rows until we exactly cross that 60% threshold. If it crosses between Row 35 and Row 36, we mathematically interpolate the exact fractional decimal (e.g., $R_{trans} = 35.42$).

Because this shadow shift is mechanically linear, we convert the abstract $R_{trans}$ directly into physical centimeters using slope ($m$) and intercept ($c$):
$$ H_A = m \times R_{trans} + c $$

### 2.2 Signal B (The Normalized Dark Ratio)
If intense sunlight glares off the metallic tray, it will destroy the clean Signal A boundary line.
To prevent catastrophic failure, Signal B completely ignores boundaries. It isolates the bottom half of the video feed and simply counts the total percentage of pixels that are pitch black (`< 40 brightness`). 
Because the nozzle structure gets thicker as the camera moves down, this `Dark Ratio` (0.0 to 1.0) mathematically correlates to altitude:
$$ H_B = m_b \times \text{Dark Ratio} + c_b $$

**Final Altitude**: We weight both signals to create an unshakable reading.
$$ H_{nozzle} = 0.70(H_A) + 0.30(H_B) $$

*(Example: The camera dynamically calculates that it is currently suspended exactly **32.5 cm** above the tray).*

---

## 3. MiDaS & YOLO: Finding the Cup's Altitude ($Z_{rim}$)
Now that we know exactly where the camera is floating ($H_{nozzle}$), we must figure out exactly how far away the lip of the cup is from the camera lens ($Z_{rim}$).
$$ H_{cup} = H_{nozzle} - Z_{rim} $$

### 3.1 The YOLO Object Detector
YOLOv8 scans the frame and draws a perfectly tight bounding box around the circular rim of the cup. 
**Crucial Conceptual Detail:** If we sample the mathematical dead-center of the box `(cx, cy)`, we are directly interrogating the hollow interior of the cup (the coffee liquid/base), which will result in deeply flawed heights. To sample the true physical height of the cup, we instruct the code to exclusively sample the bottom perimeter lip (`y2`) of the bounding box!

### 3.2 The MiDaS Blind AI Dilemma
MiDaS is a neural network that predicts depth. However, it outputs arbitrary, meaningless numbers. 
If it stares at the lip of the YOLO cup, it might output a depth score of `150`. If the room gets slightly darker, the exact same cup might output a score of `90`. 

### 3.3 The Tray ROI (The Anchor)
To cure the hallucination, we draw a permanent "Tray ROI" box in a dead corner of the camera feed where the cup can never reach. We tell MiDaS: *"Whatever is inside this box is the absolute floor ($M_{tray}$)."*

MiDaS scores the cup ($M_{rim} = 150$) and simultaneously scores the background floor ($M_{tray} = 100$).
We dynamically divide them to create an unbreakable Ratio: 
$$ \text{Ratio} = \frac{M_{rim}}{M_{tray}} = \frac{150}{100} = 1.50 $$
Even if room-lighting wreaks havoc on the AI, the mathematical *Ratio* between those two objects in the same frame will miraculously stay exactly the same.

### 3.4 The Inverse Depth Physical Regression
Now we have a solid AI Ratio (`1.50`), but we need centimeters. 
Using a pre-calibrated Non-Linear Regression ($a, b, c$), we curve-fit the Ratio directly into physical lens distance!
Instead of a dangerous polynomial, we use an inverse curve that perfectly mimics real-world optical disparity physics ($Z \propto 1/d$):
$$ Z_{rim} = \frac{a}{\text{Ratio} + b} + c $$

*(Example: A Ratio of 1.50 translates to exactly **12.5 cm**. If $H_{nozzle}$ is 32.5 cm, then $H_{cup}$ is **20.0 cm**).*

---

## 4. Pinhole Geometry: Finding the Cup's Diameter ($W_{real}$)
We have the cup's height, but we need its diameter. 
Using ancient pinhole camera physics (Similar Triangles), if we know the physical `Focal Length` of the glass lens ($f$), the size of an object in pixels ($W_{pixels}$), and exactly how far away the object is ($Z_{rim}$), we can definitively calculate its true width in reality:

$$ W_{real} = \frac{W_{pixels} \times Z_{rim}}{f} $$

With $W_{real}$ and $H_{cup}$ perfectly isolated, the final Volume is instantly generated.

---

## 5. Industrial Robustness Filters
To convert this mathematical model into a deployable real-world system, three industrial filters are perpetually running in the software backend:
1. **CLAHE Normalization (Vision)**: The `cv2.createCLAHE` module scientifically flattens extreme lighting (glare, shadows) on the video feed *before* MiDaS processes it. This forcefully stabilizes $M_{rim}$ and $M_{tray}$ accuracy regardless of the room lighting.
2. **Robust Multi-Pixel Sampling (Data Extraction)**: Sampling a single depth coordinate is heavily prone to noise. Instead, `depth.py` mathematically targets the absolute bottom perimeter of the YOLO box (`y2`) and extracts a wide horizontal strip across the entire ceramic lip, aggressively isolating the mathematical median to destroy outlier noise.
3. **Exponential Moving Average (Temporal UX)**: Video noise results in minor chaotic frame-to-frame calculation jitter. To ensure UX perfection, an EMA algorithmic filter `(0.8 * Z_prev + 0.2 * Z_now)` physically locks the depth output, creating a buttery-smooth measurement transition that eliminates display flicker.

---

## 6. Summary Calibration Workflow
To prime the math for a brand new coffee machine, the user follows a 3-step Calibration Wizard.

**Step 0: Signal A/B Limits (Dynamic Altitude)**
*   Move the nozzle down (e.g., 20.0 cm). Click Capture. The system records $R_{trans}$ and `Dark Ratio`.
*   Move the nozzle up (e.g., 35.0 cm). Click Capture. 
*   *Algorithm*: Runs a linear regression over the points to permanently lock $m, c, m_b, c_b$.

**Step 1: Focal Length Physics ($f$)**
*   Place an object of known width (e.g., 8.0 cm) at a known distance (e.g., 30.0 cm). Click Capture.
*   *Algorithm*: The AI measures the pixel width and mathematically backsolves the immutable Focal Length $f$ of the internal glass lens.

**Step 2: AI Depth Space Curve ($a, b, c$)**
*   Place a tall cup (e.g., $Z_{rim} = 15.0 \text{ cm}$). Click Capture. The AI records Ratio `1.2`.
*   Place a short cup (e.g., $Z_{rim} = 28.0 \text{ cm}$). Click Capture. The AI records Ratio `1.9`.
*   *Algorithm*: Runs `scipy.optimize.curve_fit` to perfectly fit the inverse physical mapping curve mapping AI space to physical reality.

The system is now fully autonomous and mathematically rigid.
