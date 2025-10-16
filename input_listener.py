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
import logging
from logging.handlers import RotatingFileHandler
import sys
import re

# === CONFIGURATION ===
load_dotenv()

# === LOGGING CONFIGURATION ===
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

# Rotating file handler (keeps last 5 logs, each up to 5MB)
file_handler = RotatingFileHandler("log.txt", maxBytes=5*1024*1024, backupCount=5, encoding="utf-8")
file_formatter = logging.Formatter("%(asctime)s [%(name)s] [%(levelname)s] %(message)s")
file_handler.setFormatter(file_formatter)
file_handler.setLevel(logging.DEBUG)

# Color-coded console handler
class ColorFormatter(logging.Formatter):
    COLORS = {
        "FIREBASE": "\033[96m",  # cyan
        "LED": "\033[93m",       # yellow
        "RFID": "\033[92m",      # green
        "SERIAL": "\033[95m",    # magenta
        "TIME": "\033[94m",      # blue
        "MATCH PROCESS": "\033[91m",  # red
        "GENERAL": "\033[97m",   # white
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.name, "\033[97m")
        formatted = super().format(record)
        return f"{color}{formatted}{self.RESET}"

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = ColorFormatter("%(asctime)s [%(name)s] [%(levelname)s] %(message)s")
console_handler.setFormatter(console_formatter)

root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Subsystem loggers
firebase_log = logging.getLogger("FIREBASE")
led_log = logging.getLogger("LED")
rfid_log = logging.getLogger("RFID")
serial_log = logging.getLogger("SERIAL")
general_log = logging.getLogger("GENERAL")
time_log = logging.getLogger("TIME")
match_log = logging.getLogger("MATCH PROCESS")

# === SMART PRINT REDIRECTOR ===
loggers = {
    "FIREBASE": firebase_log,
    "LED": led_log,
    "RFID": rfid_log,
    "SERIAL": serial_log,
    "TIME": time_log,
    "MATCH": match_log,
    "GENERAL": general_log,
}

def smart_print(*args, **kwargs):
    msg = " ".join(map(str, args))
    match = re.match(r"\[(\w+)\]\s*(.*)", msg)
    if match:
        subsystem, rest = match.groups()
        logger = loggers.get(subsystem.upper(), general_log)
        logger.info(rest)
    else:
        general_log.info(msg)

# Override built-in print
print = smart_print

general_log.info("Logging initialized. Program has just been started. ================ LOG START ================")

# open the json and load the serial port IDS of the arduinos. change hardwareIDS.json to change your hardware ids of your arduinos.
with open("hardwareIDS.json") as hardwareID:
    RemoteID = json.load(hardwareID)

COM_PORT1 = RemoteID["COM_PORT1"] #init com ports
COM_PORT2 = RemoteID["COM_PORT2"] 
BAUD_RATE = 9600
MATCH_WINDOW_SECONDS = 1.0 #change to adjust the window for matching slots and RFID ID numbers.
FIREBASE_DB_BASE_URL = getenv('FIREBASE_DB_BASE_URL')
FIREBASE_CREDS_FILE = getenv('FIREBASE_CREDS_FILE')

general_log.info(f"Loaded hardware IDs: {RemoteID}")
firebase_log.info(f"Firebase initializing.")

if not FIREBASE_DB_BASE_URL or not FIREBASE_CREDS_FILE:
    firebase_log.critical("Missing Firebase configuration in environment variables!")
    general_log.critical("Missing credentials. Program will not start.")
    general_log.info("program exited with error")
    sys.exit(1)


# Initialize the app with a service account, granting admin privileges
cred = credentials.Certificate(FIREBASE_CREDS_FILE)
firebase_log.info("Creds loaded")
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
POSITIONS = [10, 20, 30, 40, 50, 60, 70]  #pos for 0-6. LED width is 5 LEDS. number is where the leftmost LED is placed.
HUE_RED = 0 #hue can be 0-255
HUE_ORANGE = 25
HUE_BLUE = 170
HUE_GREEN = 85
POLL_INTERVAL = 0.5      # seconds between DB polls. This works do not change it.
HEARTBEAT_INTERVAL = 2.0 # seconds between PING heartbeats. this is used on init then never again. 
last_sent_command = {}   # slot -> (mode, hue, pos) to reduce redundant writes
MAX_RETRIES = 5 # if you have special code on your arduino you may need to increase the amount of retries.
ACK_TIMEOUT = 2.0  # seconds
ack_received = threading.Event()
general_log.debug("CONSTANTS INITIALIZED")

# === UTILITY ===
def timestamp(ts=None):
    time_log.debug("Timestamp format set")
    return datetime.fromtimestamp(ts or time.time()).strftime("%Y-%m-%d %H:%M:%S") #define our timestamp format
    

def parse_timestamp_to_epoch(ts_str):
    """Parse timestamp strings of format '%Y-%m-%d %H:%M:%S' to epoch seconds.
       Return None if parsing fails."""
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        time_log.debug(f"Parsed timestamp {ts_str} to epoch. Parsing successful.")
        return time.mktime(dt.timetuple())
    except Exception:
        time_log.error(f"Failed to parse timestamp")
        return None

def safe_write_serial_port_obj(ser, data):
    """Write bytes to serial.Serial object if available. Returns True on success."""
    if ser is None:
        return False
    try:
        if isinstance(data, str):
            data = data.encode('utf-8')
        ser.write(data)
        serial_log.debug("serial opened")
        return True
    except Exception as e:
        serial_log.critical(f"SERIAL WRITE ERROR {e}")
        return False

def safe_write_serial(port, data):
    """Thread-safe write to a serial port if present in serial_ports map."""
    with serial_ports_lock:
        ser = serial_ports.get(port)
    serial_log.debug("safe write serial set")
    return safe_write_serial_port_obj(ser, data)

# === SERIAL HANDLER THREAD ===
#literally just starts listening to the arduinos and when it detects a change start a match

def handle_serial(Serialport):
    ser = None
    while True:    
        try:
            ser = serial.Serial(Serialport, BAUD_RATE) #opens the serial port
            serial_log.debug(f"Serial connected at {Serialport}")
            general_log.info("Ready")
            time.sleep(1)
            #publish opened serial object for other threads to use (LED manager)
            with serial_ports_lock:
                serial_ports[Serialport] = ser
                serial_log.debug(f"Published serial port {Serialport} for shared use")
            break
        except Exception as e:
            serial_log.critical(f"error {e} retrying in 5 seconds")
            time.sleep(5)

    #keeps resending commands until the arduino recieves it.
    while True:
        try:
            raw_line = ser.readline().decode("utf-8").strip()
            serial_log.warning(f"Serial read failed on {Serialport}, retrying...")
        except Exception:
            continue
        
        # --- ACK Handling ---
        if raw_line == "ACK" or raw_line == "OK":
            ack_received.set()
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

        now = time.time() #set now to our timestamp

        with lock:
            if slot not in slot_status:
                slot_status[slot] = {"state": None, "last_change": 0, "tag": None} 

            prev_tag = slot_status[slot]["tag"] #set previous tag
            slot_status[slot]["state"] = state
            slot_status[slot]["last_change"] = now 

            if state == "PRESENT":
                
                # Try to match with pending RFID tag
                matched_tag = None
                
                for tag, t_time in pending_tags:
                    match_log.debug(f"Comparing tag time {timestamp(t_time)} to slot time {timestamp(now)}")
                    if abs(now - t_time) <= MATCH_WINDOW_SECONDS:
                        matched_tag = tag 
                        match_log.info(f"Tag Pulled: {matched_tag}")
                        break
                if matched_tag:
                    match_log.info(f"Tag {matched_tag} matched to slot {slot} at {timestamp(now)}")
                    slot_status[slot]["tag"] = matched_tag
                    
                    #if pending_tags changes between finding and removing it will raise value error.
                    try:
                        pending_tags.remove((matched_tag, t_time))
                    except ValueError:
                        pass
                    
                    #Add the newly scanned battery/tag to the 'CurrentChargingList' to show as actively charging
                    #this could possibly be removed as i can just look at IsCharging: True. 
                    ref.child('CurrentChargingList/' + matched_tag).update({
                        'ID': matched_tag,
                        'ChargingStartTime': timestamp(now), #Use this timestamp to later determine how long it's been charging for
                    })
                    firebase_log.debug("Added to CurrentChargingList")
                    #Pull all records of charging for this battery/tag
                    getCurrentChargingRecords = ref.child('BatteryList/' + matched_tag + '/ChargingRecords').get()

                    if getCurrentChargingRecords is None: #Incase this is the first charge record for this battery/tag
                      getCurrentChargingRecords = [] #create an empty array for charging records
                      getCurrentChargingRecords.append({'StartTime': timestamp(now),'ChargingSlot': slot,'ID' : 0}) #Append the first record with the current start time and slot
                      firebase_log.info(f"First record for {matched_tag} created")

                    else: #Otherwise append a new record with the current start time and slot
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
                    firebase_log.debug(f"Checking for name for {matched_tag}")
                    if not name_ref.get():
                        # Trigger the frontend to prompt naming
                        firebase_log.debug(f"No name found for {matched_tag}, prompting for name.")
                        ref.child(f'NameRequests/{matched_tag}').set({
                            'Slot': slot,
                            'Timestamp': timestamp(now),
                            'ID': matched_tag
                        })

            elif state == "REMOVED":
                if prev_tag:
                    match_log.info(f"Tag {prev_tag} removed from slot {slot} at {timestamp(now)}")
                    slot_status[slot]["tag"] = None
                    # Remove the newly removed battery/tag from the 'CurrentChargingList' to show as no longer actively charging
                    ref.child('CurrentChargingList/' + prev_tag).delete() #again this could be deleted.
                    firebase_log.info("Removed from CurrentChargingList")

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
                    firebase_log.debug(f"Duration for {prev_tag} was {duration}")

                    #Update the most recent record with the end time and duration, count-1 is used to get the most recent record since arrays are 0 indexed in Firebase
                    ref.child(f'BatteryList/{prev_tag}/ChargingRecords/{count-1}').update({'EndTime': endTimeStamp, 'Duration': str(duration.total_seconds())[:-2]}) #Duration is saved in SECONDS with removing the default '.0' left with the total_seconds method I.E '30.0' seconds is saved as '30'

                    #Remove the last record from the array to prevent it from being counted twice
                    #This last record is the one just updated, however is currently stored locally without duration/endtime
                    #Basically, remove the incomplete record from the local copy of the records array to then later add the completed record locally
                    del getCurrentChargingRecords[-1]

                    #Due to not waiting on confirmation from firebase that the above update has been made, manually append the end time and duration to the local copy of the records array
                    getCurrentChargingRecords.append({'StartTime': startTime,'EndTime': endTime,'Duration': str(duration.total_seconds())[:-2]})
                    firebase_log.info(f"Updated record for {prev_tag} with end time and duration")

                    #Calculate the overall charge time and average charge time
                    #Note, everything is in SECONDS
                    overallDuration = 0
                    avgDuration = 0
                    totalCycles = 0 #Get the total number of cycles for this battery/tag
                    minTimeSetting = ref.child(f'Settings/minTime').get() #Get the minimum time settings for the battery.
                    firebase_log.debug(f"Pulled Minimum Time Setting {minTimeSetting} seconds")
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

#ALEX DO NOT USE .SET ANYMORE ONLY USE .UPDATE YOU PMO - Jackson 8/7/2025


# === RFID LISTENER THREAD ===
# essentially all this does is look for a 10 digit string of numbers coming in from the keyboard. if it detects it, add it to pending_tags.

def listen_rfid():
    while True:
        tag_buffer = input().strip() #read the input and add it to a buffer variable
        rfid_log.info(f"Input Received, added to buffer: {tag_buffer}")
        if tag_buffer.isdigit() and len(tag_buffer) >= 10: #if its a valid tag scan, not just someone typing
            tag_id = tag_buffer[-10:] 
            now = time.time()
            with lock:
                pending_tags.append((tag_id, now)) #timestamp the tag scan and send it off to be matched with a slot <3
                rfid_log.info(f"Tag Read: {tag_id} at {timestamp(now)}")
        else:
            rfid_log.warning(f"Ignored invalid input: {tag_buffer}") #log it
            tag_buffer = "" #clear the buffer

# === LED MANAGER THREAD ===

def led_manager_loop():
    last_heartbeat = 0.0 #restart heartbeat
    led_log.debug("Heartbeat reset")

    while True:
        with serial_ports_lock:
            ser = serial_ports.get(COM_PORT1) #we have to share the com port so we are just waiting for the parent function (handle_serial) to open the serial interface
        if ser:
            break
        led_log.debug("Waiting for COM_PORT1 to be opened by handle_serial...")
        time.sleep(0.5) #dont spam

    def wait_for_ack(timeout=ACK_TIMEOUT):
        ack_received.clear()
        led_log.debug("Waiting for ACK...")
        return ack_received.wait(timeout=timeout)

    while True:
        loop_start = time.time()

        if (time.time() - last_heartbeat) >= HEARTBEAT_INTERVAL:
            safe_write_serial(COM_PORT1, "PING\n")
            last_heartbeat = time.time()
            led_log.debug("PING sent") 

        try:
            min_time_setting = int(ref.child('Settings/minTime').get() or 0) #pull min time setting for rendering the LEDS
        except Exception:
            min_time_setting = 0

        now = time.time() #i dont think ts does anything
        with lock:
            local_slot_status = dict(slot_status)

        #Pull charging status directly from BatteryList
        batteries_ref = db.reference("BatteryList") 
        batteries = batteries_ref.get() or {} 

        # Build mapping of slot -> (tag, battery_data)
        slot_to_battery = {}
        for tag, data in batteries.items():
            if not isinstance(data, dict): 
                continue
            if data.get("IsCharging") and data.get("ChargingSlot") is not None: #if its currently charging
                slot_to_battery[data["ChargingSlot"]] = (tag, data)
                led_log.info(f"Battery {tag} in slot {data['ChargingSlot']} is charging")

        # Iterate through all slots
        slot_evaluations = {}
        for slot in range(7):
            entry = {"state": "AVAILABLE", "tag": None, "elapsed": None}
            if slot in slot_to_battery:
                tag, bdata = slot_to_battery[slot]
                entry["state"] = "PRESENT"
                entry["tag"] = tag
                cst = bdata.get("ChargingStartTime")
                epoch = parse_timestamp_to_epoch(cst) if cst else None
                if epoch:
                    entry["elapsed"] = time.time() - epoch
            slot_evaluations[slot] = entry

        # Determine which slot is next to remove (longest elapsed)
        fully_charged = [
            (s, e["elapsed"]) for s, e in slot_evaluations.items()
            if e["state"] == "PRESENT" and e["elapsed"] and e["elapsed"] >= min_time_setting
        ]
        pick_next_slot = max(fully_charged, key=lambda x: x[1])[0] if fully_charged else None #i think this is bound to be changed. we should be listening to the database to find what the "next pick" is
        led_log.info(f"Next slot to pick: {pick_next_slot}")
        #TODO: Change this to listen to the database and not compute the best available itself.

        for slot in range(7):
            ev = slot_evaluations[slot]
            if ev["state"] == "AVAILABLE":
                mode, hue = "PULSE", HUE_ORANGE #slot is available
            elif ev["state"] == "PRESENT":
                if ev["elapsed"] and ev["elapsed"] >= min_time_setting:
                    if slot == pick_next_slot:
                        mode, hue = "DEEPPULSE", HUE_GREEN #pick this next
                    else:
                        mode, hue = "SOLID", HUE_BLUE #charged, but not the best available
                else:
                    mode, hue = "SOLID", HUE_RED #currently charging
            else:
                mode, hue = "PULSE", HUE_ORANGE #i dont think this matters but it makes the code look cooler

            pos = POSITIONS[slot] if slot < len(POSITIONS) else 0
            this_cmd = (mode, hue, pos)
            last = last_sent_command.get(slot)

            if this_cmd != last: #just make sure we are not repeating commands
                cmd_str = f"SEG {slot} POS {pos} COLOR {hue} MODE {mode}\n" #sets the command format
                retries = 0
                while retries < MAX_RETRIES: #retry logic
                    if safe_write_serial(COM_PORT1, cmd_str):
                        led_log.info(f"Sent: {cmd_str.strip()} (attempt {retries+1})")
                        if wait_for_ack():
                            last_sent_command[slot] = this_cmd
                            break
                        else:
                            retries += 1
                            led_log.warning(f"No ACK received for slot {slot}, retrying ({retries}/{MAX_RETRIES})...")
                            time.sleep(0.2)
                    else:
                        led_log.error(f"Failed to send command for slot {slot}")
                        break
                if retries >= MAX_RETRIES:
                    led_log.critical(f"Failed to confirm slot {slot} command after {MAX_RETRIES} attempts. Critical error, LEDs may be out of sync.")
                    led_log.warning("LEDS OUT OF SYNC")

            time.sleep(0.1)

        elapsed = time.time() - loop_start
        sleep_time = max(0, POLL_INTERVAL - elapsed)
        time.sleep(sleep_time)



# === MAIN ===

if __name__ == "__main__":
    threading.Thread(target=handle_serial, args=(COM_PORT1,), daemon=True).start() #args is now the com port for each arduino, kept in hardwareIDS.json. This is so we can listen to both arduinos
    threading.Thread(target=handle_serial, args=(COM_PORT2,), daemon=True).start()

    # Start the LED manager thread (reads DB and writes LED commands using the same COM_PORT1 serial object)
    threading.Thread(target=led_manager_loop, daemon=True).start()

    listen_rfid()

    # Keep alive
    while True:
        time.sleep(1)
