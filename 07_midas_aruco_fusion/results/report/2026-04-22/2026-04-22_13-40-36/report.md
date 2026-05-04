# ArUco + MiDaS Fusion Session Report

**Date/Time:** 2026-04-22 13-40-36

## 1. Parameters
Parameters used during this AI depth fusion session:

| Parameter | Value |
| :--- | :--- |
| **Physical Marker Size** | 1.5 cm |
| **Calibration Model** | 2-Point Linear (m=0.13702, c=0.11043) |
| **Camera Focal Length** | 660.8 px |

## 2. Global Stability Summary
Statistical summary of cup height predictions gathered over the running frames:

| Metric | Value | Description |
| :--- | :--- | :--- |
| **Average Cup Height** | **7.59 cm** | Mean of all valid predictions. |
| **Median Height (P50)** | **7.38 cm** | Most representative single value. |
| **Precision Error (P95−P5)** | **2.23 cm** | 90% of readings fall within this range. |
| **Standard Deviation ($\sigma$)** | 0.61 cm | Consistency / jitter of the AI model. |
| **Tray Anchor Depth (Z)** | 24.63 cm | Average physical depth of the tray. |
| **Minimum / Maximum Height** | 7.20 / 10.12 cm | Extremes recorded. |
| **Total Frames / Inferences** | 123 / 120 | Pipeline tracking efficiency. |

## 3. Visual Evidence
### Depth Tracking Chart
![Session Chart](session_chart.png)

