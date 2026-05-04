# ArUco + MiDaS Fusion Session Report

**Date/Time:** 2026-04-24 13-45-01

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
| **Average Cup Height** | **0.59 cm** | Mean of all valid predictions. |
| **Median Height (P50)** | **0.64 cm** | Most representative single value. |
| **Precision Error (P95−P5)** | **0.57 cm** | 90% of readings fall within this range. |
| **Standard Deviation ($\sigma$)** | 0.19 cm | Consistency / jitter of the AI model. |
| **Tray Anchor Depth (Z)** | 61.44 cm | Average physical depth of the tray. |
| **Minimum / Maximum Height** | 0.21 / 0.85 cm | Extremes recorded. |
| **Total Frames / Inferences** | 39 / 32 | Pipeline tracking efficiency. |

## 3. Visual Evidence
### Depth Tracking Chart
![Session Chart](session_chart.png)

## 4. Screenshots
- ![screenshots/fusion_2026-04-24_134448.jpg](screenshots/fusion_2026-04-24_134448.jpg)
- ![screenshots/fusion_2026-04-24_134454.jpg](screenshots/fusion_2026-04-24_134454.jpg)
- ![screenshots/fusion_2026-04-24_134456.jpg](screenshots/fusion_2026-04-24_134456.jpg)
- ![screenshots/fusion_2026-04-24_134500.jpg](screenshots/fusion_2026-04-24_134500.jpg)
