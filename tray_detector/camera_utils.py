"""
camera_utils.py — Utilitas kamera untuk Tray Detector

Menyediakan fungsi untuk inisialisasi kamera dengan kontrol fokus:
- Lock focus (mematikan auto-focus, set fixed focus value)
- Query kemampuan kamera (apakah support focus control)
"""

import cv2


def init_camera(camera_index=0, lock_focus=False, focus_value=0,
                width=640, height=480):
    """
    Inisialisasi kamera dengan opsi lock focus.

    Args:
        camera_index: Index perangkat kamera (0, 1, 2...)
        lock_focus: Jika True, matikan auto-focus dan set fixed focus
        focus_value: Nilai fokus tetap (0 = infinity, semakin tinggi = semakin dekat)
        width: Resolusi horizontal kamera
        height: Resolusi vertikal kamera

    Returns:
        cv2.VideoCapture object dengan konfigurasi yang sudah diterapkan
    """
    cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        print(f"[CAMERA] Error: Tidak bisa membuka kamera index {camera_index}")
        print("[CAMERA] Tips: coba index lain (0, 1, 2) atau periksa koneksi")
        return None

    # Set resolusi kamera
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[CAMERA] Resolusi: {actual_w}x{actual_h}")

    # Lock focus jika diminta
    if lock_focus:
        _lock_camera_focus(cap, focus_value)

    return cap


def _lock_camera_focus(cap, focus_value=0):
    """
    Matikan auto-focus dan set nilai fokus tetap.

    Args:
        cap: cv2.VideoCapture object
        focus_value: Nilai fokus (0 = infinity)
    """
    # Coba matikan auto-focus
    af_supported = cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)

    if af_supported:
        # Set focus value
        cap.set(cv2.CAP_PROP_FOCUS, focus_value)
        actual_focus = cap.get(cv2.CAP_PROP_FOCUS)
        print(f"[CAMERA] ✅ Focus LOCKED: auto-focus OFF, focus={actual_focus}")
    else:
        print("[CAMERA] ⚠️  Kamera tidak mendukung kontrol auto-focus via OpenCV")
        print("[CAMERA]    Coba gunakan v4l2-ctl untuk kontrol manual:")
        print(f"[CAMERA]    v4l2-ctl -d /dev/video{0} -c focus_automatic_continuous=0")
        print(f"[CAMERA]    v4l2-ctl -d /dev/video{0} -c focus_absolute={focus_value}")


def query_camera_focus_info(camera_index=0):
    """
    Query dan tampilkan info fokus kamera (untuk debugging).
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"Tidak bisa membuka kamera {camera_index}")
        return

    af = cap.get(cv2.CAP_PROP_AUTOFOCUS)
    focus = cap.get(cv2.CAP_PROP_FOCUS)
    print(f"[CAMERA INFO] Auto-focus: {af}")
    print(f"[CAMERA INFO] Focus value: {focus}")
    print(f"[CAMERA INFO] Resolution: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
          f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")

    cap.release()
