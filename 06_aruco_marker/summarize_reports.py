"""
summarize_reports.py — Gabungkan semua session report menjadi satu Markdown ringkasan

Membaca session_data.json (jika ada) atau fallback ke report.md (regex)
dari setiap folder di results/report/<timestamp>/

Output: results/report/summary_report.md

Contoh:
  python summarize_reports.py
"""

import json
import os
import re
import sys
from datetime import datetime

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_BASE = os.path.join(_SCRIPT_DIR, "results", "report")


def parse_from_json(json_path):
    """Ambil metrik dari session_data.json (akurat, tanpa regex)."""
    try:
        with open(json_path, "r") as f:
            data = json.load(f)
    except Exception:
        return None

    s = data.get("summary", {})
    p = data.get("parameters", {})
    return {
        "source": "json",
        "timestamp": data.get("session_timestamp", "N/A"),
        "avg_distance": str(s.get("avg_distance_cm", "N/A")),
        "std_dev":      str(s.get("std_dev_cm", "N/A")),
        "min_distance": str(s.get("min_distance_cm", "N/A")),
        "max_distance": str(s.get("max_distance_cm", "N/A")),
        "spread":       str(s.get("spread_cm", "N/A")),
        "detect_rate":  str(s.get("detection_rate_pct", "N/A")),
        "total_frames": str(s.get("total_frames", "N/A")),
        "detected_frames": str(s.get("detected_frames", "N/A")),
        "percentiles":  s.get("percentiles", {}),
        "median_dist": str(s.get("percentiles", {}).get("p50", "N/A")),
        "precision_error": str(round(s.get("percentiles", {}).get("p95", 0) - s.get("percentiles", {}).get("p5", 0), 2)) if "p5" in s.get("percentiles", {}) else "N/A",
        "dictionary":   p.get("dictionary", "N/A"),
        "marker_size":  str(p.get("marker_size_cm", "N/A")),
        "focal_length": str(p.get("focal_length_px", "N/A")),
        "lock_focus":   "ON" if p.get("lock_focus") else "OFF",
        "n_screenshots": len(data.get("screenshots", [])),
        "has_chart":    True,
        "chart_relpath": None,
        "conclusion":   None,
        "distance_history": data.get("distance_samples", []),
        "ground_truth": str(s.get("ground_truth_cm", "N/A")) if s.get("ground_truth_cm") is not None else "N/A",
    }


def parse_from_markdown(md_path):
    """Fallback: ekstrak metrik via regex dari report.md (sesi lama tanpa JSON)."""
    try:
        with open(md_path, "r") as f:
            content = f.read()
    except Exception:
        return None

    def find(pattern, default="N/A"):
        m = re.search(pattern, content)
        return m.group(1).strip() if m else default

    return {
        "source": "markdown",
        "avg_distance": find(r"\*\*Average Distance\*\*\s*\|\s*\*\*([\d.]+) cm\*\*"),
        "median_dist":  find(r"\*\*Median Distance \(P50\)\*\*\s*\|\s*\*\*([\d.]+) cm\*\*"),
        "std_dev":      find(r"\*\*Standard Deviation.*?\*\*\s*\|\s*\*\*?([\d.]+) cm\*\*?"),
        "precision_error": find(r"\*\*Precision Error \(P95.P5\)\*\*\s*\|\s*\*\*([\d.]+) cm\*\*"),
        "min_distance": find(r"\*\*Min(?:imum)? Distance\*\*\s*\|\s*([\d.]+) cm"),
        "max_distance": find(r"\*\*Max(?:imum)? Distance\*\*\s*\|\s*([\d.]+) cm"),
        "spread":       find(r"\*\*Distance Spread\*\*\s*\|\s*([\d.]+) cm"),
        "detect_rate":  find(r"\*\*Detection Rate\*\*\s*\|\s*([\d.]+)%"),
        "total_frames": find(r"gathered over (\d+) frames"),
        "detected_frames": "N/A",
        "dictionary":   find(r"\*\*ArUco Dictionary\*\*\s*\|\s*(DICT_\S+)"),
        "marker_size":  find(r"\*\*Physical Marker Size\*\*\s*\|\s*([\d.]+) cm"),
        "focal_length": find(r"\*\*Focal Length.*?\*\*\s*\|\s*([\d.]+) px"),
        "lock_focus":   find(r"\*\*Lock Focus\*\*\s*\|\s*(ON|OFF)"),
        "conclusion":   find(r"## 4\. Conclusion\n+(.+)"),
        "has_chart":    "distance_chart.png" in content,
        "n_screenshots": len(re.findall(r"!\[Screenshot\]", content)),
        "distance_history": [],
        "chart_relpath": None,
        "abs_error_pct": find(r"\*\*Absolute Error\*\*\s*\|\s*\*\*([\d.]+)%\*\*"),
        "ground_truth": find(r"Variance from true distance \(([\d.]+) cm,"),
    }


def auto_conclusion(stats):
    """Generate conclusion string dari detection rate."""
    try:
        rate = float(stats.get("detect_rate", 0))
    except Exception:
        return "N/A"
    if rate >= 80:
        return "The session shows high detection stability and consistent distance reporting."
    elif rate >= 50:
        return "The session shows moderate detection reliability. Consider adjusting lighting or focus."
    return "Low detection rate observed. Accuracy may be compromised."


def safe_float(val):
    try:
        return float(str(val).replace(" cm", "").replace("%", ""))
    except Exception:
        return None


def main():
    # Kumpulkan semua session folder
    entries = []
    for name in sorted(os.listdir(REPORT_BASE)):
        if not re.match(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}", name):
            continue
        folder = os.path.join(REPORT_BASE, name)
        if not os.path.isdir(folder):
            continue

        json_path = os.path.join(folder, "session_data.json")
        md_path   = os.path.join(folder, "report.md")

        # Prefer JSON, fallback ke Markdown
        if os.path.isfile(json_path):
            metrics = parse_from_json(json_path)
            print(f"  [JSON] {name}")
        elif os.path.isfile(md_path):
            metrics = parse_from_markdown(md_path)
            print(f"  [MD]   {name}")
        else:
            continue

        if metrics is None:
            continue

        metrics["timestamp"] = name
        metrics["chart_relpath"] = os.path.join(name, "distance_chart.png")
        metrics["conclusion"] = metrics.get("conclusion") or auto_conclusion(metrics)
        entries.append(metrics)

    if not entries:
        print("❌ Tidak ada report ditemukan di:", REPORT_BASE)
        sys.exit(1)

    print(f"\n✅ Total {len(entries)} sesi ditemukan")

    # Hitung global stats
    valid_avgs = [safe_float(e["avg_distance"]) for e in entries if safe_float(e["avg_distance"]) is not None]
    valid_stds = [safe_float(e["std_dev"])      for e in entries if safe_float(e["std_dev"])      is not None]
    overall_avg = round(sum(valid_avgs) / len(valid_avgs), 2) if valid_avgs else "N/A"
    overall_std = round(sum(valid_stds) / len(valid_stds), 2) if valid_stds else "N/A"

    # ── Tulis summary_report.md ─────────────────────────────────────────
    out_path = os.path.join(REPORT_BASE, "summary_report.md")
    with open(out_path, "w") as f:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write("# ArUco Detection — Summary of All Sessions\n\n")
        f.write(f"Auto-generated on: {now}  \n")
        f.write(f"Total sessions: **{len(entries)}**\n\n")
        f.write("---\n\n")

        # Overall summary
        f.write("## Overall Summary\n\n")
        f.write("| # | Session | Median Dist | Precision | Abs Error | Std Dev | Detect Rate | Frames | SS | Source |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        for i, e in enumerate(entries, 1):
            src_badge = "🟢 JSON" if e["source"] == "json" else "🟡 MD"
            
            # Hitung absolut error dari JSON jika tersedia, atau parse dari MD
            abs_err = e.get("abs_error_pct", "N/A")
            if e["source"] == "json" and e.get("ground_truth", "N/A") != "N/A" and e.get("median_dist", "N/A") != "N/A":
                try:
                    gt = float(e["ground_truth"])
                    med = float(e["median_dist"])
                    abs_err = f"{(abs(med - gt) / gt * 100):.2f}%"
                except:
                    pass
            e["abs_error_pct"] = abs_err if abs_err != "N/A" else "N/A"

            f.write(f"| {i} | {e['timestamp']} | {e.get('median_dist','N/A')} | {e.get('precision_error','N/A')} | {e['abs_error_pct']} | {e['std_dev']} | "
                    f"{e['detect_rate']}% | {e['total_frames']} | "
                    f"{e['n_screenshots']} | {src_badge} |\n")

        f.write(f"\n**Overall Average Distance:** {overall_avg} cm  \n")
        f.write(f"**Average Std Dev:** {overall_std} cm\n\n")
        f.write("---\n\n")

        # Per-session details
        f.write("## Session Breakdown\n\n")
        for i, e in enumerate(entries, 1):
            f.write(f"### Session {i}: {e['timestamp']}\n\n")
            f.write(f"| Parameter | Value |\n| :--- | :--- |\n")
            f.write(f"| **Dictionary** | {e['dictionary']} |\n")
            f.write(f"| **Marker Size** | {e['marker_size']} cm |\n")
            f.write(f"| **Focal Length** | {e['focal_length']} px |\n")
            f.write(f"| **Lock Focus** | {e['lock_focus']} |\n\n")

            f.write(f"| Metric | Value | Description |\n| :--- | :--- | :--- |\n")
            f.write(f"| **Median Distance (P50)** | **{e.get('median_dist', 'N/A')} cm** | Most representative single value. |\n")
            f.write(f"| **Avg Distance** | {e['avg_distance']} cm | Mean of all detections. |\n")
            f.write(f"| **Precision Error (P95-P5)** | **{e.get('precision_error', 'N/A')} cm** | 90% of readings fall within this range. |\n")
            if e.get("abs_error_pct", "N/A") != "N/A":
                f.write(f"| **Absolute Error** | **{e['abs_error_pct']}** | Error vs ground truth ({e.get('ground_truth', 'N/A')} cm). |\n")
            f.write(f"| **Std Dev** | {e['std_dev']} cm | Consistency of distance. |\n")
            f.write(f"| **Min** | {e['min_distance']} cm | Closest reading. |\n")
            f.write(f"| **Max** | {e['max_distance']} cm | Furthest reading. |\n")
            f.write(f"| **Spread** | {e['spread']} cm | Range (max - min). |\n")
            f.write(f"| **Detection Rate** | {e['detect_rate']}% | Frames with marker detected. |\n")
            f.write(f"| **Total Frames** | {e['total_frames']} | Duration proxy. |\n\n")

            if e["has_chart"]:
                f.write(f"![Distance Chart]({e['chart_relpath']})\n\n")

            if e["conclusion"]:
                f.write(f"> {e['conclusion']}\n\n")

            f.write("---\n\n")

    print(f"✅ Summary report generated: {out_path}")


if __name__ == "__main__":
    main()
