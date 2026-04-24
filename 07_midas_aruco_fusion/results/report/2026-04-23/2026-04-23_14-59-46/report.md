# ArUco + MiDaS Fusion Session Report

**Date/Time:** 2026-04-23 14-59-46

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
| **Average Cup Height** | **7.62 cm** | Mean of all valid predictions. |
| **Median Height (P50)** | **7.63 cm** | Most representative single value. |
| **Precision Error (P95−P5)** | **0.15 cm** | 90% of readings fall within this range. |
| **Standard Deviation ($\sigma$)** | 0.04 cm | Consistency / jitter of the AI model. |
| **Tray Anchor Depth (Z)** | 18.99 cm | Average physical depth of the tray. |
| **Minimum / Maximum Height** | 7.52 / 7.68 cm | Extremes recorded. |
| **Total Frames / Inferences** | 21 / 21 | Pipeline tracking efficiency. |

## 3. Visual Evidence
### Depth Tracking Chart
![Session Chart](session_chart.png)

