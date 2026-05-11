import cv2
from ultralytics import YOLO

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 2592)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1944)
ret, frame = cap.read()
if ret:
    model = YOLO("../weights/best_float32 (2).tflite")
    results = model(frame, verbose=False, imgsz=640, conf=0.45)
    if len(results) > 0:
        for det in results[0].boxes:
            print("Box:", det.xyxy[0].tolist(), "Conf:", det.conf[0].item(), "Class:", det.cls[0].item())
