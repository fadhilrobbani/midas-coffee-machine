import os

with open("run_fusion.py", "r") as f:
    lines = f.readlines()

def extract(start, end, indent_level, add_return=True):
    # Dedent the block by `indent_level` spaces
    block = []
    for line in lines[start-1:end]:
        if len(line.strip()) == 0:
            block.append("\n")
        else:
            block.append(line[indent_level:])
    if add_return:
        block.append("    return calib_data\n")
    return "".join(block)

# Line numbers (based on post-refactor size)
# 1p/2p: 136-314
block_1p = extract(137, 314, 4) # body of `if` starts at 137, indented 8 spaces. Wait, the variables inside need `return calib_data`. We should extract lines 137-314 and dedent by 4 so it sits under a `def` defined at indent 0.
block_3p = extract(318, 447, 4)
block_4p = extract(450, 569, 4)
block_5p = extract(572, 676, 4) # body is 8 spaces
block_6p = extract(680, 830, 4)
block_7p = extract(833, 928, 4)

live_block = extract(953, 1143, 4, add_return=False)
live_finally = extract(1148, 1163, 4, add_return=False)

# We must ensure `cv2`, `time`, `numpy`, `cs`, `hm`, `sr`, `datetime`, `os` are imported.
routines_content = """import time
import cv2
import numpy as np
import core.calibration_storage as cs
import core.height_math as hm
import sys

def run_calib_1p_2p(get_frame, aruco, yolo, midas, headless, true_height, true_height_2, calibrate_mode):
""" + block_1p + """

def run_calib_zgrid(get_frame, aruco, yolo, midas, headless, true_height, n_positions):
""" + block_3p + """

def run_calib_bbox(get_frame, aruco, yolo, midas, headless, true_height):
""" + block_4p + """

def run_calib_geom(get_frame, aruco, yolo, midas, headless, true_height, n_positions):
""" + block_5p + """

def run_calib_bilateral(get_frame, aruco, yolo, midas, headless, true_height, true_height_2, n_positions):
""" + block_6p + """

def run_calib_analytic(get_frame, aruco, yolo, midas, headless, true_height, true_height_2):
""" + block_7p

live_content = """import time
import cv2
import numpy as np
import core.height_math as hm
import core.session_reporter as sr
import os
from datetime import datetime

def run_live_pipeline(get_frame, cap, aruco, yolo, midas, headless, calib_data, marker_size, active_poly_Kgeom, active_cup_str, args, SCREENSHOT_DIR, VIDEO_DIR):
""" + live_block + """
    except KeyboardInterrupt:
        print("\\n[INFO] Execution stopped by user (Ctrl+C).")
    finally:
""" + live_finally

with open("core/calibration_routines.py", "w") as f:
    f.write(routines_content)

with open("core/live_pipeline.py", "w") as f:
    f.write(live_content)

# Now, we rewrite `run_fusion.py` to be the router.
# We keep lines 1 to 134.
top_part = "".join(lines[0:134])
# Then we add the routing logic.
routing_logic = """
    # Delegate to calibration routines
    import core.calibration_routines as calib_rt
    
    if calibrate_mode in (1, 2):
        calib_data = calib_rt.run_calib_1p_2p(get_frame, aruco, yolo, midas, headless, true_height, true_height_2, calibrate_mode)
    elif calibrate_mode == 3:
        calib_data = calib_rt.run_calib_zgrid(get_frame, aruco, yolo, midas, headless, true_height, n_positions)
    elif calibrate_mode == 4:
        calib_data = calib_rt.run_calib_bbox(get_frame, aruco, yolo, midas, headless, true_height)
    elif calibrate_mode == 5:
        calib_data = calib_rt.run_calib_geom(get_frame, aruco, yolo, midas, headless, true_height, n_positions)
    elif calibrate_mode == 6:
        calib_data = calib_rt.run_calib_bilateral(get_frame, aruco, yolo, midas, headless, true_height, true_height_2, n_positions)
    elif calibrate_mode == 7:
        calib_data = calib_rt.run_calib_analytic(get_frame, aruco, yolo, midas, headless, true_height, true_height_2)
    elif calibrate_mode != 0:
        print("[ERROR] Unknown calibration mode")
        return

    if calib_data is None:
        print("[CALIB] Error or Aborted. Exiting.")
        return

    active_poly_Kgeom = [1.0]
    active_cup_str = "LEGACY (1 Profile)"
    if calib_data.get("type") == 5:
        if "profiles" in calib_data:
            if getattr(args, "target_cup", None):
                target_str = str(args.target_cup)
                if target_str in calib_data["profiles"]:
                    active_poly_Kgeom = calib_data["profiles"][target_str]["poly_Kgeom"]
                    active_cup_str = target_str
                else:
                    keys = list(calib_data["profiles"].keys())
                    active_cup_str = keys[0] if keys else "Unknown"
                    active_poly_Kgeom = calib_data["profiles"][active_cup_str].get("poly_Kgeom", [1.0]) if keys else [1.0]
            else:
                keys = list(calib_data["profiles"].keys())
                active_cup_str = keys[0] if keys else "Unknown"
                active_poly_Kgeom = calib_data["profiles"][active_cup_str].get("poly_Kgeom", [1.0]) if keys else [1.0]
        else:
            active_poly_Kgeom = calib_data.get("poly_Kgeom", [1.0])
            
    # Delegate to live pipeline
    import core.live_pipeline as live_pipe
    live_pipe.run_live_pipeline(get_frame, cap, aruco, yolo, midas, headless, calib_data, marker_size, active_poly_Kgeom, active_cup_str, args, SCREENSHOT_DIR, VIDEO_DIR)
"""
bottom_part = "".join(lines[1167:]) # From # ╔════════════ ENTRY POINT to end

with open("run_fusion_refactored.py", "w") as f:
    f.write(top_part + routing_logic + bottom_part)
