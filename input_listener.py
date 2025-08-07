from datetime import datetime
import serial
import threading
import time
from pynput import keyboard
import os
from os import getenv
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
from dotenv import load_dotenv

# === CONFIGURATION ===
load_dotenv()

COM_PORT = "COM4"
BAUD_RATE = 9600
MATCH_WINDOW_SECONDS = 1.0
FIREBASE_DB_BASE_URL = getenv('FIREBASE_DB_BASE_URL')
FIREBASE_CREDS_FILE = getenv('FIREBASE_CREDS_FILE')

# Initialize the app with a service account, granting admin privileges
cred = credentials.Certificate(FIREBASE_CREDS_FILE)
firebase_admin.initialize_app(cred, {
    'databaseURL': FIREBASE_DB_BASE_URL
})

ref = db.reference('/')

# === STATE TRACKING ===
slot_status = {}  # slot_id -> {"state": "PRESENT"/"REMOVED", "last_change": timestamp, "tag": optional tag}
pending_tags = []  # list of (tag_id, timestamp) tuples
lock = threading.Lock()
tag_buffer = ""

# === UTILITY ===
def timestamp(ts=None):
    return datetime.fromtimestamp(ts or time.time()).strftime("%Y-%m-%d %H:%M:%S")

# === SERIAL HANDLER THREAD ===
def handle_serial():
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE)
    except Exception as e:
        print(f"[Serial Port Error] {e}")
        return

    while True:
        try:
            raw_line = ser.readline().decode("utf-8").strip()
        except Exception:
            continue

        if raw_line == "":
            continue


        # Remove leading numeric prefix (timestamp) before SLOT_
        if "SLOT_" not in raw_line:
            continue
        slot_index = raw_line.index("SLOT_")
        line = raw_line[slot_index:]  # e.g. "SLOT_0:PRESENT"

        parts = line.replace("SLOT_", "").split(":")
        if len(parts) != 2:
            continue

        try:
            slot = int(parts[0])
            state = parts[1]
        except ValueError:
            continue

        now = time.time()

        with lock:
            if slot not in slot_status:
                slot_status[slot] = {"state": None, "last_change": 0, "tag": None}

            prev_tag = slot_status[slot]["tag"]
            slot_status[slot]["state"] = state
            slot_status[slot]["last_change"] = now

            if state == "PRESENT":
                
                # Try to match with pending RFID tag
                matched_tag = None
                
                for tag, t_time in pending_tags:
                    print(f"[DEBUG] Comparing tag time {timestamp(t_time)} to slot time {timestamp(now)}")
                    if abs(now - t_time) <= MATCH_WINDOW_SECONDS:
                        matched_tag = tag
                        break
                if matched_tag:
                    print(f"[MATCH] Tag {matched_tag} matched to slot {slot} at {timestamp(now)}")
                    slot_status[slot]["tag"] = matched_tag
                    pending_tags.remove((matched_tag, t_time))

                    ref.child('CurrentChargingList/' + matched_tag).set({
                        'ID': matched_tag,
                        'ChargingStartTime': timestamp(now),
                    })

                    getCurrentChargingRecords = ref.child('BatteryList/' + matched_tag + '/ChargingRecords').get()
                    if getCurrentChargingRecords is None:
                      getCurrentChargingRecords = []
                      getCurrentChargingRecords.append({'startTime': timestamp(now),'ChargingSlot': slot,'id' : 0})
                    else:
                      getCurrentChargingRecords.append({'startTime': timestamp(now),'ChargingSlot': slot,'id': len(getCurrentChargingRecords)})

                    ref.child('BatteryList/' + matched_tag).set({
                        'ID': matched_tag,
                        'ChargingRecords': getCurrentChargingRecords,
                        'IsCharging': True,
                        'ChargingSlot': slot,
                        'ChargingStartTime': timestamp(now),
                        'ChargingEndTime': None,
                        'LastChargingSlot': None,
                    })

            elif state == "REMOVED":
                if prev_tag:
                    print(f"[REMOVED] Tag {prev_tag} removed from slot {slot} at {timestamp(now)}")
                    slot_status[slot]["tag"] = None

                    currentBatteryData = ref.child('BatteryList/' + prev_tag).get()
                    if currentBatteryData:
                        chargingStart = currentBatteryData.get('ChargingStartTime')
                        chargingSlot = currentBatteryData.get('ChargingSlot')

                    ref.child('CurrentChargingList/' + prev_tag).delete()

                    last_record = ref.child('BatteryList/' + prev_tag + '/ChargingRecords').order_by_key().limit_to_last(1).get()
                    if last_record:
                        last_record_key = last_record[0]['id']
                        ref.child(f'BatteryList/{prev_tag}/ChargingRecords/{last_record_key}/endTime').set(timestamp(now))

                    ref.child('BatteryList/' + prev_tag).set({
                        'ID': prev_tag,
                        'IsCharging': False,
                        'ChargingSlot': None,
                        'LastChargingSlot': chargingSlot,
                        'ChargingEndTime': timestamp(now),
                        'ChargingStartTime': None,
                        'LastOverallChargeTime': 0
                    })

# === RFID LISTENER THREAD ===
def on_key_press(key):
    global tag_buffer
    try:
        if hasattr(key, 'char') and key.char and key.char.isdigit():
            tag_buffer += key.char
        elif key == keyboard.Key.enter:
            if len(tag_buffer) >= 10:
                tag_id = tag_buffer[-10:]  # Take last 10 digits
                now = time.time()
                with lock:
                    pending_tags.append((tag_id, now))
                    print(f"[RFID] Tag Read: {tag_id} at {timestamp(now)}")
            tag_buffer = ""
    except Exception:
        pass

def listen_rfid():
    listener = keyboard.Listener(on_press=on_key_press)
    listener.daemon = True
    listener.start()

# === MAIN ===
threading.Thread(target=handle_serial, daemon=True).start()
listen_rfid()

# Keep alive
while True:
    time.sleep(1)
