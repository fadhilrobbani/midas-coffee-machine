# ArUco + MiDaS Fusion Session Report

**Date/Time:** 2026-04-23 17-11-53

## 1. Parameters
Parameters used during this AI depth fusion session:

| Parameter | Value |
| :--- | :--- |
| **Physical Marker Size** | 1.5 cm |
| **Calibration Model** | 1-Point K-Factor |
| **Camera Focal Length** | 660.8 px |

## 2. Global Stability Summary
Statistical summary of cup height predictions gathered over the running frames:

| Metric | Value | Description |
| :--- | :--- | :--- |
| **Average Cup Height** | **8.33 cm** | Mean of all valid predictions. |
| **Median Height (P50)** | **8.41 cm** | Most representative single value. |
| **Precision Error (P95−P5)** | **0.37 cm** | 90% of readings fall within this range. |
| **Standard Deviation ($\sigma$)** | 0.20 cm | Consistency / jitter of the AI model. |
| **Tray Anchor Depth (Z)** | 24.06 cm | Average physical depth of the tray. |
| **Minimum / Maximum Height** | 7.25 / 8.46 cm | Extremes recorded. |
| **Total Frames / Inferences** | 1160 / 47 | Pipeline tracking efficiency. |

## 3. Visual Evidence
### Depth Tracking Chart
![Session Chart](session_chart.png)

