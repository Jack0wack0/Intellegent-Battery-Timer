# battery_data.py
import json
import os
import time
from tracker import shared_tracker

BATTERY_DATA_FILE = "battery_data_testing.json"

class BatteryDataManager:
    def __init__(self):
        self.data = {}
        self.load()

    def load(self):
        if os.path.exists(BATTERY_DATA_FILE):
            with open(BATTERY_DATA_FILE, "r") as f:
                self.data = json.load(f)

    def save(self):
        with open(BATTERY_DATA_FILE, "w") as f:
            json.dump(self.data, f, indent=2)

    def check_in(self, tag):
        now = time.time()
        if tag not in self.data:
            self.data[tag] = {
                "id": tag,
                "checked_in": now,
                "last_seen": now,
                "cycles": 0,
                "total_charge_time": 0,
                "average_charge_time": 0
            }
        elif self.data[tag].get("checked_in") is None:
            self.data[tag]["checked_in"] = now
            self.data[tag]["last_seen"] = now
        else:
            self.data[tag]["last_seen"] = now

    def check_out(self, tag_id):
        now = time.time()
        if tag_id in self.data:
            entry = self.data[tag_id]

            # Ensure required keys exist
            entry.setdefault("checked_in", None)
            entry.setdefault("total_charge_time", 0)
            entry.setdefault("last_check_out", None)
            entry.setdefault("cycles", 0)

            if entry["checked_in"] is not None:
                duration = now - entry["checked_in"]
                entry["total_charge_time"] += duration
                entry["last_check_out"] = now
                entry["checked_in"] = None
                entry["cycles"] += 1
                self.save()



    def get_status(self):
        now = time.time()
        checked_in = []
        checked_out = []
        for tag, info in self.data.items():
            if now - info.get("last_check_out", 0) < now - info.get("last_check_in", 0):
                checked_in.append(tag)
            else:
                checked_out.append(tag)
        return checked_in, checked_out

    def get_metadata(self):
        result = {}
        for tag, info in self.data.items():
            result[tag] = {
                "usage_cycles": info.get("cycles", 0),
                "total_charge_time": info.get("total_charge_time", 0)
            }
        return result

    def get_stats(self, tag):
        entry = self.data.get(tag)
        if entry:
            return {
                "cycles": entry.get("cycles", 0),
                "average_charge_time": entry.get("average_charge_time", 0)
            }
        return None


shared_rfid_manager = BatteryDataManager()