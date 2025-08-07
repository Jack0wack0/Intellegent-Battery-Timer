import json
import os

SETTINGS_FILE = "settings.json"

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {"minimum_time": 60, "mode": "rfid"}  # Fallback defaults
    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)

def save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_minimum_time_seconds():
    settings = load_settings()
    return settings.get("minimum_time", 60) * 60

def get_mode():
    return load_settings().get("mode", "rfid")
