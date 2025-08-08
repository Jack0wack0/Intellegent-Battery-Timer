from flask import Flask, render_template, jsonify, request
import threading
import time
from waitress import serve

from firebase_admin import db 
from input_listener import handle_serial, listen_rfid
import threading


app = Flask(__name__)

# Global settings object
settings_state = {"minimum_time": 60, "mode": "rfid"}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def status():
    
    minimum_time_seconds = settings_state.get("minimum_time", 60)

@app.route('/api/set_minimum_time', methods=['POST'])
def set_min_time():
    settings_state["minimum_time"] = request.json.get('minimum_time', 0)
    return jsonify(success=True)

@app.route('/api/get_minimum_time')
def get_min_time():
    return jsonify(minimum_time=settings_state.get("minimum_time", 0))

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

@app.route('/api/battery-name', methods=['POST'])
def set_battery_name():
    data = request.get_json()
    tag_id = data.get('tag_id')
    name = data.get('name')
    if not tag_id or not name:
        return jsonify({"error": "Missing tag_id or name"}), 400

    ref = db.reference(f'BatteryNames/{tag_id}')
    ref.set(name)
    return jsonify({"status": "success", "tag_id": tag_id, "name": name})



if __name__ == '__main__':
    threading.Thread(target=handle_serial, daemon=True).start()
    listen_rfid()
    print("Starting Flask server on http://127.0.0.1:5000")
    serve(app, host='127.0.0.1', port=5000)
