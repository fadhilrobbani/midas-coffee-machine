import os
import json
from datetime import datetime

CALIB_PATH = "calibration.json"

def load_calibration() -> dict:
    if not os.path.exists(CALIB_PATH):
        return {}
    try:
        with open(CALIB_PATH) as f:
            data = json.load(f)
        ctype = data.get("type", 1)
        labels = {
            1: f"1-Point K-Factor",
            2: f"2-Point Linear",
            3: f"3-Point Z-Grid",
            4: f"4-BBox Area",
            5: f"5-Geometric Proj. (poly deg {len(data.get('poly_Kgeom',[]))-1})",
            6: f"6-Bilateral MiDaS",
            7: f"7-Analytic Geometry"
        }
        print(f"[CALIB] ✅ Loaded calibration model: {labels.get(ctype, 'Unknown')} (from {os.path.basename(CALIB_PATH)})")
        return data
    except Exception as e:
        print(f"[CALIB] ⚠ Failed to read calibration: {e}")
        return {}

def save_calibration_1p(K: float, z_tray_ref: float, ratio_ref: float, true_height: float):
    data = {
        "type": 1,
        "K": K,
        "z_tray_ref_cm": z_tray_ref,
        "ratio_ref": ratio_ref,
        "true_height_cm": true_height,
        "calibrated_at": datetime.now().isoformat()
    }
    with open(CALIB_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[CALIB] 💾 Tersimpan 1-Point → {CALIB_PATH}")

def save_calibration_2p(m: float, c: float, data1: dict, data2: dict):
    data = {
        "type": 2,
        "m": m,
        "c": c,
        "data1": data1,
        "data2": data2,
        "calibrated_at": datetime.now().isoformat()
    }
    with open(CALIB_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[CALIB] 💾 Saved 2-Point → {CALIB_PATH}")

def save_calibration_3p(poly_K: list, z_grid: list, true_height: float):
    data = {
        "type": 3,
        "poly_K": poly_K,
        "z_grid_points": z_grid,
        "true_height_cm": true_height,
        "calibrated_at": datetime.now().isoformat()
    }
    with open(CALIB_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[CALIB] 💾 Saved Z-Grid (type 3) → {CALIB_PATH}")

def save_calibration_4p(m_ref: float, c_ref: float, ref_area: float, z_low: float, z_high: float, true_height: float):
    data = {"type": 4, "m_ref": m_ref, "c_ref": c_ref, "ref_bbox_area_px": ref_area, "z_ref": z_low, "z_high": z_high, "true_height_cm": true_height, "calibrated_at": datetime.now().isoformat()}
    with open(CALIB_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[CALIB] 💾 Saved BBox Area (type 4) → {CALIB_PATH}")

def save_calibration_5p(poly_Kgeom: list, z_grid: list, true_height: float):
    data = {"type": 5, "profiles": {}}
    if os.path.exists(CALIB_PATH):
        try:
            with open(CALIB_PATH, "r") as f:
                old_data = json.load(f)
                if old_data.get("type") == 5 and "profiles" in old_data:
                    data["profiles"] = old_data["profiles"]
                elif old_data.get("type") == 5 and "poly_Kgeom" in old_data:
                    old_h = str(old_data.get("true_height_cm", 7.6))
                    data["profiles"][old_h] = {"poly_Kgeom": old_data["poly_Kgeom"], "z_grid_points": old_data.get("z_grid_points", []), "calibrated_at": old_data.get("calibrated_at", "")}
        except Exception: pass
    data["profiles"][str(true_height)] = {"poly_Kgeom": poly_Kgeom, "z_grid_points": z_grid, "calibrated_at": datetime.now().isoformat()}
    with open(CALIB_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[CALIB] 💾 Saved Geometric Z-Grid (type 5) for Menu [{true_height}cm] → {CALIB_PATH}")

def save_calibration_6p(poly_m: list, poly_c: list, z_grid: list, h1: float, h2: float):
    data = {"type": 6, "poly_m": poly_m, "poly_c": poly_c, "z_grid_points": z_grid, "true_height_cm_1": h1, "true_height_cm_2": h2, "calibrated_at": datetime.now().isoformat()}
    with open(CALIB_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[CALIB] 💾 Saved Bilateral Z-Grid (type 6) → {CALIB_PATH}")

def save_calibration_7(A: float, B: float, h1: float, h2: float):
    data = {"type": 7, "A": A, "B": B, "true_height_cm_1": h1, "true_height_cm_2": h2, "calibrated_at": datetime.now().isoformat()}
    with open(CALIB_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[CALIB] 💾 Saved Universal Analytic Geometry (type 7) → {CALIB_PATH}")
