import os
from os import getenv
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
from dotenv import load_dotenv

load_dotenv()

FIREBASE_DB_BASE_URL = getenv('FIREBASE_DB_BASE_URL')
FIREBASE_CREDS_FILE = getenv('FIREBASE_CREDS_FILE')

# Initialize the app with a service account, granting admin privileges
cred = credentials.Certificate(FIREBASE_CREDS_FILE)
firebase_admin.initialize_app(cred, {
    'databaseURL': FIREBASE_DB_BASE_URL
})

ref = db.reference('/')

ref.child('test').set({
          'name': 'Helloworld',
          'id': 5454
      })

id_test = ref.child('BatteryList/1').get()

print('Data from Firebase: ' + str(id_test))