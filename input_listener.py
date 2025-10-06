from datetime import datetime
import serial
import threading
import time
import json
from os import getenv
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
from dotenv import load_dotenv

# === CONFIGURATION ===
load_dotenv()

# open the json and load the serial port IDS of the arduinos. change hardwareIDS.json to change your hardware ids of your arduinos.
with open("hardwareIDS.json") as hardwareID:
    RemoteID = json.load(hardwareID)

COM_PORT1 = RemoteID["COM_PORT1"] #init com ports
#COM_PORT2 = RemoteID["COM_PORT2"] 
BAUD_RATE = 9600
MATCH_WINDOW_SECONDS = 1.0 #change to adjust the window for matching slots and RFID ID numbers.
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

# === SERIAL SHARED OBJECTS (ADDED) ===
# store opened serial.Serial objects here so the LED thread can reuse the same open port
serial_ports = {}            # port_str -> serial.Serial object
serial_ports_lock = threading.Lock()

# === LED CONFIG (ADDED) ===
POSITIONS = [0, 40, 80, 120, 160, 200, 240]  #pos for 0-6. LED width is 5 LEDS. number is where the center LED is positioned at.
HUE_RED = 0
HUE_ORANGE = 25
HUE_BLUE = 170
HUE_GREEN = 85
POLL_INTERVAL = 0.5      # seconds between DB polls
HEARTBEAT_INTERVAL = 2.0 # seconds between PING heartbeats
last_sent_command = {}   # slot -> (mode, hue, pos) to reduce redundant writes

# === UTILITY ===
def timestamp(ts=None):
    return datetime.fromtimestamp(ts or time.time()).strftime("%Y-%m-%d %H:%M:%S")

def parse_timestamp_to_epoch(ts_str):
    """Parse timestamp strings of format '%Y-%m-%d %H:%M:%S' to epoch seconds.
       Return None if parsing fails."""
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        return time.mktime(dt.timetuple())
    except Exception:
        return None

def safe_write_serial_port_obj(ser, data):
    """Write bytes to serial.Serial object if available. Returns True on success."""
    if ser is None:
        return False
    try:
        if isinstance(data, str):
            data = data.encode('utf-8')
        ser.write(data)
        return True
    except Exception as e:
        print(f"[SERIAL WRITE ERROR] {e}")
        return False
#
def safe_write_serial(port, data):
    """Thread-safe write to a serial port if present in serial_ports map."""
    with serial_ports_lock:
        ser = serial_ports.get(port)
    return safe_write_serial_port_obj(ser, data)

# === SERIAL HANDLER THREAD ===
#literally just starts listening to the arduinos and when it detects a change start a match

def handle_serial(Serialport):
    ser = None
    while True:    
        try:
            ser = serial.Serial(Serialport, BAUD_RATE) #opens the serial port
            print(f"[SERIAL] Serial connected at {Serialport}")
            print("[STATUS] Ready")
            # --- ADDED: publish opened serial object for other threads to use (LED manager)
            with serial_ports_lock:
                serial_ports[Serialport] = ser
            break
        except Exception as e:
            print(f"[SERIAL] error {e} retrying in 5 seconds") #functionality to retry the serial port if the specified arduino isnt detected.
            time.sleep(5)


    while True:
        try:
            raw_line = ser.readline().decode("utf-8").strip() #specifies the character scheme
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
                    
                    #if pending_tags changes between finding and removing it will raise value error. this is safer i think
                    try:
                        pending_tags.remove((matched_tag, t_time))
                    except ValueError:
                        pass
                    
                    #Add the newly scanned battery/tag to the 'CurrentChargingList' to show as actively charging
                    ref.child('CurrentChargingList/' + matched_tag).update({
                        'ID': matched_tag,
                        'ChargingStartTime': timestamp(now), #Use this timestamp to later determine how long it's been charging for
                    })

                    #Pull all records of charging for this battery/tag
                    getCurrentChargingRecords = ref.child('BatteryList/' + matched_tag + '/ChargingRecords').get()

                    if getCurrentChargingRecords is None: #Incase this is the first charge record for this battery/tag
                      getCurrentChargingRecords = [] #create an empty array for charging records
                      getCurrentChargingRecords.append({'StartTime': timestamp(now),'ChargingSlot': slot,'ID' : 0}) #Append the first record with the current start time and slot

                    else: #Otherwise  append a new record with the current start time and slot
                      getCurrentChargingRecords.append({'StartTime': timestamp(now),'ChargingSlot': slot,'ID': len(getCurrentChargingRecords)})

                    #Update the battery within firebase with the new charging data
                    ref.child('BatteryList/' + matched_tag).update({
                        'ID': matched_tag, #Battery Tag ID
                        'ChargingRecords': getCurrentChargingRecords, #Pass in new array with appended record
                        'IsCharging': True, #Set charging as true
                        'ChargingSlot': slot, #Current slot the battery is charging in
                        'ChargingStartTime': timestamp(now), #When was the most recent time it started charging - used to determine how long it's been charging for/Now time
                        'ChargingEndTime': None, #Remove the ChargingEndTime as it's currently charging
                        'LastChargingSlot': None, #Remove the LastChargingSlot as it's currently charging
                    })
                    
                    # Check if battery has a name in BatteryNames
                    name_ref = ref.child(f'BatteryNames/{matched_tag}')
                    if not name_ref.get():
                        # Trigger the frontend to prompt naming
                        ref.child(f'NameRequests/{matched_tag}').set({
                            'Slot': slot,
                            'Timestamp': timestamp(now),
                            'ID': matched_tag
                        })


            elif state == "REMOVED":
                if prev_tag:
                    print(f"[REMOVED] Tag {prev_tag} removed from slot {slot} at {timestamp(now)}")
                    slot_status[slot]["tag"] = None

                    # Remove the newly removed battery/tag from the 'CurrentChargingList' to show as no longer actively charging
                    ref.child('CurrentChargingList/' + prev_tag).delete()

                    #Get the current (Now removed) charging slot for this battery/tag
                    chargingSlot = ref.child(f'BatteryList/{prev_tag}/ChargingSlot').get()

                    #Pull all records of charging for this battery/tag
                    getCurrentChargingRecords = ref.child('BatteryList/' + prev_tag + '/ChargingRecords').get()

                    #Count the number of existing records to determine the ID of the most recent record
                    count = len(getCurrentChargingRecords) if getCurrentChargingRecords else 0 #Set to 0 if this is the first record for firebase 'array'

                    startTime = ref.child(f'BatteryList/{prev_tag}/ChargingRecords/{count-1}/StartTime').get() #Pull the start time of the most recent record to determine duration
                    endTime = timestamp(now) #Set the end time as now since it's just been removed
                    endTimeStamp = timestamp(now) #Set the end time as now since it's just been removed


                    endTime = datetime.strptime(endTime, "%Y-%m-%d %H:%M:%S") #Convert to datetime object
                    startTime = datetime.strptime(startTime, "%Y-%m-%d %H:%M:%S") #Convert to datetime object
                    duration = endTime - startTime #Determine the duration between start and end time 

                    #Update the most recent record with the end time and duration, count-1 is used to get the most recent record since arrays are 0 indexed in Firebase
                    ref.child(f'BatteryList/{prev_tag}/ChargingRecords/{count-1}').update({'EndTime': endTimeStamp, 'Duration': str(duration.total_seconds())[:-2]}) #Duration is saved in SECONDS with removing the default '.0' left with the total_seconds method I.E '30.0' seconds is saved as '30'


                    #Remove the last record from the array to prevent it from being counted twice
                    #This last record is the one just updated, however is currently stored locally without duration/endtime
                    #Basically, remove the incomplete record from the local copy of the records array to then later add the completed record locally
                    del getCurrentChargingRecords[-1]

                    #Due to not waiting on confirmation from firebase that the above update has been made, manually append the end time and duration to the local copy of the records array
                    getCurrentChargingRecords.append({'StartTime': startTime,'EndTime': endTime,'Duration': str(duration.total_seconds())[:-2]})

                    #Calculate the overall charge time and average charge time
                    #Note, everything is in SECONDS
                    overallDuration = 0
                    avgDuration = 0
                    totalCycles = 0 #Get the total number of cycles for this battery/tag

                    minTimeSetting = ref.child(f'Settings/minTime').get() #Get the minimum time settings for the battery

                    for record in getCurrentChargingRecords: #Loop through all records for this battery/tag
                        
                        if float(record['Duration']) >= int(minTimeSetting): #Only count records that are above the minimum time setting
                            totalCycles += 1 #Increment the total cycles for this battery/tag
                            overallDuration += int(record.get('Duration')) #Overall charge time is the sum of all durations in the records array

                    if totalCycles > 0:    
                      avgDuration = overallDuration/totalCycles   #Average charge time is the overall charge time divided by the number of cycles
                      avgDuration = "{:.0f}".format(avgDuration) #Format to remove decimal places, this also rounds DOWN by removing the decimal places

                    if int(str(duration.total_seconds())[:-2]) < int(minTimeSetting):
                        ref.child('BatteryList/' + prev_tag).update({
                        'ID': prev_tag,
                        'IsCharging': False, #Set charging as false
                        'ChargingSlot': None, #Remove the ChargingSlot as it's no longer charging
                        'LastChargingSlot': chargingSlot, #Set the last charging slot to the current slot it was charging in
                        'TotalCycles' : totalCycles, #Total number of charge cycles for this battery/tag
                        'AverageChargeTime': avgDuration, #Average charge time in seconds
                        'OverallChargeTime': overallDuration, #Overall lifetime charge time in seconds
                    })
                    else:
                        ref.child('BatteryList/' + prev_tag).update({
                        'ID': prev_tag,
                        'IsCharging': False, #Set charging as false
                        'ChargingSlot': None, #Remove the ChargingSlot as it's no longer charging
                        'LastChargingSlot': chargingSlot, #Set the last charging slot to the current slot it was charging in
                        'ChargingEndTime': timestamp(now), #When was the most recent time it was on a charger
                        'ChargingStartTime': None, #Remove the ChargingStartTime as it's no longer charging
                        'LastOverallChargeTime': str(duration.total_seconds())[:-2], #Set the last overall charge time to the duration of the most recent charge 
                        'TotalCycles' : totalCycles, #Total number of charge cycles for this battery/tag
                        'AverageChargeTime': avgDuration, #Average charge time in seconds
                        'OverallChargeTime': overallDuration, #Overall lifetime charge time in seconds
                    })

#ALEX DO NOT USE .SET ANYMORE DINGUS ONLY USE .UPDATE BRO - Jackson 8/7/2025

# === RFID LISTENER THREAD ===
# essentially all this does is look for a 10 digit string of numbers coming in from the keyboard. if it detects it, add it to pending_tags.

def listen_rfid():
    while True:
        tag_buffer = input().strip()
        if tag_buffer.isdigit() and len(tag_buffer) >= 10:
            tag_id = tag_buffer[-10:]
            now = time.time()
            with lock:
                pending_tags.append((tag_id, now))
                print(f"[RFID] Tag Read: {tag_id} at {timestamp(now)}")
            

# === LED MANAGER THREAD (ADDED) ===
def led_manager_loop():
    """
    Poll firebase every POLL_INTERVAL seconds, determine each slot's state, and send LED commands.
    Heartbeat 'PING' sent every HEARTBEAT_INTERVAL seconds to keep LEDs alive.
    """
    last_heartbeat = 0.0

    # Wait until COM_PORT1 serial is opened by handle_serial
    # This avoids opening the same port twice and ensures we reuse the port in handle_serial.
    while True:
        with serial_ports_lock:
            ser = serial_ports.get(COM_PORT1)
        if ser:
            break
        print("[LED] Waiting for COM_PORT1 to be opened by handle_serial...")
        time.sleep(0.5)

    while True:
        loop_start = time.time()

        # Heartbeat if needed
        if (time.time() - last_heartbeat) >= HEARTBEAT_INTERVAL:
            ok = safe_write_serial(COM_PORT1, "PING\n")
            if ok:
                last_heartbeat = time.time()

        # Read minTime from settings
        try:
            min_time_setting = ref.child('Settings/minTime').get()
            if min_time_setting is None:
                min_time_setting = 0
            else:
                min_time_setting = int(min_time_setting)
        except Exception:
            min_time_setting = 0

        now = time.time()

        # Copy slot_status under lock so we don't hold lock while hitting firebase
        with lock:
            local_slot_status = dict(slot_status)

        slot_evaluations = {}
        current_charging = ref.child('CurrentChargingList').get() or {}

        # helper: find tag for slot via CurrentChargingList/BatteryList if not in local slot_status
        def find_tag_for_slot_db(slot):
            # check CurrentChargingList for tags whose BatteryList ChargingSlot matches
            if isinstance(current_charging, dict):
                for tag in current_charging.keys():
                    try:
                        bslot = ref.child(f'BatteryList/{tag}/ChargingSlot').get()
                        if bslot is not None and int(bslot) == slot:
                            return tag
                    except Exception:
                        continue
            return None

        for slot in range(7):
            entry = {"state": "AVAILABLE", "tag": None, "elapsed": None}

            ls = local_slot_status.get(slot)
            if ls and ls.get("state") == "PRESENT" and ls.get("tag"):
                tag = ls.get("tag")
                entry["state"] = "PRESENT"
                entry["tag"] = tag
                cst = ref.child(f'BatteryList/{tag}/ChargingStartTime').get()
                if not cst:
                    cst = ref.child(f'CurrentChargingList/{tag}/ChargingStartTime').get()
                epoch = parse_timestamp_to_epoch(cst) if cst else None
                if epoch:
                    entry["elapsed"] = now - epoch
            else:
                tag = find_tag_for_slot_db(slot)
                if tag:
                    entry["state"] = "PRESENT"
                    entry["tag"] = tag
                    cst = ref.child(f'BatteryList/{tag}/ChargingStartTime').get()
                    if not cst:
                        cst = ref.child(f'CurrentChargingList/{tag}/ChargingStartTime').get()
                    epoch = parse_timestamp_to_epoch(cst) if cst else None
                    if epoch:
                        entry["elapsed"] = now - epoch
                else:
                    entry["state"] = "AVAILABLE"
                    entry["tag"] = None
                    entry["elapsed"] = None

            slot_evaluations[slot] = entry

        # Determine fully charged slots and pick-next
        fully_charged_slots = []
        for s, e in slot_evaluations.items():
            if e["state"] == "PRESENT" and e["elapsed"] is not None and e["elapsed"] >= min_time_setting:
                fully_charged_slots.append((s, e["elapsed"]))

        pick_next_slot = None
        if fully_charged_slots:
            fully_charged_slots.sort(key=lambda x: x[1], reverse=True)
            pick_next_slot = fully_charged_slots[0][0]

        # Send LED commands
        for slot in range(7):
            ev = slot_evaluations[slot]
            if ev["state"] == "AVAILABLE":
                mode = "PULSE"
                hue = HUE_ORANGE
            elif ev["state"] == "PRESENT":
                if ev["elapsed"] is not None and ev["elapsed"] >= min_time_setting:
                    if slot == pick_next_slot:
                        mode = "DEEPPULSE"
                        hue = HUE_GREEN
                    else:
                        mode = "SOLID"
                        hue = HUE_BLUE
                else:
                    mode = "SOLID"
                    hue = HUE_RED
            else:
                mode = "PULSE"
                hue = HUE_ORANGE

            pos = POSITIONS[slot] if slot < len(POSITIONS) else 0
            this_cmd_tuple = (mode, hue, pos)
            last = last_sent_command.get(slot)
            if last != this_cmd_tuple:
                cmd_str = f"SEG {slot} POS {pos} COLOR {hue} MODE {mode}\n"
                ok = safe_write_serial(COM_PORT1, cmd_str)
                if ok:
                    print(f"[LED] Sent: {cmd_str.strip()}")
                    last_sent_command[slot] = this_cmd_tuple
                else:
                    print(f"[LED] Failed to send LED command for slot {slot} (serial not ready)")

        # Sleep until next poll
        elapsed_loop = time.time() - loop_start
        to_sleep = POLL_INTERVAL - elapsed_loop
        if to_sleep > 0:
            time.sleep(to_sleep)


# === MAIN ===

if __name__ == "__main__":
    threading.Thread(target=handle_serial, args=(COM_PORT1,), daemon=True).start() #args is now the com port for each arduino, kept in hardwareIDS.json. This is so we can listen to both arduinos
    #threading.Thread(target=handle_serial, args=(COM_PORT2,), daemon=True).start()

    # Start the LED manager thread (reads DB and writes LED commands using the same COM_PORT1 serial object)
    threading.Thread(target=led_manager_loop, daemon=True).start()

    listen_rfid()

    # Keep alive
    while True:
        time.sleep(1)
