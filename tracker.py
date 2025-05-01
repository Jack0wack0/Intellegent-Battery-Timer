import time
from collections import defaultdict

class BatteryTracker:
    def __init__(self):
        self.batteries = defaultdict(lambda: {'first_seen': 0, 'last_seen': 0})

    def update(self, detected_qrs):
        now = time.time()
        for qr in detected_qrs:
            if qr:
                if 'first_seen' not in self.batteries[qr] or self.batteries[qr]['first_seen'] == 0:
                    self.batteries[qr]['first_seen'] = now
                self.batteries[qr]['last_seen'] = now

        for key in list(self.batteries):
            if now - self.batteries[key]['last_seen'] > 30:
                del self.batteries[key]

    def get_all(self):
        return dict(self.batteries)

shared_tracker = BatteryTracker()
