# Walkthrough: Coffee Machine AI Monitor GUI

We have implemented a PyGObject (GTK 3) GUI application to test the YOLOv8 coffee machine model (`best.pt`) with live camera or video files.

## Summary of Changes
1. **[app.py](file:///home/fadhilrobbani/Programming/Aranus/coffee-machine-new-liquid-model/app.py)**: Main GUI application that runs the camera feed/YOLOv8 inference in a background thread to prevent UI freezing.
2. **Custom Dark Theme CSS**: Styled custom widgets for a clean modern dark-mode layout.

---

## How to Run the GUI

Activate your conda environment and run the script:

```bash
conda activate midas-py310
python app.py
```

---

## Key Features

1. **Flexible Video Sources**: 
   - Enter `0` (or `1`, `2`) to capture from your webcam.
   - Enter the path of an MP4/AVI file to run inference on a recorded video file. If the video ends, the thread will loop back to the beginning automatically.
2. **Model Optimization Sliders**:
   - **Confidence Threshold**: Real-time slider (from `0.05` to `1.00`). Drag to adjust target confidence levels.
   - **NMS IoU Threshold**: Adjusts Non-Maximum Suppression overlap threshold.
3. **Toggle YOLOv8 Inference**:
   - Flip the GTK Switch to turn YOLOv8 inference on and off instantly without stopping the video feed.
4. **Live Statistics**:
   - **FPS**: Calculates raw rendering frame rate.
   - **Inference Delay**: Displays model prediction time in milliseconds.
   - **Cup Rim & Liquid Count**: Updates dynamically to show how many objects of each class are in the frame.
5. **Adaptive Layout**:
   - The video feed container dynamically resizes the frame using Bilinear scaling to fit your window size.
