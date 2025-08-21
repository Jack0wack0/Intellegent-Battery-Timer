from datetime import datetime
from numpy import record
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

                    #Add the newly scanned battery/tag to the 'CurrentChargingList' to show as actively charging
                    ref.child('CurrentChargingList/' + matched_tag).update({
                        'ID': matched_tag,
                        'ChargingStartTime': timestamp(now), #Use this timestamp to later determine how long it's been charging for
                    })

                    #Pull all records of charging for this battery/tag
                    getCurrentChargingRecords = ref.child('BatteryList/' + matched_tag + '/ChargingRecords').get()

                    if getCurrentChargingRecords is None: #Incase this is the first charge record for this battery/tag
                      getCurrentChargingRecords = [] #Start with an empty array
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

                    if int(str(duration.total_seconds())[:-2]) < minTimeSetting:
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
if __name__ == "__main__":
    threading.Thread(target=handle_serial, daemon=True).start()
    listen_rfid()

    # Keep alive
    while True:
        time.sleep(1)

