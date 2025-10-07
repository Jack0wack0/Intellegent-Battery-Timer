import os
from os import getenv
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
from dotenv import load_dotenv
import time
from datetime import datetime

load_dotenv()

FIREBASE_DB_BASE_URL = getenv('FIREBASE_DB_BASE_URL')
FIREBASE_CREDS_FILE = getenv('FIREBASE_CREDS_FILE')

# Initialize the app with a service account, granting admin privileges
cred = credentials.Certificate(FIREBASE_CREDS_FILE)
firebase_admin.initialize_app(cred, {
    'databaseURL': FIREBASE_DB_BASE_URL
})

def timestamp(ts=None):
    return datetime.fromtimestamp(ts or time.time()).strftime("%Y-%m-%d %H:%M:%S")

prevtag = "0000000001"
ref = db.reference('/')
now = time.time()

ref.child('BatteryList/' + prevtag).update({
                        'ID': prevtag, #Battery Tag ID
                        'IsCharging': True, #Set charging as true
                        'ChargingSlot': 0, #Current slot the battery is charging in
                        'ChargingStartTime': timestamp(now), #When was the most recent time it started charging - used to determine how long it's been charging for/Now time
                        'ChargingEndTime': None, #Remove the ChargingEndTime as it's currently charging
                        'LastChargingSlot': None, #Remove the LastChargingSlot as it's currently charging
})

#id_test = ref.child('BatteryList/1').get()

#print('Data from Firebase: ' + str(id_test))