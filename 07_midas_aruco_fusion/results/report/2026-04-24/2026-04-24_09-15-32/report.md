# ArUco + MiDaS Fusion Session Report

**Date/Time:** 2026-04-24 09-15-32

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
| **Average Cup Height** | **7.87 cm** | Mean of all valid predictions. |
| **Median Height (P50)** | **7.91 cm** | Most representative single value. |
| **Precision Error (P95−P5)** | **0.62 cm** | 90% of readings fall within this range. |
| **Standard Deviation ($\sigma$)** | 0.24 cm | Consistency / jitter of the AI model. |
| **Tray Anchor Depth (Z)** | 21.81 cm | Average physical depth of the tray. |
| **Minimum / Maximum Height** | 6.17 / 8.49 cm | Extremes recorded. |
| **Total Frames / Inferences** | 374 / 344 | Pipeline tracking efficiency. |

## 3. Visual Evidence
### Depth Tracking Chart
![Session Chart](session_chart.png)

