import serial
import threading
import time
from pynput import keyboard
import queue

ARDUINO_PORT = 'COM4'
BAUDRATE = 9600
MATCH_WINDOW = 1.5  # seconds tolerance for matching tag to slot presence

tag_queue = queue.Queue()

# Thread-safe list of (slot_id, state, timestamp)
slot_events = []
slot_events_lock = threading.Lock()

class SlotListener(threading.Thread):
    def __init__(self, port, baudrate=9600):
        super().__init__()
        self.ser = serial.Serial(port, baudrate, timeout=1)
        self.running = True

    def run(self):
        while self.running:
            try:
                line = self.ser.readline().decode(errors='ignore').strip()
                if not line:
                    continue
                #print(f"[Arduino Raw] {line}")  # debug print

                if line.startswith("SLOT_") and (":PRESENT" in line or ":REMOVED" in line):
                    try:
                        slot_id_str = line.split("_")[1].split(":")[0]
                        slot_id = int(slot_id_str)
                    except (IndexError, ValueError) as e:
                        print(f"[Arduino Error] Failed to parse slot_id: {e}")
                        continue

                    state = line.split(":")[1]
                    timestamp = time.time()

                    with slot_events_lock:
                        slot_events.append((slot_id, state, timestamp))

                    if state == "PRESENT":
                        print(f"[Arduino] Slot {slot_id} reports: PRESENT")
                    elif state == "REMOVED":
                        print(f"[Arduino] Slot {slot_id} reports: REMOVED")
            except Exception as e:
                print(f"[Arduino Error] {e}")

    def stop(self):
        self.running = False
        self.ser.close()

class TagListener(threading.Thread):
    def __init__(self):
        super().__init__()
        self.buffer = ""
        self.running = True
        self.listener = keyboard.Listener(on_press=self.on_press)

    def on_press(self, key):
        try:
            char = key.char
            if char.isdigit():
                self.buffer += char
                if len(self.buffer) >= 10:  # assuming tag length 10 digits
                    timestamp = time.time()
                    tag_queue.put((self.buffer, timestamp))
                    print(f"[RFID] Tag Read: {self.buffer}")
                    self.buffer = ""
        except AttributeError:
            pass

    def run(self):
        self.listener.start()
        self.listener.join()

    def stop(self):
        self.running = False
        self.listener.stop()

def prune_old_events(max_age=10):
    """Remove slot events older than max_age seconds."""
    cutoff = time.time() - max_age
    with slot_events_lock:
        while slot_events and slot_events[0][2] < cutoff:
            slot_events.pop(0)

def find_slot_for_tag(t_tag, window=MATCH_WINDOW):
    with slot_events_lock:
        # Filter events within [t_tag - window, t_tag + window]
        relevant_events = [e for e in slot_events if t_tag - window <= e[2] <= t_tag + window]

    # For each slot, find the latest event within window
    latest_events = {}
    for slot_id, state, ts in sorted(relevant_events, key=lambda x: x[2]):
        latest_events[slot_id] = (state, ts)

    # Find slots currently present in this window
    present_slots = [slot for slot, (state, _) in latest_events.items() if state == "PRESENT"]

    if len(present_slots) == 1:
        return present_slots[0]
    else:
        return None

def match_tag_to_slot():
    while True:
        try:
            tag, tag_time = tag_queue.get(timeout=0.5)
        except queue.Empty:
            prune_old_events()  # clean old events periodically
            continue

        print(f"[MATCH] Trying to match tag {tag} at time {tag_time}")
        matched_slot = find_slot_for_tag(tag_time)

        if matched_slot is not None:
            print(f"[MATCH] Battery {tag} assigned to slot {matched_slot} at {time.strftime('%H:%M:%S')}")
        else:
            print(f"[NO MATCH] Battery {tag} read but no unique slot match found at {time.strftime('%H:%M:%S')}")

def main():
    slot_listener = SlotListener(ARDUINO_PORT, BAUDRATE)
    tag_listener = TagListener()

    slot_listener.start()
    tag_listener.start()

    matcher_thread = threading.Thread(target=match_tag_to_slot, daemon=True)
    matcher_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        slot_listener.stop()
        tag_listener.stop()
        slot_listener.join()
        tag_listener.join()

if __name__ == '__main__':
    main()

#THIS IS STILL BROKEN IDK HOW TO FIX IT I WILL GET CHATGPT TO DO IT LATER
# i will scan a tag and i get the raw arduino data just fine but it for some reason doesnt bind it to the tag id. 