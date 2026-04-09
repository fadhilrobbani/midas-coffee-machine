import os
import json

calib_dir = "01_calibration"
snapshots_dir = os.path.join(calib_dir, "calibration_snapshots_multivariate")
json_path = os.path.join(calib_dir, "calibration_points_multivariate.json")

# Update JSON
if os.path.exists(json_path):
    with open(json_path, 'r') as f:
        data = json.load(f)
    changed = False
    for pt in data:
        if 'Diam_rim' not in pt or pt['Diam_rim'] != 7.2:
            pt['Diam_rim'] = 7.2
            changed = True
    if changed:
        with open(json_path, 'w') as f:
            json.dump(data, f, indent=4)
        print("Updated calibration_points_multivariate.json to include Diam_rim: 7.2")

# Update Filenames
count = 0
if os.path.exists(snapshots_dir):
    for filename in os.listdir(snapshots_dir):
        if filename.endswith(".jpg") and "diam" not in filename:
            parts = filename.split('_')
            # Assuming parts is ['calib', 'tray23.3cm', 'rim15.6cm', '1775102929.jpg']
            if len(parts) >= 4:
                new_filename = f"{parts[0]}_{parts[1]}_{parts[2]}_diam7.2cm_{parts[3]}"
                os.rename(
                    os.path.join(snapshots_dir, filename),
                    os.path.join(snapshots_dir, new_filename)
                )
                count += 1
if count > 0:
    print(f"Renamed {count} old snapshot files to include diam7.2cm.")
