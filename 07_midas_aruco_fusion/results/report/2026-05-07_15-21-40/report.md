# ArUco + MiDaS Fusion Session Report

**Date/Time:** 2026-05-07 15-21-40

## 1. Parameters
Parameters used during this AI depth fusion session:

| Parameter | Value |
| :--- | :--- |
| **Physical Marker Size** | 2.5 cm |
| **Calibration Model** | Bilateral Z-Grid |
| **Camera Focal Length** | 1009.3 px |

## 2. Global Stability Summary
Statistical summary of cup height predictions gathered over the running frames:

| Metric | Value | Description |
| :--- | :--- | :--- |
| **Average Cup Height** | **11.49 cm** | Mean of all valid predictions. |
| **Median Height (P50)** | **11.60 cm** | Most representative single value. |
| **Precision Error (P95−P5)** | **5.52 cm** | 90% of readings fall within this range. |
| **Standard Deviation ($\sigma$)** | 2.25 cm | Consistency / jitter of the AI model. |
| **Tray Anchor Depth (Z)** | 22.81 cm | Average physical depth of the tray. |
| **Minimum / Maximum Height** | 8.45 / 14.14 cm | Extremes recorded. |
| **Total Frames / Inferences** | 12 / 12 | Pipeline tracking efficiency. |

## 3. Visual Evidence
### Depth Tracking Chart
![Session Chart](session_chart.png)

