import os
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
import cv2
import time
from tracker import shared_tracker
from framebuffer import framebuffer
from battery_data import shared_rfid_manager  # ✅ Import to log history and handle check-out

qr_detector = cv2.QRCodeDetector()

def start_camera_loop():
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not cap.isOpened():
        print("Failed to open camera")
        return

    print("Camera loop started")
    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.1)
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, decoded_info, points, _ = qr_detector.detectAndDecodeMulti(gray)

        cleaned_qrs = [qr for qr in decoded_info if qr]
        shared_tracker.update(cleaned_qrs)

        for qr in cleaned_qrs:
            shared_rfid_manager.check_in(qr)

        # Auto check-out logic
        active_tags = set(cleaned_qrs)
        for tag in list(shared_rfid_manager.data.keys()):
            last_seen = shared_tracker.batteries.get(tag, {}).get("last_seen", 0)
            if time.time() - last_seen > 30:
                shared_rfid_manager.check_out(tag)

        display = frame.copy()

        if points is not None and len(points):
            for i in range(len(decoded_info)):
                if decoded_info[i]:
                    pts = points[i].astype(int).reshape((-1, 1, 2))
                    diag = cv2.norm(pts[0][0] - pts[2][0])
                    thickness = max(2, min(int(diag / 40), 8))
                    cv2.polylines(display, [pts], True, (0, 255, 0), thickness)
                    x, y = pts[0][0]
                    cv2.putText(display, decoded_info[i], (x, y - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 4)

                    # ✅ Show cycles and avg charge time for debug
                    stats = shared_rfid_manager.get_stats(decoded_info[i])
                    if stats:
                        stats_text = f"Cycles: {stats['cycles']} Avg: {int(stats['average_charge_time'])}s"
                        cv2.putText(display, stats_text, (x, y + 20),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)

        framebuffer.latest_frame = display.copy()
        time.sleep(0.05)

def get_current_batteries():
    data = shared_tracker.get_all()
    print("get_current_batteries() sees:", data)
    return data
