from flask import Flask, render_template, Response, jsonify, request
import threading
import time
from vision import start_camera_loop
from tracker import shared_tracker
from framebuffer import framebuffer
import cv2
from waitress import serve
from battery_data import shared_rfid_manager
from settings import get_minimum_time_seconds, get_mode



app = Flask(__name__)
minimum_time_setting = 60 * 60 #defaut charge time is 60 minutes

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def status():
    batteries = shared_tracker.get_all()
    minimum_time_seconds = get_minimum_time_seconds()

    eligible = [
        (k, v) for k, v in batteries.items()
        if time.time() - v['first_seen'] >= minimum_time_seconds
    ]

    if eligible:
        next_battery = sorted(eligible, key=lambda x: x[1]['first_seen'])[0][0]
    else:
        next_battery = "None"

    return jsonify({
        'next_battery': next_battery,
        'batteries': [
            {
                'id': k,
                'time_charging': int(time.time() - v['first_seen'])
            } for k, v in sorted(batteries.items(), key=lambda x: x[1]['first_seen'])
        ]
    })


@app.route('/video_feed')
def video_feed():
    def generate():
        while True:
            if framebuffer.latest_frame is not None and framebuffer.latest_frame.size > 0:
                #gray_stream = cv2.cvtColor(framebuffer.latest_frame, cv2.COLOR_BGR2GRAY)
                ret, buffer = cv2.imencode('.jpg', framebuffer.latest_frame)
                if not ret:
                    continue
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.1)
    
    return Response(
        generate(),
        mimetype='multipart/x-mixed-replace; boundary=frame',
        headers={"Cache-Control": "no-store"}
    )

minimum_time_setting = 0

@app.route('/api/set_minimum_time', methods=['POST'])
def set_minimum_time():
    global minimum_time_setting
    minimum_time_setting = request.json.get('minimum_time', 0)
    return '', 204

from flask import request

minimum_time_seconds = 0  # global variable for charge threshold

@app.route('/api/set_minimum_time', methods=['POST'])
def set_min_time():
    global minimum_time_seconds
    minimum_time_seconds = request.json.get('minimum_time', 0)
    return jsonify(success=True)

@app.route('/api/get_minimum_time')
def get_min_time():
    return jsonify(minimum_time=minimum_time_seconds)

@app.route('/api/rfid/checkin', methods=['POST'])
def rfid_checkin():
    data = request.get_json()
    tag_id = data.get("tag")
    if not tag_id:
        return jsonify({"error": "Missing tag field"}), 400
    shared_rfid_manager.check_in(tag_id)
    return jsonify({"status": "checked_in", "tag": tag_id})

@app.route('/api/rfid/checkout', methods=['POST'])
def rfid_checkout():
    data = request.get_json()
    tag_id = data.get("tag")
    if not tag_id:
        return jsonify({"error": "Missing tag field"}), 400
    shared_rfid_manager.check_out(tag_id)
    return jsonify({"status": "checked_out", "tag": tag_id})

@app.route('/api/rfid/status', methods=['GET'])
def rfid_status():
    checked_in, checked_out = shared_rfid_manager.get_status()
    return jsonify({
        "checked_in": checked_in,
        "checked_out": checked_out
    })
    
@app.route('/api/rfid/history', methods=['GET'])
def rfid_history():
    return jsonify(shared_rfid_manager.get_metadata())

# Global settings object
settings_state = {"minimum_time": 60, "mode": "camera"}

@app.route('/api/set_settings', methods=['POST'])
def set_settings():
    data = request.get_json()
    if "minimum_time" in data:
        settings_state["minimum_time"] = int(data["minimum_time"])
    if "mode" in data:
        settings_state["mode"] = data["mode"]
    return jsonify(settings_state)

@app.route('/api/get_settings', methods=['GET'])
def get_settings():
    return jsonify(settings_state)





if __name__ == '__main__':
    t = threading.Thread(target=start_camera_loop)
    t.daemon = True
    t.start()
    serve(app, host='127.0.0.1', port=5000)
