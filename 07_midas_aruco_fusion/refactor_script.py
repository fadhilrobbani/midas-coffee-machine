import re

with open("run_fusion.py", "r") as f:
    text = f.read()

# 1. Provide imports at the top
imports = """import core.calibration_storage as cs
import core.height_math as hm
import core.session_reporter as sr
"""
text = text.replace("import cv2", imports + "\nimport cv2")

# 2. Add CALIB_PATH update on init
text = text.replace("calib_data = load_calibration()", 
    "cs.CALIB_PATH = CALIB_PATH\n        calib_data = cs.load_calibration()")
text = text.replace("save_calibration", "cs.save_calibration")
text = text.replace("calc_height", "hm.calc_height")

# Also, when saving we also need to set CALIB_PATH in case calibrate > 0
calib_path_set = """    if args.fisheye:
        CALIB_PATH = os.path.join(_THIS_DIR, f"calibration_fisheye_{args.cup_profile}.json")
    elif args.cup_profile != "default":
        CALIB_PATH = os.path.join(_THIS_DIR, f"calibration_{args.cup_profile}.json")"""
calib_path_new = calib_path_set + "\n\n    # Sync CALIB_PATH to storage module\n    cs.CALIB_PATH = CALIB_PATH"
text = text.replace(calib_path_set, calib_path_new)

# Sync REPORT_DIR for session_reporter
report_dir_set = 'REPORT_DIR     = os.path.join(RESULT_DIR, "report")'
report_dir_new = 'REPORT_DIR     = os.path.join(RESULT_DIR, "report")\n# For module\nsr.REPORT_DIR = REPORT_DIR'
text = text.replace(report_dir_set, report_dir_new)

# Update session_reporter call
text = text.replace("_generate_session_report", "sr._generate_session_report")

# 3. Delete old blocks
# Block 1: Calib Save/Load 
text = re.sub(
    r'# ╔═════════════════════════════════════════════════════════════════════════╗\n# ║  KALIBRASI: Save / Load.*?# ╔═════════════════════════════════════════════════════════════════════════╗\n# ║  PIPELINE UTAMA',
    '# ╔═════════════════════════════════════════════════════════════════════════╗\n# ║  PIPELINE UTAMA',
    text, flags=re.DOTALL
)

# Block 2: Report Gen
text = re.sub(
    r'# ╔═════════════════════════════════════════════════════════════════════════╗\n# ║  REPORT GENERATOR.*?# ╔═════════════════════════════════════════════════════════════════════════╗\n# ║  ENTRY POINT',
    '# ╔═════════════════════════════════════════════════════════════════════════╗\n# ║  ENTRY POINT',
    text, flags=re.DOTALL
)

with open("run_fusion_refactored.py", "w") as f:
    f.write(text)

