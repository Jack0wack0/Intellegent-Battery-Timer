from flask import Flask, render_template, jsonify, request
import threading
import time
from waitress import serve
from battery_data import shared_rfid_manager

app = Flask(__name__)

# Global settings object
settings_state = {"minimum_time": 60, "mode": "rfid"}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def status():
    batteries = shared_rfid_manager.get_all_checked_in()  # You may need to ensure this function exists
    minimum_time_seconds = settings_state.get("minimum_time", 60)

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

@app.route('/api/set_minimum_time', methods=['POST'])
def set_min_time():
    settings_state["minimum_time"] = request.json.get('minimum_time', 0)
    return jsonify(success=True)

@app.route('/api/get_minimum_time')
def get_min_time():
    return jsonify(minimum_time=settings_state.get("minimum_time", 0))

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
    serve(app, host='127.0.0.1', port=5000)
