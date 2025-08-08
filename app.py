from flask import Flask, render_template, jsonify, request
import threading
import time
from waitress import serve
from firebase_admin import db 
from input_listener import handle_serial, listen_rfid
import threading
import os
from dotenv import load_dotenv


app = Flask(__name__)


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

# this is not working i need to fix it


load_dotenv()

@app.route('/')
def index():
    firebase_config = {
        "apiKey": os.getenv("FIREBASE_API_KEY"),
        "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
        "databaseURL": os.getenv("FIREBASE_DB_URL"),
        "projectId": os.getenv("FIREBASE_PROJECT_ID")
    }
    return render_template("index.html", firebase_config=firebase_config)



if __name__ == '__main__':
    threading.Thread(target=handle_serial, daemon=True).start()
    listen_rfid()
    print("Starting Flask server on http://127.0.0.1:5000")
    serve(app, host='127.0.0.1', port=5000)
